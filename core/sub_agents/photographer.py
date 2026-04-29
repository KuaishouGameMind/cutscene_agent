import asyncio
import os
import json
import base64
import io
import traceback
from typing import Any, List, Optional

from PIL import Image
from pydantic import BaseModel, Field
from openai import AsyncOpenAI

from agents import Agent, Runner
from agents.models.openai_chatcompletions import OpenAIChatCompletionsModel
from agents.models.openai_responses import OpenAIResponsesModel
from agents.mcp.server import MCPServerStreamableHttp, MCPServerStreamableHttpParams

_ORIGINAL_FETCH_RESPONSE = OpenAIChatCompletionsModel._fetch_response


async def _debug_fetch_response(self, *args, **kwargs):
    result = await _ORIGINAL_FETCH_RESPONSE(self, *args, **kwargs)
    if isinstance(result, tuple):
        print("\n" + "=" * 50)
        print("[DEBUG] OpenAIChatCompletionsModel._fetch_response returned a tuple causing crash.")
        print(f"[DEBUG] Returned tuple length: {len(result)}")
        if len(result) >= 2:
            raw_response = result[1]
            print(f"[DEBUG] Raw response type: {type(raw_response)}")
            print(f"[DEBUG] Raw response content: {raw_response}")
        else:
            print(f"[DEBUG] Result: {result}")
        print("=" * 50 + "\n")
    else:
        print(f"[DEBUG] _fetch_response result {result}")
    return result


def _enable_debug_fetch_patch() -> None:
    if OpenAIChatCompletionsModel._fetch_response is not _debug_fetch_response:
        OpenAIChatCompletionsModel._fetch_response = _debug_fetch_response

class PhotographerAgentSettings(BaseModel):
    base_url: str = Field(default="")
    api_key: str = Field(..., description="OpenAI API Key")
    model_name: str = Field(default="gpt-4o")
    api_type: str = Field(default="chat_completions", description="API type: 'chat_completions' or 'responses'")
    ue_mcp_url: str = Field(default="http://localhost:8100/mcp")
    image_history_k: int = Field(default=3, description="Number of latest images to keep")
    image_resolution: List[int] = Field(default=[640, 480], description="[width, height] for screenshots")
    image_message_role: str = Field(default="user", description="Role for image messages in the conversation")
    auto_managed_message_role: str = Field(default="developer", description="Role for auto-managed context messages")
    save_debug_screenshot: bool = Field(default=False, description="Whether to save screenshots to local disk for debugging")
    debug_fetch_response: bool = Field(default=False, description="Whether to enable debug monkeypatch for chat completions fetch response")


