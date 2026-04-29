import os
import sys
import time
import asyncio
import pprint
import json
import datetime
import traceback
import agents
from agents.exceptions import ModelBehaviorError
import openai
import openai.types.responses
import dataclasses
import random
from enum import Enum
from typing import AsyncGenerator, Any
from openai import AsyncOpenAI
from agents import Agent, Runner, set_trace_processors
from agents.models.openai_chatcompletions import OpenAIChatCompletionsModel
from agents.models.openai_responses import OpenAIResponsesModel
from agents.run import CallModelData, ModelInputData, RunConfig
from agents.model_settings import ModelSettings
from agents.mcp import (
    MCPServer,
    MCPServerStdio,
    MCPServerStdioParams,
    MCPServerStreamableHttp,
    MCPServerStreamableHttpParams,
)
from agents import StreamEvent
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from pydantic import BaseModel, Field
from prompt import PromptManager
from prompt.templates.common import (
    get_identity_instruction,
    get_safety_instruction,
    get_formatting_instruction,
)

from prompt.templates.cutscene import (
    get_director_instruction,
    get_cutscene_rules,
    get_subagent_delegation_instruction,
)
from core.session_recorder import SessionRecorder, to_jsonable
from core.subagent_runner import (
    SubAgentRunner,
    _build_scene_specialist_template,
    _build_animation_specialist_template,
    _build_photographer_template,
)

set_trace_processors([])  # disable OpenAI tracing

# Query tools return asset catalogs / read-only information.
# The compression strategy retains the most recent invocation of each query tool.
QUERY_TOOLS = frozenset({
    "get_sequence_content",
    "get_available_characters",
    "get_available_animations",
    "get_available_tone",
    "get_available_camera_templates",
    "get_queryable_asset_kinds",
    "get_query_instruction",
    "query_assets",
    "get_importable_asset_types",
    "get_import_guide",
})


class CutsceneAgentSettings(BaseModel):
    base_url: str
    api_key: str
    model_name: str

    ue_mcp_server_url: str

    api_type: str = Field(
        "chat_completions",
        description="API type: 'chat_completions' or 'responses'",
    )

    # developer/system/user, some models may not support developer role
    auto_managed_message_role: str = Field(
        "developer", description="Role of auto-managed messages"
    )
    toolcall_history_length: int = Field(
        10,
        description="Number of recent tool calls to keep in full detail, older ones may be compressed. Value<=0 means no compression.",
    )

    debug_response: bool = False


class EventType(str, Enum):
    """Agent event types."""

    INITIALIZE = "initialize"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    REASONING = "reasoning"
    MESSAGE = "message"
    IDLE = "idle"
    ERROR = "error"


class UpstreamRateLimitError(RuntimeError):
    def __init__(self, message: str, raw_error: dict | None = None):
        super().__init__(message)
        self.raw_error = raw_error or {}


class SafeOpenAIStreamWrapper:
    """Wraps OpenAI stream to catch and report malformed chunks (e.g. lists instead of objects)."""

    def __init__(self, stream):
        self.stream = stream

    def __aiter__(self):
        self._iterator = self.stream.__aiter__()
        return self

    async def __anext__(self):
        chunk = await self._iterator.__anext__()

    # Vertex/some proxy layers may wrap error chunks as lists
        if isinstance(chunk, list) and len(chunk) > 0:
            c0 = chunk[0]

            # Compat: object has .error attribute
            err = getattr(c0, "error", None)
            if isinstance(err, dict) and err.get("code") == 429:
                raise UpstreamRateLimitError(
                    f"Upstream rate limited (429): {err.get('message', '')}",
                    raw_error=err,
                )

            # If still a list but not a recognized 429, treat as protocol error (preserve info)
            raise RuntimeError(f"Unexpected list chunk from LLM stream: {chunk}")

        # Compat: not a list, but chunk itself carries error
        err = getattr(chunk, "error", None)
        if isinstance(err, dict) and err.get("code") == 429:
            raise UpstreamRateLimitError(
                f"Upstream rate limited (429): {err.get('message', '')}",
                raw_error=err,
            )

        return chunk

    async def __aenter__(self):
        if hasattr(self.stream, "__aenter__"):
            await self.stream.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if hasattr(self.stream, "__aexit__"):
            await self.stream.__aexit__(exc_type, exc_val, exc_tb)

    def __getattr__(self, name):
        return getattr(self.stream, name)


