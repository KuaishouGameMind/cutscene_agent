# Demo Project Notes

Use this reference when working with the official demo project or while validating this skill.

## Expected Demo Defaults

- UE project: `UE_CSAgent_demo`
- Repository project path: `demo/UE_CSAgent_demo`
- Working Level Sequence asset: `/Game/AIGC_sequence`
- Object path: `/Script/LevelSequence.LevelSequence'/Game/AIGC_sequence.AIGC_sequence'`
- CutsceneProvider MCP endpoint: `http://localhost:8100/mcp`
- Server is started from: `Tools -> Cutscene Tools -> Open Cutscene Panel -> Start`

## Bundled One-Command Demo

When the user says "make a demo", "做一个 demo", or an equivalent request
without providing a new script, use the bundled offline assets:

- Character: `demo_mannequin`
- Animation: `demo_standing_greeting`
- Audio: `demo_sample_audio`
- Character binding name: `DemoMannequin`
- Character location: `[0.0, 0.0, 0.0]`
- Audio range: `0.0` to `1.944`
- Animation start: `0.0`

Do not skip discovery. First confirm these identifiers are returned by:

- `get_available_characters`
- `get_available_animations`
- `query_assets(asset_kind="Audio")`

Then execute sequentially:

```json
{"tool":"add_character","args":{"name":"DemoMannequin","identifier":"demo_mannequin","location":[0.0,0.0,0.0]}}
{"tool":"add_character_audio","args":{"character_name":"DemoMannequin","identifier":"demo_sample_audio","start_time":0.0,"end_time":1.944,"speech_text":"Demo sample audio"}}
{"tool":"add_character_animation","args":{"character_name":"DemoMannequin","identifier":"demo_standing_greeting","start_time":0.0}}
```

Call `get_sequence_content` after every mutation. A successful final state has:

- one `DemoMannequin` binding
- one `Base Audio Track` containing `sample_audio`
- one `Base Animation Track` containing `standing_greeting`

The verified animation duration is approximately `5.07` seconds. The audio
section is quantized to the 30 fps sequence and may report approximately
`1.93` seconds rather than exactly `1.944`.

## Verify MCP

The MCP endpoint is not a normal webpage. A plain browser or web request may return:

```text
Not Acceptable: Client must accept text/event-stream
```

This means the streamable HTTP server is responding. Use an MCP client to verify protocol initialization and `list_tools`.

Minimum expected tools:

- `get_sequence_content`
- `get_available_characters`
- `get_available_animations`
- `add_character`
- `orient_character_to_center`
- `add_character_animation`
- `add_camera`
- `set_active_camera`
- `apply_camera_template`
- `take_editor_screenshot`

## Open Or Select The Working Sequence

If `get_sequence_content` returns:

```text
No level sequence is currently open. Please open a sequence first.
```

Open `/Game/AIGC_sequence` in UE Sequencer or select it in the CutsceneProvider panel.

Candidate UE Python command:

```python
import unreal
seq = unreal.EditorAssetLibrary.load_asset('/Game/AIGC_sequence.AIGC_sequence')
unreal.get_editor_subsystem(unreal.AssetEditorSubsystem).open_editor_for_assets([seq])
from cutscene_provider.config import set_widget_selected_sequence
set_widget_selected_sequence(seq)
```

Expected empty-sequence verification:

```json
{
  "sequence_name": "AIGC_sequence",
  "frame_rate": 30.0,
  "bindings": [],
  "top_level_tracks": []
}
```

## First Verified Natural-Language Operation

User intent:

> Create a demo camera in the current `AIGC_sequence` and make it active from 0s to 5s.

Tool calls:

```json
{"tool": "add_camera", "args": {"camera_name": "Agent_Demo_Camera"}}
{"tool": "set_active_camera", "args": {"camera_name": "Agent_Demo_Camera", "start_time": 0.0, "end_time": 5.0}}
```

Verified result:

- `bindings` contains `Agent_Demo_Camera`
- binding type is `CineCameraActor`
- camera cut track contains a section for `Agent_Demo_Camera` from `0.0` to `5.0`

Observed caveat:

- Duplicate camera cut sections were observed in one validation run.
- Always inspect `get_sequence_content` after camera edits.

## Empty Demo Limitations

Before demo assets are added:

- `get_available_characters` may return `[]`
- `get_available_animations` may return `[]`
- `get_queryable_asset_kinds` may return empty static/dynamic kinds
- camera templates may still be available because they are plugin-provided
- audio and facial generation tools may be stubs unless external services are configured

Do not attempt a full character/dialogue/animation cutscene until asset queries return usable demo assets.
