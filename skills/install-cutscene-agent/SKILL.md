---
name: install-cutscene-agent
description: Set up and verify the Cutscene Agent ecosystem for an Unreal Engine project. Use when an agent needs to clone cutscene_agent and CutsceneProvider, install Python dependencies, enable and build the UE plugin, configure MCP clients or the Python CLI, open the demo sequence, start the MCP server, diagnose setup failures, and offer to generate the bundled offline demo as an end-to-end acceptance test.
---

# Install Cutscene Agent

Set up a working environment in which an AI agent can control an Unreal
Engine Level Sequence through CutsceneProvider MCP.

Read [setup.md](references/setup.md) for verified Windows and UE 5.6 commands.
Read [troubleshooting.md](references/troubleshooting.md) only when a step fails.

## Required Outcome

Do not report setup as complete until all of these are true:

1. `cutscene_agent` and `CutsceneProvider` are available locally.
2. The bundled project exists at
   `cutscene_agent/demo/UE_CSAgent_demo`, unless the user explicitly chooses
   another UE project.
3. CutsceneProvider is installed as `<UEProject>/Plugins/CutsceneProvider`.
4. The bundled asset table is copied from
   `demo/UE_CSAgent_demo/Setup/CutsceneAssets.xlsx` to
   `<UEProject>/Plugins/CutsceneProvider/Content/Data/CutsceneAssets.xlsx`.
5. `PythonScriptPlugin`, `ControlRig`, and `CutsceneProvider` are enabled.
6. The UE editor target builds successfully when compilation is required.
7. The CutsceneProvider panel starts the server at
   `http://localhost:8100/mcp`.
8. MCP initialization and `list_tools` succeed.
9. A Level Sequence is open and `get_sequence_content` returns JSON.
10. For the official demo, character, animation, and audio queries return the
   bundled demo identifiers.

## Workflow

1. Inspect the host OS, Python version, Unreal Engine version, project path,
   Git LFS availability, and existing repository paths.
2. Clone only missing repositories. Keep the plugin folder name exactly
   `CutsceneProvider`.
3. Install `cutscene_agent/requirements.txt` in an isolated Python
   environment when possible.
4. Use `cutscene_agent/demo/UE_CSAgent_demo` as the default project. Do not
   copy or regenerate ignored UE cache directories.
5. Install or link CutsceneProvider into the UE project's `Plugins` folder.
6. Copy the bundled `CutsceneAssets.xlsx` into the installed plugin's
   `Content/Data` directory.
7. Enable required plugins in the `.uproject`.
8. Build the editor target with UnrealBuildTool if the plugin has no
   compatible binaries.
9. Open the UE project and wait for plugin Python dependencies to install.
10. Open `Tools -> Cutscene Tools -> Open Cutscene Panel`, select/open the
   working sequence, and click `Start`.
11. Verify port `8100` and the MCP protocol. A plain HTTP response saying
   `Not Acceptable: Client must accept text/event-stream` still proves that
   the endpoint is responding.
12. Verify sequence and asset readiness with read-only MCP calls.
13. Ask the user whether to generate the bundled demo as an end-to-end
    validation. If accepted, run the post-setup demo procedure below.

## Post-Setup Demo Validation

After every successful setup, proactively ask:

> Setup is complete. Would you like me to generate the bundled offline demo
> in `/Game/AIGC_sequence` to verify character, audio, and animation control?

Do not silently skip this offer. If the user declines, report setup complete
without modifying the sequence.

If the user accepts:

1. Read
   [`../cutscene-gen/references/demo.md`](../cutscene-gen/references/demo.md).
2. Call `get_sequence_content` before editing.
3. If the sequence already contains bindings or tracks, do not clear or
   duplicate them automatically. Explain the existing state and ask whether
   to reset it or use another sequence.
4. Confirm these identifiers through asset queries:
   - `demo_mannequin`
   - `demo_standing_greeting`
   - `demo_sample_audio`
5. Execute the bundled demo sequentially:
   - `add_character`
   - `get_sequence_content`
   - `add_character_audio`
   - `get_sequence_content`
   - `add_character_animation`
   - `get_sequence_content`
6. Verify the final sequence contains:
   - binding `DemoMannequin`
   - `Base Audio Track` with `sample_audio`
   - `Base Animation Track` with `standing_greeting`
7. Report the verified result and ask the user to play the sequence in UE.

This acceptance test uses bundled offline assets and must not require TTS,
facial-animation, vision, or other online services.

## Configuration Choice

Choose one control surface:

- **Any MCP-capable agent**: connect directly to CutsceneProvider at
  `http://localhost:8100/mcp`, then use `cutscene-gen`.
- **Python CLI agent**: set `LLM_BASE_URL`, `LLM_API_KEY`,
  `LLM_MODEL_NAME`, and `UE_MCP_URL` in the process environment before
  running `python main.py`.

The current CLI reads process environment variables directly. Do not assume
that merely creating a `.env` file loads it.

## Safety

- Do not overwrite an existing UE project or unrelated plugin changes.
- Do not delete `Binaries`, `Intermediate`, generated assets, or registry
  files unless the user explicitly requests cleanup.
- Close Unreal Editor before rebuilding editor modules.
- Prefer a directory junction or symlink during local plugin development;
  copy or submodule installation is more appropriate for distribution.
- Never copy or commit UE-generated `Binaries`, `Intermediate`, `Saved`,
  `DerivedDataCache`, or `.vs` directories.
- Do not vendor the CutsceneProvider checkout into the bundled demo. Install
  or link it during setup.
- Make read-only MCP checks before modifying a sequence.

## Handoff

After setup and the optional demo validation, direct the agent to
[`../cutscene-gen/SKILL.md`](../cutscene-gen/SKILL.md) for further cutscene
creation. Report concrete paths, endpoint, sequence name, available demo
identifiers, demo validation status, and any optional services that remain
unconfigured.
