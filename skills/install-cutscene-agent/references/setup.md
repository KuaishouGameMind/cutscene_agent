# Verified Setup

## Repositories

- Cutscene Agent:
  `https://github.com/Kuaishou-GameMind/cutscene_agent`
- Unreal Engine plugin:
  `https://github.com/Kuaishou-GameMind/CutsceneProvider`
- Optional agent-oriented reference:
  `https://github.com/Kuaishou-GameMind/cutscene_copilot`

Clone CutsceneProvider with the exact folder name:

```powershell
git clone https://github.com/Kuaishou-GameMind/CutsceneProvider.git CutsceneProvider
```

If Git LFS is installed, verify the plugin UI asset:

```powershell
git lfs pull
git lfs ls-files
```

The Cutscene Agent repository uses Git LFS for UE binary assets. Run
`git lfs install` before cloning when necessary, and confirm that files under
`demo/UE_CSAgent_demo/Content` are materialized rather than small pointer
files.

## Bundled Demo Project

Use this project by default:

```text
<cutscene_agent>/demo/UE_CSAgent_demo/UE_CSAgent_demo.uproject
```

The repository intentionally excludes regenerable directories:

```text
Binaries
DerivedDataCache
Intermediate
Saved
.vs
```

Do not recreate or commit them as part of setup. Unreal Engine and
UnrealBuildTool regenerate them locally.

## Windows Prerequisite Check

Run the bundled preflight script before plugin installation or compilation:

```powershell
& "<cutscene_agent>\skills\install-cutscene-agent\scripts\check_windows_prerequisites.ps1" `
  -ProjectFile "<cutscene_agent>\demo\UE_CSAgent_demo\UE_CSAgent_demo.uproject"
```

For a custom or source-built UE installation that is not registered:

```powershell
& "<cutscene_agent>\skills\install-cutscene-agent\scripts\check_windows_prerequisites.ps1" `
  -ProjectFile "<UEProject>\<ProjectName>.uproject" `
  -UnrealEnginePath "<UE root>"
```

The script outputs JSON and exits with:

- `0`: project, UE, and native build toolchain are ready.
- `2`: one or more prerequisites are missing.

It checks:

- the `.uproject` and its `EngineAssociation`
- Epic Launcher and UnrealVersionSelector registry entries
- explicit custom UE paths
- `UnrealEditor.exe`
- `Build.bat`
- Visual Studio 2022 version 17.8 or newer
- `Game development with C++`
- MSBuild
- MSVC x64 compiler
- Windows 10 or Windows 11 SDK

Do not continue setup when `Ready` is `false`. Show `Missing` and
`SuggestedActions` to the user, wait for installation or a corrected path,
then rerun the same command.

`-SkipBuildToolchainCheck` is reserved for a project with compatible
precompiled editor binaries that were independently verified. Do not use it
for the bundled demo.

## Python

Use Python 3.10 or newer:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

The CLI reads environment variables from its process:

```powershell
$env:LLM_BASE_URL = "http://localhost:11434/v1"
$env:LLM_API_KEY = "your-api-key"
$env:LLM_MODEL_NAME = "your-model"
$env:UE_MCP_URL = "http://localhost:8100/mcp"
python main.py
```

## Install The Plugin

The resulting path must be:

```text
<UEProject>/Plugins/CutsceneProvider/CutsceneProvider.uplugin
```

For local development on Windows, a directory junction keeps the plugin
checkout independent:

```powershell
New-Item -ItemType Directory -Path "<UEProject>\Plugins" -Force
New-Item -ItemType Junction `
  -Path "<UEProject>\Plugins\CutsceneProvider" `
  -Target "<Workspace>\CutsceneProvider"
```

Install the bundled static asset table after the plugin is present:

```powershell
$dataDir = "<UEProject>\Plugins\CutsceneProvider\Content\Data"
New-Item -ItemType Directory -Path $dataDir -Force
Copy-Item `
  "<cutscene_agent>\demo\UE_CSAgent_demo\Setup\CutsceneAssets.xlsx" `
  "$dataDir\CutsceneAssets.xlsx" `
  -Force
```

This step is mandatory for the bundled demo identifiers. The table is kept
in the demo project because CutsceneProvider is a companion repository and
is not vendored into this repository.

Enable these plugins in the `.uproject`:

```json
{
  "Name": "PythonScriptPlugin",
  "Enabled": true
},
{
  "Name": "ControlRig",
  "Enabled": true
},
{
  "Name": "CutsceneProvider",
  "Enabled": true
}
```

## Build

Close Unreal Editor before building:

```powershell
& "<UE>\Engine\Build\BatchFiles\Build.bat" `
  <ProjectName>Editor Win64 Development `
  -Project="<UEProject>\<ProjectName>.uproject" `
  -WaitMutex
```

A Blueprint-only project may need a minimal C++ game module and editor target
before UnrealBuildTool can compile the plugin.

The bundled demo already includes the minimal `Source` and target files
required to build `UE_CSAgent_demoEditor`.

## Start MCP

1. Open the UE project.
2. Wait for CutsceneProvider dependencies to finish installing.
3. Open `Tools -> Cutscene Tools -> Open Cutscene Panel`.
4. Open or select the working Level Sequence.
5. Click `Start`.

Default endpoint:

```text
http://localhost:8100/mcp
```

## Verification

Verify TCP:

```powershell
Test-NetConnection localhost -Port 8100
```

Then use an MCP client to initialize a session and call:

1. `list_tools`
2. `get_sequence_content`
3. `get_queryable_asset_kinds`
4. `get_available_characters`
5. `get_available_animations`
6. `query_assets` for `Audio`

Official demo readiness expects:

```text
demo_mannequin
demo_standing_greeting
demo_sample_audio
```

## End-To-End Acceptance Test

Once all read-only checks pass, proactively ask the user whether to generate
the bundled offline demo in `/Game/AIGC_sequence`.

If accepted, first confirm the sequence is empty. Then follow the exact
recipe in:

```text
skills/cutscene-gen/references/demo.md
```

The acceptance test succeeds only when `get_sequence_content` confirms:

- `DemoMannequin`
- `Base Audio Track` with `sample_audio`
- `Base Animation Track` with `standing_greeting`

Do not clear a non-empty sequence without explicit user approval.
