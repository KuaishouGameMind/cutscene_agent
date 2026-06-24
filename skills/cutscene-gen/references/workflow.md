# Cutscene Workflow

Use this workflow for script-driven or natural-language cutscene creation in Unreal Engine Level Sequences.

## Phase 0: Understand The Request

Extract:

- characters and identities
- shot list or scene beats
- dialogue lines and emotions
- explicit actions
- intended pacing and duration
- camera language, such as close-up, wide, over-the-shoulder, dolly, or orbit

If the request is underspecified, make conservative cinematic choices instead of stopping, unless missing information prevents safe tool use.

## Phase 1: Inspect Current State

Call `get_sequence_content` first.

Use the returned JSON to determine:

- current sequence name and frame rate
- existing character/camera bindings
- existing animation/audio/camera tracks
- whether the task should append, revise, or repair content

If no Level Sequence is open, stop sequence editing and ask the user to open/select the working sequence.

## Phase 2: Discover Assets

Never assume asset identifiers.

Call at least:

- `get_available_characters`
- `get_available_animations`
- `get_available_camera_templates`

When a richer search is needed:

1. `get_queryable_asset_kinds`
2. `get_query_instruction(asset_kind)`
3. `query_assets(asset_kind, filters)`

Use returned metadata such as gender, tags, duration, description, style, or priority to choose assets.

## Phase 3: Stage Characters

Use the script to map story characters to queried character assets.

Default placements:

- two-person dialogue: `[-60, 0, 0]` and `[60, 0, 0]`
- three-person dialogue: `[-60, 0, 0]`, `[30, -52, 0]`, `[30, 52, 0]`
- side-by-side spacing: about 70
- staggered front-back spacing: about 40

Call sequence:

1. `add_character` once per character
2. `orient_character_to_center` once after all relevant characters exist
3. `get_sequence_content` to verify bindings

`add_character` handles spawn and position, not final group orientation.

## Phase 4: Dialogue, Audio, And Face

Use this phase only if AIGCAssetTools or equivalent services are configured. In the default open-source stub state, TTS and face generation may raise `NotImplementedError`.

Dialogue parsing rules:

- quoted text is spoken dialogue
- parenthetical text is stage direction, emotion, pause, or action note
- do not send parenthetical text to TTS
- preserve pauses on the timeline when specified

Tone rules:

- call `get_available_tone` before TTS
- character-specific tone wins
- otherwise match gender
- keep the same tone for the same character throughout the scene
- use different tones for different characters when available

Tool chain:

1. `tts_function(text, gender, tone, emotion)`
2. `audio_to_face_expression(audio_file_path, emotion)`
3. `push_file_to_ue` or `import_dynamic_asset` for audio
4. `add_character_audio(character_name, identifier, start_time, end_time)`
5. `push_file_to_ue` or `import_dynamic_asset` for face data
6. `add_character_facial_animation(character_name, identifier, start_time, gender)`

Set audio `end_time = start_time + audio_duration`.

## Phase 5: Body Animation

Use `get_available_animations`, optionally filtered by gender if supported.

Choose animations by:

- emotion
- action tags
- duration proximity
- character gender/skeleton compatibility
- non-overlap with existing sections

Rules:

- do not overlap body animations for the same character unless blend behavior is intentional
- avoid unexplained gaps for characters that should remain visibly performing
- if no exact action exists, choose an idle/emotional animation matching the dialogue

Call `add_character_animation`, then verify with `get_sequence_content`.

## Phase 6: Cameras

Call `get_available_camera_templates` before choosing templates.

Typical sequence:

1. `add_camera(camera_name)`
2. `apply_camera_template(camera_name, position_template, position_args, movement_template, movement_args, start_time, duration)`
3. `set_active_camera(camera_name, start_time, end_time)`
4. `get_sequence_content`

Camera principles:

- ensure the timeline has active camera coverage
- vary shot types across the scene
- use OTS for dialogue, close-up for emotional beats, wide shots for establishing or group context
- add Dolly or Orbit movement sparingly for longer shots
- when using a dynamic movement, provide both `movement_template` and `movement_args`

If the project has no characters yet, a simple camera creation/cut test is still useful for checking MCP control of Sequencer.

## Phase 7: Review And Repair

After all intended edits, inspect `get_sequence_content`.

Check:

- all expected characters are bound
- audio sections play fully
- facial animations align with audio start time
- body animations do not conflict
- camera cuts cover the intended duration
- no accidental duplicate camera cuts or duplicate tracks exist
- saved sequence path matches the user's target

If needed, use small corrective tool calls and verify again.
