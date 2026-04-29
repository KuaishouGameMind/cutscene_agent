"""
SubAgent Runner — Sub-agent delegation execution system.

The main Agent invokes SubAgentRunner via FunctionTool, launching a
temporary sub-agent (with its own instructions and tool scope) to execute
sub-tasks and return a result summary to the main Agent.

Three modes are supported:
1. Preset templates (scene_specialist / animation_specialist)
2. Custom mode (custom): main Agent specifies prompt and tool scope
3. Dedicated vision mode (photographer): auto-screenshots and iteratively adjusts viewport
"""
from __future__ import annotations

import json
import traceback
from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING

from agents import Agent, Runner, FunctionTool
from agents.models.openai_chatcompletions import OpenAIChatCompletionsModel
from agents.models.openai_responses import OpenAIResponsesModel
from agents.mcp import MCPServerStreamableHttp, MCPServerStreamableHttpParams
from core.sub_agents.photographer import PhotographerAgent, PhotographerAgentSettings

if TYPE_CHECKING:
    from core.cutscene_agent import CutsceneAgent


# ---------------------------------------------------------------------------
# SubAgentTemplate
# ---------------------------------------------------------------------------

@dataclass
class SubAgentTemplate:
    """Configuration for a preset sub-agent template."""

    name: str
    """Unique template identifier, used as the template_name parameter value."""

    description: str
    """Short description visible to the main Agent LLM for selection."""

    instructions: str
    """System instructions (full prompt) for the sub-agent."""

    allowed_ue_tools: list[str] = field(default_factory=list)
    """List of UE MCP tool names the sub-agent is allowed to call."""

    allowed_external_tools: list[str] = field(default_factory=list)
    """List of External MCP tool names the sub-agent is allowed to call."""

    model_override: str | None = None
    """If not None, the sub-agent uses this model instead of the main Agent's model."""

    max_turns: int = 20
    """Maximum execution turns for the sub-agent."""

    inject_cutscene_content: bool = True
    """Whether to inject current cutscene content into the sub-agent input."""


# ---------------------------------------------------------------------------
# Template Registry
# ---------------------------------------------------------------------------

def _build_scene_specialist_template() -> SubAgentTemplate:
    """Build the scene_specialist template."""
    instructions = (
        "You are a professional scene setup assistant responsible for adding and managing characters in UE according to the director's instructions.\n\n"
        "Your responsibilities:\n"
        "1. Add characters to the scene based on the script\n"
        "2. Set character positions appropriately\n"
        "3. Adjust character orientations\n\n"
    )

    actor_rules = (
        "## Character Management Rules\n"
        "When adding characters, follow this workflow:\n"
        "1. Use get_available_characters to query available characters.\n"
        "2. Use add_character to place characters at specified positions.\n"
        "   - add_character only handles spawning and position, not orientation.\n"
        "   - Side-by-side spacing is about 70, staggered front-back spacing is about 40\n"
        "3. After all characters are added, you must call orient_character_to_center(names) to uniformly adjust orientations.\n"
        "   - orient_character_to_center makes all characters face the group center on the horizontal plane.\n\n"
        "Example (two-person dialogue):\n"
        "- Character A at position (-60, 0, 0)\n"
        "- Character B at position (60, 0, 0)\n"
        "- First call add_character to place A and B respectively\n"
        "- Then call orient_character_to_center([\"A\", \"B\"])\n\n"
        "Example (three-person dialogue, triangular formation):\n"
        "- Character A at position (-60, 0, 0)\n"
        "- Character B at position (30, -52, 0)\n"
        "- Character C at position (30, 52, 0)\n"
        "- First call add_character to place A, B, C respectively\n"
        "- Then call orient_character_to_center([\"A\", \"B\", \"C\"])\n\n"
        "## Tool Calling Rules\n"
        "Call tools sequentially, confirming each step succeeds before proceeding to the next.\n"
        "After completing all operations, output a summary of what you accomplished."
    )

    return SubAgentTemplate(
        name="scene_specialist",
        description="Scene setup specialist: responsible for adding characters to the scene, setting positions and orientations. Suitable for tasks requiring character creation/management in UE.",
        instructions=instructions + actor_rules,
        allowed_ue_tools=[
            "add_character",
            "orient_character_to_center",
            "get_available_characters",
        ],
        allowed_external_tools=[],
        max_turns=20,
        inject_cutscene_content=True,
    )


