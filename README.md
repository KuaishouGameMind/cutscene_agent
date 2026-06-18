# Cutscene Agent

[![Project Page](https://img.shields.io/badge/Project-Page-blue)](https://kuaishou-gamemind.github.io/cutscene_agent/)
[![arXiv](https://img.shields.io/badge/arXiv-2604.25318-b31b1b.svg)](https://arxiv.org/abs/2604.25318)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

**Companion repositories:** [CutsceneProvider](https://github.com/Kuaishou-GameMind/CutsceneProvider) · [cutscene_copilot](https://github.com/Kuaishou-GameMind/cutscene_copilot)

## TL;DR

Cutscene Agent turns natural-language scripts into fully editable Unreal Engine cutscenes — with coordinated character animation, dialogue, and cinematography — in minutes, not weeks.

## For Agent

Give your coding agent these two skills:

- **[install-cutscene-agent](skills/install-cutscene-agent/SKILL.md)** — clone the required repositories, install dependencies, configure and build the UE plugin, start MCP, verify the environment, and offer to run the bundled demo as an acceptance test.
- **[cutscene-gen](skills/cutscene-gen/SKILL.md)** — query available assets and use CutsceneProvider tools effectively to create, inspect, and repair cutscenes.

With both skills, an MCP-capable agent such as Codex, Claude Code, opencode,
or a Copilot-style agent can set up the project and control Sequencer from
natural-language requests.

## For Human

### What You Need

- Python 3.10+
- Unreal Engine 5.6
- [CutsceneProvider](https://github.com/Kuaishou-GameMind/CutsceneProvider)
- An OpenAI-compatible LLM API for the Python CLI

Online TTS, facial-animation, and vision services are optional. A bundled
demo can use offline audio and animation assets without those services.

The repository includes a ready-to-use UE project at
[`demo/UE_CSAgent_demo`](demo/UE_CSAgent_demo).

### 1. Install The Python Project

```bash
git clone https://github.com/Kuaishou-GameMind/cutscene_agent.git
cd cutscene_agent

python -m venv .venv
```

Activate the virtual environment using the command appropriate for your
platform, then install dependencies:

```bash
python -m pip install -r requirements.txt
```

### 2. Install CutsceneProvider

Use the bundled project under `demo/UE_CSAgent_demo`, or install
CutsceneProvider into another UE project's `Plugins` directory. The plugin
folder must be named `CutsceneProvider`:

```bash
cd YourProject/Plugins
git clone https://github.com/Kuaishou-GameMind/CutsceneProvider.git CutsceneProvider
```

Enable these plugins:

- `PythonScriptPlugin`
- `ControlRig`
- `CutsceneProvider`

Regenerate project files and build the editor target if UE asks to compile
`CutsceneProviderEditor`.

### 3. Start The MCP Server

1. Open the UE project.
2. Open the target Level Sequence in Sequencer.
3. Go to `Tools -> Cutscene Tools -> Open Cutscene Panel`.
4. Select the sequence and click **Start**.

The default endpoint is:

```text
http://localhost:8100/mcp
```

### 4. Choose How To Control Sequencer

#### MCP-Capable Agent

Configure your agent to connect to the CutsceneProvider endpoint, teach it
the [cutscene-gen skill](skills/cutscene-gen/SKILL.md), and describe the
scene in natural language:

```text
Make a demo with the bundled character, voice line, and greeting animation.
```

#### Python CLI

Set the configuration in the process environment:

```bash
LLM_BASE_URL=http://localhost:11434/v1
LLM_API_KEY=your-api-key
LLM_MODEL_NAME=your-model
UE_MCP_URL=http://localhost:8100/mcp
```

Then run:

```bash
python main.py
```

> `.env.example` documents the variables, but the current CLI reads process
> environment variables directly.

### How It Works

Cutscene Agent uses two MCP layers:

| Component | Role |
| --- | --- |
| **CutsceneProvider** | Runs inside UE and edits Level Sequences, actors, animations, audio, cameras, assets, and the viewport |
| **AIGCAssetTools** | Provides optional external generation hooks for TTS, facial animation, vision, and file delivery |

The main Director agent can delegate character staging, animation selection,
and viewport composition to specialized sub-agents.

### Key MCP Tools

| Category | Tools |
| --- | --- |
| State | `get_sequence_content`, `clear_sequence`, `save_sequence_as` |
| Assets | `get_queryable_asset_kinds`, `query_assets`, `get_available_characters`, `get_available_animations` |
| Characters | `add_character`, `orient_character_to_center` |
| Audio and face | `add_character_audio`, `add_character_facial_animation`, `import_dynamic_asset` |
| Animation | `add_character_animation` |
| Camera | `add_camera`, `apply_camera_template`, `set_active_camera` |
| Viewport | `take_editor_screenshot`, `take_camera_screenshot`, `move_view` |

### Optional Service Integration

The open-source AIGC service functions in
[`mcp_servers/aigc_asset_tools.py`](mcp_servers/aigc_asset_tools.py) are
extension points:

- `tts_function`
- `audio_to_face_expression`
- `video_understanding`

Connect these functions to your own services when you need dynamically
generated speech, facial animation, or visual analysis. The file bridge
`push_file_to_ue` is ready to send generated assets into CutsceneProvider.

### Project Structure

```text
cutscene_agent/
├── main.py
├── core/                  # Director, sub-agents, and session recording
├── prompt/                # Prompt assembly and cutscene workflow rules
├── mcp_servers/           # Optional AIGC asset service
├── skills/
│   ├── install-cutscene-agent/
│   └── cutscene-gen/
└── docs/
```

## Citation

```bibtex
@article{he2026cutscene,
  title={Cutscene Agent: An LLM Agent Framework for Automated 3D Cutscene Generation},
  author={He, Lanshan and Pang, Haozhou and Gan, Qi and Shen, Xin and Zhang, Ziwei and Liu, Yibo and Fang, Gang and Liu, Bo and Sheng, Kai and Zeng, Shengfeng and Li, Chaofan and Hui, Zhen and Zhou, Keer and Zhou, Lan and Dai, Shujun},
  journal={arXiv preprint arXiv:2604.25318},
  year={2026}
}
```

## License

This project is licensed under the [MIT License](LICENSE).