class PhotographerAgent:
    def __init__(
        self,
        settings: PhotographerAgentSettings,
        *,
        instructions: str | None = None,
        max_turns: int = 10,
    ):
        self.settings = settings
        self.instructions = instructions or self._build_system_prompt()
        self.max_turns = max_turns
        self.conversation: List[dict] = []
        self.mcp_server_ue = None
        self.agent = None
        self.runner = None

    async def initialize(self):
        if self.settings.debug_fetch_response:
            _enable_debug_fetch_patch()

        # Initialize MCP Connection
        self.mcp_server_ue = MCPServerStreamableHttp(
            params=MCPServerStreamableHttpParams(
                url=self.settings.ue_mcp_url,
            ),
            tool_filter=self._context_aware_tool_filter,
            client_session_timeout_seconds=300,
        )
        await self.mcp_server_ue.connect()

        # Initialize Model
        model_client = AsyncOpenAI(
            base_url=self.settings.base_url, 
            api_key=self.settings.api_key
        )
        if self.settings.api_type == "responses":
            model = OpenAIResponsesModel(
                openai_client=model_client,
                model=self.settings.model_name,
            )
        else:
            model = OpenAIChatCompletionsModel(
                openai_client=model_client,
                model=self.settings.model_name,
            )

        self.agent = Agent(
            model=model,
            name="Photographer",
            mcp_servers=[self.mcp_server_ue],
            instructions=self.instructions,
            tool_use_behavior="stop_on_first_tool"
        )

        self.runner = Runner()
        print("[PhotographerAgent] Initialized.")

    def _build_system_prompt(self) -> str:
        return (
            "You are an expert photographer agent controlling a virtual camera. "
            "Your goal is to adjust the camera viewport based on the user's instructions and the current frame.\n"
            "Available tools:\n"
            "- move_view: Move or rotate the camera. This tool works like controlling character movement in a 3D game — all inputs are relative adjustments from the current position. Start with small movements to avoid drastic changes.\n"
            "- undo_move_view: Undo the last viewport movement. Use this when you judge the previous move direction was wrong or the magnitude was too large.\n"
            "- take_editor_screenshot: The system will automatically call this tool, but you should be aware of its existence.\n\n"
            "Workflow:\n"
            "1. Analyze the latest screenshot provided in context.\n"
            "2. If necessary, use 'move_view' or 'undo_move_view' to adjust composition, angle, or position.\n"
            "3. If the viewport is correct, confirm to the user."
        )

    def _context_aware_tool_filter(self, context, tool: dict) -> bool:
        allowed_tool_names = {
            "move_view",
            "undo_move_view",
            "take_editor_screenshot"
        }
        return tool.name in allowed_tool_names

    async def _capture_and_process_screenshot(self) -> Optional[dict]:
        """
        Calls take_editor_screenshot and returns a message dictionary with the image.
        """
        arguments = {"resolution": self.settings.image_resolution}
        result = await self.mcp_server_ue.call_tool("take_editor_screenshot", arguments)
        if not result.isError:
            print(f"image base64: {result.content[0].data[:100]}... (len={len(result.content[0].data)})")
            print(result.content[0].mimeType) # image/png

            if self.settings.save_debug_screenshot:
                debug_image = Image.open(io.BytesIO(base64.b64decode(result.content[0].data)))
                debug_image.save("debug_screenshot.png")

            image_message = {
                "role": self.settings.image_message_role,
                "content": [
                    {
                        "type": "input_text",
                        "text": "Here is the screenshot from the editor automatically captured by the system."
                    },
                    {
                        "type": "input_image",
                        "image_url": f"data:{result.content[0].mimeType};base64,{result.content[0].data}",
                        # "detail": "auto"
                    }
                ]
            }
            return image_message

        return None

    def _manage_history(self, conversation):
        k = self.settings.image_history_k

        image_indices = []
        for i in range(len(conversation) - 1, -1, -1):
            msg = conversation[i]
            content = msg.get("content")
            if isinstance(content, list):
                for j in range(len(content) - 1, -1, -1):
                    item = content[j]
                    if isinstance(item, dict) and item.get("type") in ["image", "input_image", "image_url"]:
                        image_indices.append((i, j))

        if len(image_indices) > k:
            prune_targets = image_indices[k:]
            for msg_idx, content_idx in prune_targets:
                conversation[msg_idx]["content"][content_idx] = {
                    "type": "input_text",
                    "text": "[Image Pruned due to history limit]"
                }
                    
        return conversation

    def _resize_image_if_needed(self, image_data: str, mime_type: str) -> str:
        try:
            target_w, target_h = self.settings.image_resolution
            img_bytes = base64.b64decode(image_data)
            with Image.open(io.BytesIO(img_bytes)) as img:
                if img.width == target_w and img.height == target_h:
                    return image_data

                img = img.resize((target_w, target_h))
                buf = io.BytesIO()
                fmt = "PNG"
                if "jpeg" in mime_type.lower() or "jpg" in mime_type.lower():
                    fmt = "JPEG"

                img.save(buf, format=fmt)
                return base64.b64encode(buf.getvalue()).decode("utf-8")
        except Exception as exc:
            print(f"[PhotographerAgent] Resize failed: {exc}")
            return image_data

    def _extract_screenshot_payload(self, output: Any) -> tuple[str, str] | None:
        output_obj = output
        if isinstance(output_obj, str):
            try:
                output_obj = json.loads(output_obj)
            except json.JSONDecodeError:
                return None

        if isinstance(output_obj, dict) and output_obj.get("type") == "text":
            nested_text = output_obj.get("text")
            if isinstance(nested_text, str):
                try:
                    output_obj = json.loads(nested_text)
                except json.JSONDecodeError:
                    return None

        if not isinstance(output_obj, dict):
            return None

        image_data = output_obj.get("data")
        mime_type = output_obj.get("mimeType") or output_obj.get("mime_type")
        if not image_data or not mime_type:
            return None
        return mime_type, image_data


    def _process_new_items(self, new_items: list[Any]) -> dict[str, Any]:
        call_id_to_toolname = {}
        processed_items = []
        tool_calls_log = []
        final_message = ""
        has_tool_calls = False
        has_message_output = False

        for item in new_items:
            if item.type == "tool_call_item":
                has_tool_calls = True
                call_id = getattr(item.raw_item, "id", "")
                tool_name = item.raw_item.name
                call_id_to_toolname[call_id] = tool_name
                tool_calls_log.append({
                    "tool_name": tool_name,
                    "arguments": item.raw_item.arguments,
                    "call_id": call_id,
                })
                processed_items.append(item.to_input_item())
            elif item.type == "tool_call_output_item":
                output_item = item.to_input_item()
                call_id = item.raw_item.get("call_id")
                tool_name = call_id_to_toolname.get(call_id)
                if tool_name == "take_editor_screenshot":
                    try:
                        payload = self._extract_screenshot_payload(item.raw_item.get("output"))
                        if payload is None:
                            processed_items.append(output_item)
                            continue

                        mime_type, image_data = payload
                        image_data = self._resize_image_if_needed(image_data, mime_type)
                        image_message = {
                            "role": self.settings.image_message_role,
                            "content": [
                                {
                                    "type": "input_text",
                                    "text": f"Here is the screenshot from the editor of tool call {call_id}."
                                },
                                {
                                    "type": "input_image",
                                    "image_url": f"data:{mime_type};base64,{image_data}",
                                    # "detail": "auto"
                                }
                            ]
                        }
                        output_item["output"] = "<Output of take_editor_screenshot is automatically converted to an image message. See the following message.>"

                        processed_items.append(output_item)
                        processed_items.append(image_message)
                    except Exception as e:
                        print(f"[PhotographerAgent] Failed to process screenshot output: {e}")
                        processed_items.append(output_item)
                else:
                    processed_items.append(output_item)
            else:
                if item.type == "message_output_item":
                    has_message_output = True
                    try:
                        final_message = item.raw_item.content[0].text
                    except (AttributeError, IndexError, TypeError):
                        final_message = str(item.raw_item.content)
                processed_items.append(item.to_input_item())

        return {
            "items": processed_items,
            "tool_calls": tool_calls_log,
            "final_message": final_message,
            "has_tool_calls": has_tool_calls,
            "has_message_output": has_message_output,
        }


    async def run(self, user_text: str, *, context: str = "") -> dict[str, Any]:
        conversation = []
        if context:
            conversation.append({
                "role": self.settings.auto_managed_message_role,
                "content": [
                    {
                        "type": "input_text",
                        "text": f"<current_context>\n{context}\n</current_context>",
                    }
                ],
            })
        conversation.append(
            {
                "role": "user",
                "content": user_text
            }
        )

        tool_calls_log = []
        final_message = ""
        turns = 0

        while turns < self.max_turns:
            turns += 1
            try:
                screenshot_message = await self._capture_and_process_screenshot()
                if screenshot_message:
                    conversation.append(screenshot_message)
                conversation = self._manage_history(conversation)
               
                result = await self.runner.run(
                    starting_agent=self.agent,
                    input=conversation,
                    max_turns=10
                )

                processed = self._process_new_items(result.new_items)
                conversation.extend(processed["items"])
                tool_calls_log.extend(processed["tool_calls"])
                if processed["final_message"]:
                    final_message = processed["final_message"]

                if not processed["has_tool_calls"] and processed["has_message_output"]:
                    print("No further tool calls. Task complete.")
                    break

            except Exception as e:
                print(f"Error during execution: {e}")
                traceback.print_exc()
                return {
                    "status": "error",
                    "error": f"{type(e).__name__}: {e}",
                    "traceback": traceback.format_exc(),
                    "tool_calls": tool_calls_log,
                    "tool_calls_count": len(tool_calls_log),
                    "result_summary": final_message,
                    "turns_used": turns,
                }

        return {
            "status": "success",
            "tool_calls": tool_calls_log,
            "tool_calls_count": len(tool_calls_log),
            "result_summary": final_message,
            "turns_used": turns,
        }

    async def cleanup(self):
        if self.mcp_server_ue is not None:
            await self.mcp_server_ue.cleanup()

if __name__ == "__main__":
    settings = PhotographerAgentSettings(
        api_key=os.getenv("CUTSCENE_AGENT_API_KEY"),
        model_name="GEMINI_25_PRO",
        image_history_k=5,
        image_resolution=[1280, 720]
    )

    agent = PhotographerAgent(settings)
    
    try:
        async def main():
            await agent.initialize()
            result = await agent.run("Adjust the current viewport to a side view of the two people in the frame, including their waist and above, centered composition.")
            print(result)
            await agent.cleanup()
            
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nExiting...")