def _build_animation_specialist_template() -> SubAgentTemplate:
    """Build the animation_specialist template."""
    instructions = (
        "You are a professional animation choreography assistant responsible for selecting and adding appropriate body animations for characters based on the director's instructions.\n\n"
        "Your responsibilities:\n"
        "1. Select appropriate body animations based on character dialogue and emotions\n"
        "2. Add animations to characters on the timeline\n"
        "3. Ensure animation duration matches dialogue duration\n\n"
    )

    animation_rules = (
        "## Animation Rules\n"
        "Use get_available_animations to discover available animation clips before selecting.\n"
        "Choose the most suitable clips based on tag metadata returned by the query.\n"
        "[IMPORTANT] When adding animations to dialogue, select animations with a reasonably matching duration.\n"
        "[IMPORTANT] Animations for the same character must not overlap on the timeline.\n"
        "If the script does not specify corresponding actions, add suitable animations by judging the emotion and dialogue duration.\n\n"
        "## Tool Calling Rules\n"
        "Call tools sequentially, confirming each step succeeds before proceeding to the next.\n"
        "After completing all operations, output a summary of what you accomplished."
    )

    return SubAgentTemplate(
        name="animation_specialist",
        description="Animation choreography specialist: responsible for selecting and adding body animations for characters based on the script and dialogue timeline. Suitable for batch animation tasks.",
        instructions=instructions + animation_rules,
        allowed_ue_tools=[
            "add_character_animation",
            "get_available_animations",
        ],
        allowed_external_tools=[],
        max_turns=30,
        inject_cutscene_content=True,
    )


def _build_photographer_template() -> SubAgentTemplate:
    """Build the photographer template."""
    instructions = (
        "You are an expert photographer agent controlling a virtual camera. "
        "Your goal is to adjust the camera viewport based on the director's instructions and the current frame.\n"
        "Available tools:\n"
        "- move_view: Move or rotate the camera. This tool works like controlling character movement in a 3D game — all inputs are relative adjustments from the current position. Start with small movements to avoid drastic changes.\n"
        "- undo_move_view: Undo the last viewport movement. Use this when you judge the previous move direction was wrong or the magnitude was too large.\n"
        "- take_editor_screenshot: The system automatically provides the latest screenshot at the start of each turn; you can also proactively call this tool to re-observe the frame.\n\n"
        "Workflow:\n"
        "1. Analyze the latest screenshot provided in context.\n"
        "2. If composition, angle, framing, or subject position does not meet requirements, use move_view or undo_move_view for small iterative adjustments.\n"
        "3. When the viewport meets requirements, summarize briefly whether the current frame is satisfactory."
    )

    return SubAgentTemplate(
        name="photographer",
        description="Photography director specialist: responsible for fine-tuning editor viewport and composition based on current screenshots. Suitable for independent camera framing and positioning tasks.",
        instructions=instructions,
        allowed_ue_tools=[
            "move_view",
            "undo_move_view",
            "take_editor_screenshot",
            "take_camera_screenshot",
        ],
        allowed_external_tools=[],
        max_turns=10,
        inject_cutscene_content=True,
    )


# ---------------------------------------------------------------------------
# SubAgentRunner
# ---------------------------------------------------------------------------

