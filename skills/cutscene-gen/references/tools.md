# Tool Rules

This reference describes how to use CutsceneProvider and AIGCAssetTools MCP tools safely.

## Universal Rules

- Call tools sequentially when operations depend on each other.
- Inspect each tool's input schema before first use in a new environment.
- Do not fabricate identifiers, asset paths, or enum values.
- Treat `get_sequence_content` as the truth after each mutation.
- If a tool returns an error, read it literally and inspect state before retrying.
- Prefer appending or repairing content over destructive actions unless the user asks to reset.

## State Tools

### `get_sequence_content`

Use before planning and after every mutation.

Expected success shape:

```json
{
  "sequence_name": "AIGC_sequence",
  "frame_rate": 30.0,
  "bindings": [],
  "top_level_tracks": []
}
```

If it reports no sequence is open, ask the user to open/select a sequence or run the demo setup command in `demo.md`.

### `clear_sequence`

Use only when the user explicitly asks to reset/regenerate or when a test artifact must be removed. Verify with `get_sequence_content`.

### `save_sequence_as`

Use for preserving a generated result under a new path. Set playback end based on the final planned duration.

## Asset Tools

### Progressive Query

Use:

1. `get_queryable_asset_kinds`
2. `get_query_instruction(asset_kind)`
3. `query_assets(asset_kind, filters)`

Shortcut tools:

- `get_available_characters`
- `get_available_animations`
- `get_available_camera_templates`
- `get_available_tone`

Filtering examples depend on the returned schema. Common filter expressions:

- exact string: `"female"`
- regex: `"/idle|talk/i"`
- numeric: `">3.0"`, `"<5.0"`, `"=30"`

## Character Tools

### `add_character`

Use only with an identifier returned by asset queries.

After adding all characters for a scene, call `orient_character_to_center(names)`.

Then verify:

- binding names match script character names
- positions are plausible
- characters are not too close

### `orient_character_to_center`

Call after all relevant characters are added. It makes characters face the group center on the horizontal plane.

## Audio And Dynamic Import Tools

Default open-source tools may be stubs:

- `get_available_tone`
- `tts_function`
- `audio_to_face_expression`
- `video_understanding`

If they raise `NotImplementedError`, do not force the full audio/face pipeline. Report that audio/face services are not configured and continue with available sequence operations.

For configured services:

1. Generate audio with `tts_function`.
2. Generate face data with `audio_to_face_expression`.
3. Import files with `push_file_to_ue` or `import_dynamic_asset`.
4. Add imported assets to the timeline.

Use `get_importable_asset_types` and `get_import_guide` before importing a new data type.

## Animation Tools

Use `get_available_animations` before `add_character_animation`.

When selecting:

- match action and emotion tags
- prefer duration close to the shot or dialogue duration
- avoid overlap for the same character
- choose idle/emotional filler when the script lacks explicit action

Verify with `get_sequence_content` that the animation section appears on the expected character binding.

## Camera Tools

### Minimal Camera Test

A simple environment test can be:

```json
{"tool": "add_camera", "args": {"camera_name": "Agent_Demo_Camera"}}
{"tool": "set_active_camera", "args": {"camera_name": "Agent_Demo_Camera", "start_time": 0.0, "end_time": 5.0}}
```

Then verify with `get_sequence_content`.

### Template-Based Shots

Call `get_available_camera_templates` before `apply_camera_template`.

Common flow:

1. `add_camera`
2. `apply_camera_template`
3. `set_active_camera`
4. `get_sequence_content`

For dynamic movement, always pass both:

- `movement_template`
- `movement_args`

### Duplicate Camera Cuts

During local validation, duplicate `MovieSceneCameraCutSection` entries were observed after camera mutation. The exact cause was not proven.

Rule:

- inspect camera cuts after camera edits
- if duplicates affect playback or clarity, clean or reset the sequence intentionally
- do not assume a mutation produced exactly one section unless verified

## Viewport Tools

Use viewport tools when the user asks for visual composition or when camera framing must be checked.

Workflow:

1. `take_editor_screenshot` or `take_camera_screenshot`
2. inspect image
3. `move_view` in small increments if needed
4. screenshot again
5. `undo_move_view` if the movement made framing worse

Do not use viewport tools to edit sequence content.