class CutsceneAgent:
    def __init__(
        self,
        settings: CutsceneAgentSettings,
        session_name: str | None = None,
        base_dir: str | os.PathLike = "data/autosave",
    ):
        self.settings = settings
        self.session_name = session_name
        self.base_dir = base_dir

    async def initialize(self) -> AsyncGenerator[dict, None]:
        yield {
            "type": EventType.INITIALIZE,
            "content": "Initializing Cutscene Agent...",
        }

        self.model_client = AsyncOpenAI(
            base_url=self.settings.base_url, api_key=self.settings.api_key
        )

        if self.settings.api_type == "responses":
            self.model = OpenAIResponsesModel(
                openai_client=self.model_client,
                model=self.settings.model_name,
            )
        else:
            # Monkey-patch create to wrap the stream for better error reporting
            original_create = self.model_client.chat.completions.create

            async def wrapped_create(*args, **kwargs):
                response = await original_create(*args, **kwargs)
                # If it's a stream (AsyncStream or has __aiter__), wrap it
                if hasattr(response, "__aiter__"):
                    return SafeOpenAIStreamWrapper(response)
                if self.settings.debug_response:
                    print("Non-stream raw response:", response)
                return response

            self.model_client.chat.completions.create = wrapped_create

            self.model = OpenAIChatCompletionsModel(
                openai_client=self.model_client,
                model=self.settings.model_name,
            )

        await self._init_mcp_servers()
        yield {
            "type": EventType.INITIALIZE,
            "content": "Connected to MCP servers.",
        }

        await self._init_prompt_manager()
        yield {
            "type": EventType.INITIALIZE,
            "content": "Prompt manager initialized.",
        }

        self._init_subagent_system()
        yield {
            "type": EventType.INITIALIZE,
            "content": "Sub-agent system initialized.",
        }

        self.agent = Agent(
            model=self.model,
            name="CutsceneAgent",
            mcp_servers=self.mcp_servers,
            tools=[self._subagent_tool],
            instructions=self.prompt_manager.render_system_prompt(max_tokens=100000),
            tool_use_behavior="stop_on_first_tool",
        )
        # -----------------------
        print("-" * 50)
        print("Final System Prompt (Instructions):")
        print(self.agent.instructions)
        print("-" * 50)
        # -----------------------
        self.runner = Runner()

        self.conversation: list[dict] = []
        self._step_counter = 0

        # Initialize session recorder
        self.recorder = SessionRecorder(
            base_dir=self.base_dir,
            settings=self.settings,
            session_name=self.session_name,
        )
        print(f"[SessionRecorder] Session dir: {self.recorder.session_dir}")

        yield {
            "type": EventType.INITIALIZE,
            "content": "Cutscene Agent is ready.",
        }

    async def _init_mcp_servers(self):

        self.mcp_server_external_tools = MCPServerStdio(
            params=MCPServerStdioParams(
                command=sys.executable,
                args=[
                    "-m",
                    "mcp_servers.aigc_asset_tools",
                    "mcp",
                    "--ue-mcp-url",
                    self.settings.ue_mcp_server_url,
                ],
                env=dict(os.environ),
                cwd=os.getcwd(),
            ),
            tool_filter=self._context_aware_tool_filter,
            client_session_timeout_seconds=300,
        )
        await self.mcp_server_external_tools.connect()

        self.mcp_server_ue = MCPServerStreamableHttp(
            params=MCPServerStreamableHttpParams(
                url=self.settings.ue_mcp_server_url,
            ),
            tool_filter=self._context_aware_tool_filter,
            client_session_timeout_seconds=300,
        )
        await self.mcp_server_ue.connect()

        self.mcp_servers: list[MCPServer] = [
            self.mcp_server_external_tools,
            self.mcp_server_ue,
        ]

    async def _init_prompt_manager(self):
        self.prompt_manager = PromptManager(model_name=self.settings.model_name)
        self.prompt_manager.system_elements.append(
            get_identity_instruction(self.settings.model_name)
        )
        self.prompt_manager.system_elements.append(get_safety_instruction())
        self.prompt_manager.system_elements.append(get_director_instruction())

        cutscene_rules = get_cutscene_rules()
        for rule in cutscene_rules:
            self.prompt_manager.system_elements.append(rule)

    def _init_subagent_system(self):
        """Initialize sub-agent delegation system: register templates, create FunctionTool."""
        from agents import FunctionTool

        self._subagent_runner = SubAgentRunner(main_agent=self)

        # Register preset templates
        scene_template = _build_scene_specialist_template()
        animation_template = _build_animation_specialist_template()
        photographer_template = _build_photographer_template()
        self._subagent_runner.register_template(scene_template)
        self._subagent_runner.register_template(animation_template)
        self._subagent_runner.register_template(photographer_template)

        # Inject sub-agent delegation instruction into prompt
        templates_desc = self._subagent_runner.get_templates_description()
        delegation_instruction = get_subagent_delegation_instruction(templates_desc)
        self.prompt_manager.system_elements.append(delegation_instruction)

        # Build run_subagent FunctionTool
        templates_description_for_tool = (
            f"Delegate a sub-task to a specialized sub-agent. "
            f"Available templates: {', '.join(self._subagent_runner.templates.keys())}, custom. "
            f"The sub-agent will execute the task using its own set of tools and return a JSON summary."
        )

        async def _on_invoke_subagent(ctx, args_json: str) -> str:
            args = json.loads(args_json)
            return await self._subagent_runner.run(
                template_name=args.get("template_name", ""),
                task=args.get("task", ""),
                context=args.get("context", ""),
                custom_instructions=args.get("custom_instructions", ""),
                custom_tool_scope=args.get("custom_tool_scope"),
            )

        self._subagent_tool = FunctionTool(
            name="run_subagent",
            description=templates_description_for_tool,
            params_json_schema={
                "type": "object",
                "properties": {
                    "template_name": {
                        "type": "string",
                        "description": (
                            "Sub-agent template name. Options: "
                            + ", ".join(
                                [
                                    f"'{n}' ({t.description})"
                                    for n, t in self._subagent_runner.templates.items()
                                ]
                            )
                            + ", 'custom' (provide custom_instructions and custom_tool_scope)"
                        ),
                    },
                    "task": {
                        "type": "string",
                        "description": "Detailed task description for the sub-agent. Be specific about what to accomplish.",
                    },
                    "context": {
                        "type": "string",
                        "description": "Optional context information (e.g. current characters, timeline state, script content).",
                    },
                    "custom_instructions": {
                        "type": "string",
                        "description": "System instructions for custom sub-agent (only used when template_name='custom').",
                    },
                    "custom_tool_scope": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of tool names the custom sub-agent can use (only used when template_name='custom').",
                    },
                },
                "required": ["template_name", "task"],
                "additionalProperties": False,
            },
            on_invoke_tool=_on_invoke_subagent,
            strict_json_schema=False,
        )

        print(
            f"[SubAgent] Registered templates: {list(self._subagent_runner.templates.keys())}"
        )

    def _context_aware_tool_filter(self, context, tool) -> bool:
        if tool.name in ("take_editor_screenshot", "take_camera_screenshot"):
            # Skip screenshot tools for main agent (used by photographer sub-agent)
            return False
        if tool.name == "clear_sequence":
            return False
        # if tool.name == "get_sequence_content":
        #     return False
        return True

    def _process_event(self, event: StreamEvent) -> dict | None:
        """Process stream events and convert to EventType dict.

        Event recording is handled by the SessionRecorder in core_run_step.
        """

        if event.type == "run_item_stream_event":
            run_item_event: agents.RunItemStreamEvent = event

            if run_item_event.item.type == "message_output_item":
                message_output_item: agents.items.MessageOutputItem = (
                    run_item_event.item
                )
                return {
                    "type": EventType.MESSAGE,
                    "content": message_output_item.raw_item.content[0].text,
                    "_raw_item": message_output_item.raw_item,
                }
            elif run_item_event.item.type == "tool_call_item":
                tool_call_item: agents.items.ToolCallItem = run_item_event.item
                return {
                    "type": EventType.TOOL_CALL,
                    "content": {
                        "tool_name": tool_call_item.raw_item.name,
                        "tool_args": tool_call_item.raw_item.arguments,
                        "call_id": tool_call_item.raw_item.id,
                    },
                    "_raw_item": tool_call_item.raw_item,
                }
            elif run_item_event.item.type == "tool_call_output_item":
                tool_call_output_item: agents.items.ToolCallOutputItem = (
                    run_item_event.item
                )
                return {
                    "type": EventType.TOOL_RESULT,
                    "content": {
                        "tool_result": tool_call_output_item.raw_item["output"],
                        "call_id": tool_call_output_item.raw_item["call_id"],
                    },
                    "_raw_item": tool_call_output_item.raw_item,
                }
            elif run_item_event.item.type == "reasoning_item":
                reasoning_item: agents.items.ReasoningItem = run_item_event.item
                try:
                    reasoning_content = reasoning_item.raw_item.content[0].text
                except Exception:
                    reasoning_content = str(reasoning_item.raw_item.content)
                return {
                    "type": EventType.REASONING,
                    "content": reasoning_content,
                    "_raw_item": reasoning_item.raw_item,
                }

        return None


    async def core_run_step(self, user_input: list[dict], max_substeps: int=None) -> AsyncGenerator[dict, None]:
        old_conversation = await self._process_old_conversation(self.conversation)
        current_turn_conversation = []

        self._step_counter += 1
        step_index = self._step_counter
        substep_index = 0

        while True:

            if max_substeps is not None and substep_index >= max_substeps:
                break
            substep_index += 1

            substep_input = await self._prepare_input(
                old_conversation, user_input, current_turn_conversation
            )

            # Record substep begin
            self.recorder.begin_substep(
                step_index=step_index,
                substep_index=substep_index,
                system_prompt=self.agent.instructions,
                input_messages=substep_input,
                user_input=user_input,
            )

            # Retry parameters
            max_retries = 5
            attempt = 0
            run_config = RunConfig()
            model_settings = ModelSettings(
                max_tokens=4096,
            )
            run_config.model_settings = model_settings

            runner_result = None
            try:
                while True:
                    saw_tool_call_in_this_attempt = False
                    try:
                        runner_result = self.runner.run_streamed(
                            starting_agent=self.agent,
                            input=substep_input,
                            max_turns=999,
                            run_config=run_config,
                        )
                        async for event in runner_result.stream_events():
                            event_processed = self._process_event(event)
                            if event_processed is not None:
                                # Record event to session recorder
                                raw_item = event_processed.pop("_raw_item", None)
                                self.recorder.record_event(
                                    event_type=event_processed["type"].value,
                                    payload=raw_item,
                                    step_index=step_index,
                                    substep_index=substep_index,
                                )
                                # Track whether a tool call was made in this attempt
                                if event_processed["type"] == EventType.TOOL_CALL:
                                    saw_tool_call_in_this_attempt = True
                                yield event_processed

                        break  # Stream ended normally, exit retry loop

                    except ModelBehaviorError as e:
                        # Tool call format error (e.g. Invalid JSON) — no side effects, safe to retry
                        if attempt >= max_retries:
                            raise

                        backoff = min(10.0, (2**attempt)) + random.random()
                        print(
                            f"[ModelBehaviorError] {e}. Retry in {backoff:.2f}s (attempt {attempt+1}/{max_retries})"
                        )
                        self.recorder.record_event(
                            event_type="model_behavior_error",
                            payload={
                                "error": str(e),
                                "attempt": attempt + 1,
                                "max_retries": max_retries,
                                "backoff": round(backoff, 2),
                                "saw_tool_call": saw_tool_call_in_this_attempt,
                            },
                            step_index=step_index,
                            substep_index=substep_index,
                        )
                        await asyncio.sleep(backoff)
                        attempt += 1
                        continue

                    except UpstreamRateLimitError as e:
                        # If a tool call was already made, don't auto-retry to avoid duplicate side effects
                        if saw_tool_call_in_this_attempt:
                            raise

                        if attempt >= max_retries:
                            raise

                        # Exponential backoff + jitter
                        backoff = min(30.0, (2**attempt)) + random.random()
                        print(
                            f"[RateLimit] {e}. Retry in {backoff:.2f}s (attempt {attempt+1}/{max_retries})"
                        )
                        await asyncio.sleep(backoff)
                        attempt += 1
                        continue

            except Exception as e:
                # Record the failed substep with error info, then re-raise
                self.recorder.end_substep_with_error(
                    error=e,
                    partial_items=(
                        runner_result.new_items if runner_result is not None else None
                    ),
                )
                raise

            new_items = runner_result.new_items

            # Record substep end
            self.recorder.end_substep(new_items=new_items)

            has_message = any(item.type == "message_output_item" for item in new_items)
            has_tool_call = any(item.type == "tool_call_item" for item in new_items)

            current_turn_conversation = await self._process_and_concat_response(
                current_turn_conversation, new_items
            )

            if has_message and not has_tool_call:
                self.conversation = await self._process_step_result(
                    old_conversation, user_input, current_turn_conversation
                )
                # Save conversation snapshot after each step
                self.recorder.save_conversation(self.conversation)
                break

            await asyncio.sleep(3)

    async def _prepare_input(
        self,
        old_conversation: list[dict],
        user_input: list[dict],
        current_turn_conversation: list[agents.items.TResponseInputItem],
    ):

        conversation = old_conversation.copy()
        conversation.extend(user_input)

        conversation.extend(current_turn_conversation)

        # Auto-inject current sequence content
        try:
            current_cutscene_content = None
            res = await self.mcp_server_ue.call_tool(
                tool_name="get_sequence_content", arguments={}
            )
            if res.isError:
                print(f"Error retrieving sequence content: {res.content}")
                pass
            else:
                current_cutscene_content = res.content[0].text
        except Exception as e:
            print(f"Error calling get_sequence_content: {e}")

        if current_cutscene_content:
            current_cutscene_content_text = f"<current_cutscene_content>\n  (This block is automatically retrieved and sent by the system) Contents in current cutscene:\n ```{current_cutscene_content}```   \n</current_cutscene_content>"
            conversation.append(
                {
                    "role": self.settings.auto_managed_message_role,
                    "content": [
                        {
                            "type": "input_text",
                            "text": current_cutscene_content_text,
                        }
                    ],
                }
            )

        return conversation

    async def _process_old_conversation(self, old_conversation: list[dict]):
        result_conversation = []
        # current implementation: simply return old conversation

        return old_conversation

    async def _process_and_concat_response(
        self, conversation: list[dict], new_items: list[agents.items.RunItem]
    ):

        # TODO: convert tool image output to input_image type
        conversation.extend([item.to_input_item() for item in new_items])
        # print(f"Current conversation: {pprint.pformat(conversation)}")

        # Category-aware tool call history compression
        # - Mutation tools: compressed first (effects captured by auto-injected cutscene state)
        # - Query tools: retain the most recent invocation of each unique query tool
        # - N most recent tool calls are always kept in full detail
        toolcall_history_length = self.settings.toolcall_history_length
        if toolcall_history_length > 0:
            tool_calls = []
            summary_msg_idx = -1
            existing_summary_names = []

            for i, item in enumerate(conversation):
                # Check if a summary message exists
                content = item.get("content")
                if (isinstance(content, str) and "<tool_call_summary>" in content) or (
                    isinstance(content, dict)
                    and content.get("type") in ("text", "input_text")
                    and "<tool_call_summary>" in content.get("text", "")
                ):
                    summary_msg_idx = i
                    try:
                        start = content.find("<tool_call_summary>") + len(
                            "<tool_call_summary>"
                        )
                        end = content.find("</tool_call_summary>")
                        if start > -1 and end > -1:
                            existing_summary_names = [
                                x.strip()
                                for x in content[start:end].split("\n")
                                if x.strip()
                            ]
                    except Exception:
                        pass

                # Also check list-typed content (our summary_item uses a list)
                if isinstance(content, list):
                    for block in content:
                        if (
                            isinstance(block, dict)
                            and block.get("type") in ("text", "input_text")
                            and "<tool_call_summary>" in block.get("text", "")
                        ):
                            summary_msg_idx = i
                            try:
                                text = block["text"]
                                start = text.find("<tool_call_summary>") + len(
                                    "<tool_call_summary>"
                                )
                                end = text.find("</tool_call_summary>")
                                if start > -1 and end > -1:
                                    existing_summary_names = [
                                        x.strip()
                                        for x in text[start:end].split("\n")
                                        if x.strip()
                                    ]
                            except Exception:
                                pass
                            break

                # Collect tool calls (ordered chronologically)
                if item.get("type") == "function_call":
                    tool_calls.append(item)

            if len(tool_calls) > toolcall_history_length:
                # Split into candidates for compression vs. unconditionally kept
                compress_candidates = tool_calls[:-toolcall_history_length]
                recent_kept = tool_calls[-toolcall_history_length:]

                # Query tools already represented in the recent-kept portion
                query_names_in_recent = {
                    c["name"] for c in recent_kept if c["name"] in QUERY_TOOLS
                }

                # Among compress candidates, protect the most recent call of each
                # query tool that has NO representative in recent_kept.
                # Iterating forward: later entries overwrite earlier ones -> keeps latest.
                latest_query_ids: dict[str, str] = {}
                for c in compress_candidates:
                    if (
                        c["name"] in QUERY_TOOLS
                        and c["name"] not in query_names_in_recent
                    ):
                        latest_query_ids[c["name"]] = c["call_id"]

                protected_ids = set(latest_query_ids.values())

                # Actually compress = candidates minus protected query calls
                calls_to_compress = [
                    c
                    for c in compress_candidates
                    if c["call_id"] not in protected_ids
                ]

                if not calls_to_compress:
                    return conversation

                new_names = [c["name"] for c in calls_to_compress]
                print(
                    f"Compressing {len(calls_to_compress)} tool calls "
                    f"(protected {len(protected_ids)} query tools): {new_names}"
                )
                ids_to_remove = set(c["call_id"] for c in calls_to_compress)

                final_summary_names = existing_summary_names + new_names
                summary_content_text = (
                    "<tool_call_summary>\n"
                    + "\n".join(final_summary_names)
                    + "\n</tool_call_summary>"
                )

                summary_item = {
                    "role": self.settings.auto_managed_message_role,
                    "content": [{"type": "input_text", "text": summary_content_text}],
                }

                new_conversation = []
                summary_inserted = False

                for i, item in enumerate(conversation):
                    # If this is an old summary, skip it (will be reinserted at the right position)
                    if i == summary_msg_idx:
                        if not summary_inserted:
                            new_conversation.append(summary_item)
                            summary_inserted = True
                        continue

                    # If this is a compressed tool call or its output, skip it
                    is_removed = False
                    if item.get("type") in ["function_call", "function_call_output"]:
                        if item.get("call_id") in ids_to_remove:
                            is_removed = True

                    if is_removed:
                        if not summary_inserted:
                            new_conversation.append(summary_item)
                            summary_inserted = True
                        continue

                    new_conversation.append(item)

                if not summary_inserted:
                    new_conversation.insert(0, summary_item)

                conversation = new_conversation

        return conversation

    async def _process_step_result(
        self,
        old_conversation: list[dict],
        user_input: list[dict],
        current_responses: list[dict],
    ):
        # current implementation: simply return old conversation extended with user input and current responses
        conversation = old_conversation.copy()
        conversation.extend(user_input)
        conversation.extend(current_responses)
        return conversation

    async def run_cli_loop(self):
        print("Cutscene Agent CLI. Type 'exit' to quit.")

        try:
            while True:
                is_idle = True
                user_input = input("You: ")
                if user_input.lower() in ["exit", "quit"]:
                    await self.save_session_record(
                        exit_reason={
                            "type": "user_exit",
                        }
                    )
                    break
                is_idle = False

                user_message = {"role": "user", "content": user_input}
                async for event in self.core_run_step([user_message]):
                    if event is None:
                        continue
                    if event["type"] == EventType.MESSAGE:
                        print(f"[Agent Message] {event['content']}")
                    elif event["type"] == EventType.TOOL_CALL:
                        print(
                            f"[Tool Call] {event['content']['tool_name']} with args {event['content']['tool_args']}"
                        )
                    elif event["type"] == EventType.TOOL_RESULT:
                        print(f"[Tool Result] {event['content']}")
                    elif event["type"] == EventType.REASONING:
                        print(f"[Reasoning] {event['content']}")
        except (KeyboardInterrupt, asyncio.CancelledError):
            print(
                "Keyboard interrupt received. Please wait while we save the session record..."
            )
            await self.save_session_record(
                exit_reason={
                    "type": "Ctrl C",
                    "is_idle": is_idle,
                    "traceback": traceback.format_exc(),
                }
            )
        except Exception as e:
            await self.save_session_record(
                exit_reason={
                    "type": "Exception",
                    "exception_type": type(e).__name__,
                    "message": str(e),
                    "traceback": traceback.format_exc(),
                }
            )

    async def save_session_record(self, exit_reason: Any = None):
        """Finalize the current session recorder and save conversation."""

        # Get the final cutscene content
        try:

            async with streamablehttp_client(self.settings.ue_mcp_server_url) as (
                read,
                write,
                _,
            ):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    res = await session.call_tool("get_sequence_content", arguments={})
                    if not getattr(res, "isError", False) and res.content:
                        final_content = res.content[0].text
                        final_content_path = (
                            self.recorder.session_dir / "final_content.json"
                        )
                with open(final_content_path, "w", encoding="utf-8") as f:
                    # Try to parse the returned string as JSON, fallback to storing as-is
                    try:
                        content_json = json.loads(final_content)
                        json.dump(content_json, f, ensure_ascii=False, indent=2)
                    except json.JSONDecodeError:
                        json.dump(
                            {"final_content": final_content},
                            f,
                            ensure_ascii=False,
                            indent=2,
                        )
                print(
                    f"[SessionRecorder] Final cutscene content saved to: {final_content_path}"
                )
        except Exception as e:
            print(f"Error fetching final sequence content: {e}")

        self.recorder.save_conversation(self.conversation)
        session_dir = self.recorder.finalize(exit_reason=exit_reason)
        print(f"[SessionRecorder] Session saved to: {session_dir}")
        return session_dir

    async def clear_conversation_and_record(self):
        """Finalize the current session and start a new one."""
        # Finalize current recorder if it has content
        if self._step_counter > 0:
            await self.save_session_record(exit_reason={"type": "conversation_cleared"})

        # Reset state
        self.conversation = []
        self._step_counter = 0

        # Create a fresh recorder for the new session
        self.recorder = SessionRecorder(
            base_dir=self.base_dir,
            settings=self.settings,
            session_name=self.session_name,
        )
        print(f"[SessionRecorder] New session dir: {self.recorder.session_dir}")

    async def close(self):
        for server in self.mcp_servers:
            try:
                await server.cleanup()
            except (Exception, asyncio.CancelledError) as e:
                print(f"[CutsceneAgent] Warning: error during MCP server cleanup: {e}")
