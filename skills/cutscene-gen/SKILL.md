---
name: cutscene-gen
description: Use when an agent needs to create, edit, inspect, or debug Unreal Engine cutscenes through CutsceneProvider MCP tools from a script or natural-language direction. Applies to Codex, Claude Code, opencode, Copilot-like agents, or any bot controlling a UE Level Sequence through MCP. Covers asset discovery, character staging, dialogue/audio import, animation choreography, camera setup, viewport checks, and sequence verification.
---

# Cutscene Gen

Turn a user's script or natural-language direction into small, verified CutsceneProvider MCP tool calls that modify the active Unreal Engine Level Sequence.

This skill is the generation companion to `install_cutscene_agent`: assume setup is complete or verify it quickly before editing the sequence.

## Operating Contract

1. Treat the active Level Sequence as the source of truth.
2. Query before use; never invent asset identifiers.
3. Inspect tool schemas before calling unfamiliar tools.
4. Make dependent tool calls sequentially.
5. Verify every mutation with `get_sequence_content`.
6. Preserve existing sequence content unless the user asks to clear or replace it.
7. If a tool fails, read the error, inspect current state, and retry with a smaller operation.

## First Checks

Before generating content, confirm:

- CutsceneProvider MCP is reachable at the configured URL, usually `http://localhost:8100/mcp`.
- `list_tools` includes core tools such as `get_sequence_content`, `get_available_characters`, `add_character`, `add_camera`, and `set_active_camera`.
- A Level Sequence is open or selected in the CutsceneProvider panel. For the demo project, expect `/Game/AIGC_sequence`.
- `get_sequence_content` returns JSON. If it says no sequence is open, ask the user to open the sequence or use the project setup command from [demo.md](references/demo.md).

## Workflow

Use [workflow.md](references/workflow.md) for the complete phase order. The short version:

1. Parse the user's request into shots, characters, dialogue, actions, timing, and camera intent.
2. Call `get_sequence_content` to inspect the current sequence.
3. Query assets:
   - `get_queryable_asset_kinds`
   - `get_query_instruction`
   - `query_assets`
   - shortcut tools such as `get_available_characters`, `get_available_animations`, `get_available_camera_templates`
4. Add or reuse characters, then orient them as a group.
5. Add dialogue audio and facial expressions only when the AIGC tools are configured; otherwise skip or use already-provided assets.
6. Add body animations using queried animation identifiers.
7. Add cameras, templates, camera cuts, and optional camera movement.
8. Verify the final sequence with `get_sequence_content`; repair overlaps, gaps, duplicate cuts, or missing bindings.

## Tool Families

Read [tools.md](references/tools.md) when deciding exact MCP calls.

- **State**: `get_sequence_content`, `clear_sequence`, `save_sequence_as`
- **Assets**: `get_queryable_asset_kinds`, `get_query_instruction`, `query_assets`, `get_available_*`
- **Characters**: `add_character`, `orient_character_to_center`
- **Audio/face**: `tts_function`, `audio_to_face_expression`, `push_file_to_ue`, `import_dynamic_asset`, `add_character_audio`, `add_character_facial_animation`
- **Animation**: `get_available_animations`, `add_character_animation`
- **Camera**: `add_camera`, `get_available_camera_templates`, `apply_camera_template`, `set_active_camera`
- **Viewport**: `take_editor_screenshot`, `take_camera_screenshot`, `move_view`, `undo_move_view`

## Demo Defaults

For the official demo project:

- Working sequence: `/Game/AIGC_sequence`
- MCP endpoint: `http://localhost:8100/mcp`
- A plain request to "make a demo" uses the bundled offline Mannequin,
  `standing_greeting` animation, and `sample_audio` voice asset.
- Do not assume assets are present until asset queries return them.
- The first verified natural-language operation was: create `Agent_Demo_Camera`, set it active from `0.0` to `5.0`, then verify via `get_sequence_content`.

Use [demo.md](references/demo.md) for setup-state assumptions and observed quirks.

## Reporting

Keep user updates concise:

- State the phase completed.
- Name the most important tools called.
- Report verified sequence changes.
- Mention blockers in terms of missing sequence, missing assets, missing MCP tools, or unconfigured AIGC services.

Do not claim a cutscene is complete until `get_sequence_content` proves the expected characters, audio/animation tracks, and camera cuts are present.
