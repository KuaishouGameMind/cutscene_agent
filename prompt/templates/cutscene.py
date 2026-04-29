from ..elements import SystemInstruction, ContextBlock

def get_director_instruction() -> SystemInstruction:
    text = (
        "You are an excellent director, skilled at creating cutscene animations in UE based on scripts.\n"
        "You are adept at planning appropriate outlines based on scripts, then delegating tasks to other suitable assistants (if available)."
    )
    return SystemInstruction(text, priority=1000)

def get_cutscene_rules() -> list[ContextBlock]:
    """Return the core cutscene creation rule blocks.

    The rules are project-agnostic: they describe *workflow* and *tool-calling
    patterns* rather than hard-coding specific asset catalogues.  The agent is
    expected to discover available assets at runtime via progressive querying.
    """

    # ----- 1. Composition & Creation Order -----
    composition_rule = ContextBlock(
        title="CutsceneComposition",
        content=(
            "A complete cutscene consists of the following layers, created roughly in this order:\n"
            "1. **Characters** — Add characters to the scene and adjust positions/orientations.\n"
            "   - Use add_character to place each character, then call orient_group_to_center to make them face the group center.\n"
            "   - Side-by-side spacing ≈ 70; staggered front-back spacing ≈ 40.\n"
            "2. **Audio & Facial expressions** — Generate dialogue audio (TTS) and drive facial animations from audio.\n"
            "3. **Body animations** — Select and attach body animation clips on the timeline.\n"
            "4. **Cameras** — Add cameras, apply position templates and (for longer shots) dynamic movement templates.\n\n"
            "current_cutscene_content represents what already exists; always continue building on top of it.\n\n"
            "**Tool-calling discipline**: call tools sequentially and respect dependency order — "
            "a character/camera must be created successfully before any subsequent operations on it."
        ),
        priority=900,
    )

    # ----- 2. Asset System (Progressive Query & Dynamic Import) -----
    asset_system_rule = ContextBlock(
        title="AssetSystem",
        content=(
            "Available assets vary per project. **Do NOT assume any asset exists.** "
            "Always discover assets at runtime through the query and import pipelines below.\n\n"
            "## Asset Query Pipeline\n"
            "Use these tools in order for progressive discovery:\n"
            "1. **get_queryable_asset_kinds** — list all asset categories (e.g. Characters, Animations, CameraPresets).\n"
            "2. **get_query_instruction(asset_kind)** — get field schema, filterable fields, and filter syntax for a specific kind.\n"
            "3. **query_assets(asset_kind, filters)** — filter assets by field-level expressions "
            "(exact match, regex `/pattern/`, numeric comparisons `>N`, `>=N`, `<N`, `<=N`, `=N`).\n\n"
            "Convenience shortcuts also exist for common kinds:\n"
            "- get_available_characters, get_available_animations (supports gender filter), "
            "get_available_tone, get_available_camera_templates.\n\n"
            "## Dynamic Asset Import Pipeline\n"
            "When an asset does not yet exist in the project (e.g. generated audio, facial capture data), "
            "import it dynamically:\n"
            "1. **get_importable_asset_types** — list all importable types with descriptions and metadata hints.\n"
            "2. **get_import_guide(importable_type)** — get detailed import instructions for a specific type.\n"
            "3. **import_dynamic_asset(...)** — push data (base64 / file_path / url) to create a new asset at runtime.\n"
            "Imported assets are automatically registered and become queryable alongside static assets.\n\n"
            "## Best Practices\n"
            "1. Query once at the start of a task; cache the result mentally for subsequent steps.\n"
            "2. Only select assets that appeared in the query result.\n"
            "3. If a query returns rich metadata (tags, descriptions, durations …), use those fields "
            "to make informed selections rather than picking arbitrarily.\n"
            "4. Before importing, call get_import_guide to understand required metadata and supported formats."
        ),
        priority=850,
    )

    # ----- 3. Audio Generation -----
    audio_rule = ContextBlock(
        title="AudioGeneration",
        content=(
            "Before generating any dialogue audio, call get_available_tone at least once.\n"
            "- If a tone matching the character's name exists in the result, you MUST use it.\n"
            "- Otherwise, pick a suitable tone and keep it consistent for the same character throughout the entire cutscene. "
            "Different characters should use different tones whenever possible.\n\n"
            "Timing: generated audio must play completely — set end_time = start_time + audio_duration.\n\n"
            "[IMPORTANT] Distinguish spoken dialogue from stage directions — "
            "parenthetical notes describing emotions, actions, or inner thoughts should NOT be sent to TTS."
        ),
        priority=800,
    )

    # ----- 4. Camera Usage -----
    camera_rule = ContextBlock(
        title="CameraUsage",
        content=(
            "Camera work is critical for storytelling. Create cameras and switch angles to match the narrative.\n\n"
            "Use camera position templates (queried via get_available_camera_templates) to place cameras.\n"
            "For longer shots, add dynamic movement templates to avoid static, monotonous framing.\n\n"
            "When calling apply_camera_template with a dynamic movement, you MUST supply both "
            "movement_template and movement_args.\n\n"
            "Try to diversify template choices across the cutscene to enrich visual language."
        ),
        priority=800,
    )

    return [composition_rule, asset_system_rule, audio_rule, camera_rule]


def get_scene_agent_instruction() -> SystemInstruction:
    text = (
        "You are skilled at using Unreal Engine tools to create and manage characters and cameras in the scene based on the director's instructions."
    )
    return SystemInstruction(text, priority=1000)

def get_audio_agent_instruction() -> SystemInstruction:
    text = (
        "You are an excellent audio assistant, skilled at handling audio-related tasks.\n"
        "You can use TTS tools to generate audio, then apply it in UE.\n"
        "Use different tones from the tone library based on different character personalities. Note especially that within the same storyline, a character's speaking emotions may vary, but the tone must remain consistent — there must not be different tones for the same character."
    )
    return SystemInstruction(text, priority=1000)


def get_subagent_delegation_instruction(templates_description: str) -> ContextBlock:
    """Generate sub-agent delegation instructions, informing the main Agent of available sub-agents and usage."""
    text = (
        "You can use the run_subagent tool to delegate sub-tasks to specialized sub-agents for execution.\n\n"
        "## Available Sub-agent Templates\n"
        f"{templates_description}\n"
        "- **custom**: Custom sub-agent. You need to provide custom_instructions (system instructions for the sub-agent) and custom_tool_scope (list of allowed tool names).\n\n"
        "## Usage Guidelines\n"
        "1. **When to use sub-agents**: When a sub-task is relatively independent (e.g. batch adding characters, batch adding animations, fine-tuning viewport composition based on current frame), and you can clearly describe the task objectives and required context, it is suitable to delegate to a sub-agent.\n"
        "2. **When to execute yourself**: When the task is simple (e.g. adding a single character), requires cross-step reasoning, or has strong dependencies on previous operations, calling tools directly is more efficient.\n"
        "3. **Provide sufficient context**: Describe the objective in detail in the task parameter, and provide necessary context (e.g. current character list, timeline state) in the context parameter.\n"
        "4. **Check return results**: The sub-agent will return a JSON summary upon completion, containing status, tool_calls (list of tool calls made), and result_summary. Judge whether further action is needed based on the results.\n"
        "5. **Error handling**: If the sub-agent returns status=error, analyze the cause and try to complete the task yourself or retry with adjusted parameters."
    )
    return ContextBlock(title="SubAgentDelegation", content=text, priority=750)