class SubAgentRunner:
    """Sub-agent delegation executor.

    Holds a reference to the main Agent to share MCP connections and model configuration.
    After the main Agent calls ``run()``, a temporary Agent is created to execute the sub-task
    and return a structured result.
    """

    def __init__(self, main_agent: "CutsceneAgent") -> None:
        self.main_agent = main_agent
        self.templates: dict[str, SubAgentTemplate] = {}

    def register_template(self, template: SubAgentTemplate) -> None:
        self.templates[template.name] = template

    def get_templates_description(self) -> str:
        """Generate description text for all registered templates, for use in the main Agent prompt."""
        lines = []
        for t in self.templates.values():
            lines.append(f"- **{t.name}**: {t.description}")
        return "\n".join(lines)

    def _resolve_model(self, template: SubAgentTemplate):
        if template.model_override:
            if self.main_agent.settings.api_type == "responses":
                return OpenAIResponsesModel(
                    openai_client=self.main_agent.model_client,
                    model=template.model_override,
                )
            return OpenAIChatCompletionsModel(
                openai_client=self.main_agent.model_client,
                model=template.model_override,
            )
        return self.main_agent.model

    async def run(
        self,
        *,
        template_name: str,
        task: str,
        context: str = "",
        custom_instructions: str = "",
        custom_tool_scope: list[str] | None = None,
    ) -> str:
        """Execute a sub-agent task and return a JSON result summary.

        Parameters
        ----------
        template_name : str
            Preset template name (scene_specialist / animation_specialist / custom).
        task : str
            Task description, passed to the sub-agent as the user message.
        context : str
            Optional context (e.g. current characters, timeline state).
        custom_instructions : str
            Only for custom mode: system instructions for the sub-agent.
        custom_tool_scope : list[str] | None
            Only for custom mode: list of tool names the sub-agent may use.

        Returns
        -------
        str
            JSON-formatted result summary.
        """
        # Resolve template
        if template_name == "custom":
            if not custom_instructions:
                return json.dumps({
                    "status": "error",
                    "error": "custom mode requires the custom_instructions parameter.",
                }, ensure_ascii=False)
            template = SubAgentTemplate(
                name="custom",
                description="Custom sub-agent",
                instructions=custom_instructions,
                allowed_ue_tools=custom_tool_scope or [],
                allowed_external_tools=[],
                max_turns=20,
                inject_cutscene_content=True,
            )
        else:
            template = self.templates.get(template_name)
            if template is None:
                available = ", ".join(self.templates.keys()) or "(none)"
                return json.dumps({
                    "status": "error",
                    "error": f"Unknown template '{template_name}', available templates: {available}",
                }, ensure_ascii=False)

        # Record subagent start
        step_index = self.main_agent._step_counter
        self.main_agent.recorder.record_event(
            event_type="subagent_begin",
            payload={
                "template_name": template_name,
                "task": task,
                "context": context[:500] if context else "",
            },
            step_index=step_index,
        )

        temp_mcp_server = None
        try:
            if template.name == "photographer":
                result = await self._execute_photographer_subagent(template, task, context)
            else:
                result = await self._execute_subagent(template, task, context)
        except Exception as exc:
            result = json.dumps({
                "status": "error",
                "error": f"{type(exc).__name__}: {exc}",
                "traceback": traceback.format_exc(),
            }, ensure_ascii=False)

        # Record subagent end
        self.main_agent.recorder.record_event(
            event_type="subagent_end",
            payload={
                "template_name": template_name,
                "result_preview": result[:1000] if isinstance(result, str) else str(result)[:1000],
            },
            step_index=step_index,
        )

        return result

    async def _execute_subagent(
        self,
        template: SubAgentTemplate,
        task: str,
        context: str,
    ) -> str:
        """Create a temporary sub-agent, execute the task, and clean up resources."""

        # 1. Create temporary UE MCP connection (independent tool_filter)
        allowed_ue = set(template.allowed_ue_tools)
        temp_mcp_server = MCPServerStreamableHttp(
            params=MCPServerStreamableHttpParams(
                url=self.main_agent.settings.ue_mcp_server_url,
            ),
            tool_filter=lambda ctx, tool: tool.name in allowed_ue,
            client_session_timeout_seconds=300,
        )

        mcp_servers = []
        try:
            await temp_mcp_server.connect()
            mcp_servers.append(temp_mcp_server)

            # 2. Wrap external tools (if template needs them)
            extra_tools: list[FunctionTool] = []
            if template.allowed_external_tools:
                extra_tools = await self._wrap_external_tools(template.allowed_external_tools)

            # 3. Select model
            model = self._resolve_model(template)

            # 4. Create temporary Agent
            agent = Agent(
                model=model,
                name=f"SubAgent_{template.name}",
                mcp_servers=mcp_servers,
                tools=extra_tools,
                instructions=template.instructions,
                tool_use_behavior="stop_on_first_tool",
            )

            # 5. Build input
            input_messages = self._build_input(template, task, context)

            # 6. Execute sub-agent loop
            runner = Runner()
            conversation = input_messages.copy()
            tool_calls_log: list[dict] = []
            final_message = ""
            turns = 0

            while turns < template.max_turns:
                turns += 1
                result = await runner.run(
                    starting_agent=agent,
                    input=conversation,
                    max_turns=999,
                )

                has_message = False
                has_tool_call = False

                for item in result.new_items:
                    if item.type == "tool_call_item":
                        has_tool_call = True
                        tool_calls_log.append({
                            "tool_name": item.raw_item.name,
                            "arguments": item.raw_item.arguments,
                            "call_id": getattr(item.raw_item, "id", ""),
                        })
                    elif item.type == "tool_call_output_item":
                        pass  # tracked implicitly
                    elif item.type == "message_output_item":
                        has_message = True
                        try:
                            final_message = item.raw_item.content[0].text
                        except (IndexError, AttributeError):
                            final_message = str(item.raw_item.content)

                # Extend conversation with new items
                conversation.extend(
                    [item.to_input_item() for item in result.new_items]
                )

                if has_message and not has_tool_call:
                    break

            # 7. Generate result summary
            return json.dumps({
                "status": "success",
                "template_name": template.name,
                "tool_calls_count": len(tool_calls_log),
                "tool_calls": tool_calls_log,
                "result_summary": final_message,
                "turns_used": turns,
            }, ensure_ascii=False)

        finally:
            # 8. Clean up temporary MCP connection
            if temp_mcp_server is not None:
                try:
                    await temp_mcp_server.cleanup()
                except Exception as cleanup_err:
                    print(f"[SubAgentRunner] Warning: MCP cleanup error: {cleanup_err}")

    async def _execute_photographer_subagent(
        self,
        template: SubAgentTemplate,
        task: str,
        context: str,
    ) -> str:
        """Execute the photographer sub-agent."""

        photographer_settings = PhotographerAgentSettings(
            base_url=self.main_agent.settings.base_url,
            api_key=self.main_agent.settings.api_key,
            model_name=template.model_override or self.main_agent.settings.model_name,
            api_type=self.main_agent.settings.api_type,
            ue_mcp_url=self.main_agent.settings.ue_mcp_server_url,
            image_history_k=5,
            image_resolution=[1280, 720],
            image_message_role="user",
            auto_managed_message_role=self.main_agent.settings.auto_managed_message_role,
        )
        photographer = PhotographerAgent(
            photographer_settings,
            instructions=template.instructions,
            max_turns=template.max_turns,
        )
        try:
            await photographer.initialize()
            result = await photographer.run(task, context=context)
            result["template_name"] = template.name
            return json.dumps(result, ensure_ascii=False)
        finally:
            try:
                await photographer.cleanup()
            except Exception as cleanup_err:
                print(f"[SubAgentRunner] Warning: MCP cleanup error: {cleanup_err}")

    def _build_input(
        self,
        template: SubAgentTemplate,
        task: str,
        context: str,
    ) -> list[dict]:
        """Build input messages for the sub-agent."""
        messages = []

        # Inject cutscene content (if available and template requires it)
        if template.inject_cutscene_content and context:
            messages.append({
                "role": self.main_agent.settings.auto_managed_message_role,
                "content": [{
                    "type": "input_text",
                    "text": f"<current_context>\n{context}\n</current_context>",
                }]
            })

        # User task
        messages.append({
            "role": "user",
            "content": task,
        })

        return messages

    async def _wrap_external_tools(
        self,
        tool_names: list[str],
    ) -> list[FunctionTool]:
        """Wrap external MCP tools as FunctionTool, reusing the main Agent's MCP connection."""
        wrapped = []
        server = self.main_agent.mcp_server_external_tools

        # Get available tool list from server
        available_tools = await server.list_tools()
        tool_map = {t.name: t for t in available_tools}

        for name in tool_names:
            tool_info = tool_map.get(name)
            if tool_info is None:
                print(f"[SubAgentRunner] Warning: external tool '{name}' not found, skipping.")
                continue

            # Build FunctionTool wrapper
            captured_name = name
            captured_server = server

            async def invoke_wrapper(ctx, args_json: str, _name=captured_name, _server=captured_server):
                args = json.loads(args_json) if args_json else {}
                result = await _server.call_tool(_name, args)
                if result.isError:
                    return result.content[0].text if result.content else "Tool error"
                return result.content[0].text if result.content else ""

            ft = FunctionTool(
                name=tool_info.name,
                description=tool_info.description or "",
                params_json_schema=tool_info.inputSchema or {"type": "object", "properties": {}},
                on_invoke_tool=invoke_wrapper,
                strict_json_schema=False,
            )
            wrapped.append(ft)

        return wrapped
