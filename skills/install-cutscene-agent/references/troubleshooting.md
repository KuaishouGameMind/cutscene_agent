# Troubleshooting

## Missing Or Out-Of-Date Module

If UE reports that `CutsceneProviderEditor` is missing or built for another
engine version:

1. Close every Unreal Editor instance.
2. Build the project editor target through UnrealBuildTool or an IDE.
3. Reopen the project.

If UnrealBuildTool cannot find `<ProjectName>Editor`, the project is probably
Blueprint-only and needs a minimal C++ target.

## MCP Port Is Closed

Plugin initialization does not necessarily start the MCP server.

1. Confirm the plugin loaded in the UE log.
2. Open the CutsceneProvider panel.
3. Click `Start`.
4. Check `localhost:8100` again.

## Browser Says Not Acceptable

This response is expected from a plain browser:

```text
Not Acceptable: Client must accept text/event-stream
```

Use an MCP client rather than treating the endpoint as a normal webpage.

## No Sequence Is Open

Open the Level Sequence in Sequencer or select it in the CutsceneProvider
panel. For the official demo, expect `/Game/AIGC_sequence`.

## Asset Queries Are Empty

Confirm:

- `Content/Data/CutsceneAssets.xlsx` exists inside CutsceneProvider.
- It was copied from
  `demo/UE_CSAgent_demo/Setup/CutsceneAssets.xlsx`.
- Its sheets use the required four header rows.
- The character Blueprint and referenced UE assets are saved.
- The server/plugin was restarted or the asset manager cache was reloaded.

For the bundled demo, query results should expose:

- `demo_mannequin`
- `demo_standing_greeting`
- `demo_sample_audio`

## CLI Ignores `.env`

The current `main.py` reads `os.getenv` directly. Export variables into the
shell or launch the process through a tool that injects the environment.

## Offline Tokenizer Failure

If `tiktoken` cannot download its encoding in a restricted environment, use
the repository version that includes approximate token-count fallback.

## Screenshot Hangs

`take_editor_screenshot` may stall while shaders compile or the editor is
throttled in the background. Sequence state can still be verified through
`get_sequence_content`.

## UE Assets Are Tiny Pointer Files

Git LFS content was not materialized. Run:

```powershell
git lfs install
git lfs pull
```

Then confirm the `.uasset` files are real binary assets before opening UE.
