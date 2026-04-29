# Cutscene Agent

[![Project Page](https://img.shields.io/badge/Project-Page-blue)](https://kuaishou-gamemind.github.io/cutscene_agent/)
[![arXiv](https://img.shields.io/badge/arXiv-2604.25318-b31b1b.svg)](https://arxiv.org/abs/2604.25318)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

**Companion repositories:** [cutscene_copilot](https://github.com/Kuaishou-GameMind/cutscene_copilot) · [CutsceneProvider](https://github.com/Kuaishou-GameMind/CutsceneProvider)

An AI-powered agent that creates cutscene animations in Unreal Engine by orchestrating characters, dialogue audio, body animations, and cameras through natural language instructions.

Built on the [OpenAI Agents SDK](https://github.com/openai/openai-agents-python) with a dual-MCP (Model Context Protocol) architecture.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      Cutscene Agent                         │
│  ┌───────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │ PromptManager │  │ SubAgentRunner│  │ SessionRecorder  │  │
│  └───────┬───────┘  └──────┬───────┘  └──────────────────┘  │
│          │                 │                                │
│  ┌───────┴─────────────────┴───────────┐                    │
│  │         Main Director Agent         │                    │
│  │  (plans outline, delegates tasks)   │                    │
│  └──────────┬──────────────┬───────────┘                    │
│             │              │                                │
│    ┌────────┴───┐   ┌──────┴──────┐                         │
│    │ Scene      │   │ Animation   │   ┌──────────────┐      │
│    │ Specialist │   │ Specialist  │   │ Photographer │      │
│    └────────┬───┘   └──────┬──────┘   └──────┬───────┘      │
└─────────────┼──────────────┼─────────────────┼──────────────┘
              │              │                 │
     ┌────────┴──────────────┴─────────────────┴──────┐
     │          MCP Tool Layer (dual servers)          │
     │                                                 │
     │  ┌─────────────────────┐  ┌──────────────────┐  │
     │  │   CutsceneProvider  │  │  AIGCAssetTools   │  │
     │  │   (UE Plugin MCP)   │  │  (Stdio MCP)      │  │
     │  │                     │  │                    │  │
     │  │ • add_character     │  │ • tts_function     │  │
     │  │ • add_animation     │  │ • audio_to_face    │  │
     │  │ • add_camera        │  │   _expression      │  │
     │  │ • apply_camera      │  │ • push_file_to_ue  │  │
     │  │   _template         │  │ • video             │  │
     │  │ • query_assets      │  │   _understanding   │  │
     │  │ • import_dynamic    │  │ • get_available     │  │
     │  │   _asset            │  │   _tone            │  │
     │  │ • move_view         │  │                    │  │
     │  │ • take_screenshot   │  │                    │  │
     │  │ • ...               │  │                    │  │
     │  └─────────────────────┘  └──────────────────┘  │
     └────────────┬──────────────────────┬─────────────┘
                  │                      │
                  ▼                      ▼
        ┌──────────────────┐   ┌──────────────────┐
        │  Unreal Engine   │   │ External Services │
        │  Level Sequence  │   │ (TTS, FaceAnim,  │
        │                  │   │  Vision LLM)      │
        └──────────────────┘   └──────────────────┘
```

### Dual-MCP Design

| MCP Server                 | Transport       | Role                                                                                                       |
| -------------------------- | --------------- | ---------------------------------------------------------------------------------------------------------- |
| **CutsceneProvider** | Streamable HTTP | UE plugin — manages characters, animations, cameras, asset queries, and dynamic imports inside the editor |
| **AIGCAssetTools**   | Stdio           | External content generation — TTS audio, facial expressions, file bridging to UE                          |

The agent connects to both servers simultaneously. Generated assets (e.g. audio WAV) flow through `push_file_to_ue` → CutsceneProvider's `import_dynamic_asset` to enter the UE pipeline.

### Sub-Agent System

The main **Director** agent can delegate tasks to specialized sub-agents:

| Sub-Agent                      | Purpose                                                                |
| ------------------------------ | ---------------------------------------------------------------------- |
| **Scene Specialist**     | Batch character placement and orientation                              |
| **Animation Specialist** | Animation clip selection and timeline choreography                     |
| **Photographer**         | Vision-based viewport composition (screenshots + iterative adjustment) |
| **Custom**               | Ad-hoc sub-agent with user-defined instructions and tool scope         |

## Prerequisites

- **Python 3.10+**
- **[CutsceneProvider](link upcoming)** — UE plugin providing the editor-side MCP server (default: `http://localhost:8100/mcp`)
- An **OpenAI-compatible LLM API** (OpenAI, Anthropic via proxy, local Ollama, etc.)
- *(Optional)* TTS service, facial expression generation service, vision LLM — for full audio/face pipeline

## Installation

```bash
# Clone the repository
git clone link-to-repo
cd cutscene_agent

# Install dependencies
pip install -r requirements.txt

# Copy and edit environment config
cp .env.example .env
# Edit .env with your LLM API credentials and UE MCP URL
```

## Configuration

All settings are configured via environment variables or a `.env` file. See [.env.example](.env.example) for the full list:

| Variable                    | Description                                                 | Default                       |
| --------------------------- | ----------------------------------------------------------- | ----------------------------- |
| `LLM_BASE_URL`            | OpenAI-compatible API endpoint                              | `http://localhost:11434/v1` |
| `LLM_API_KEY`             | API key for the LLM service                                 | *(required)*                |
| `LLM_MODEL_NAME`          | Model identifier                                            | `claude-sonnet-4-20250514`  |
| `UE_MCP_URL`              | CutsceneProvider MCP endpoint                               | `http://localhost:8100/mcp` |
| `AUTO_MANAGED_MSG_ROLE`   | Role for auto-managed messages (`system` / `developer`) | `system`                    |
| `TOOLCALL_HISTORY_LENGTH` | Max tool-call entries before history compression            | `999`                       |

## Quick Start

1. **Start CutsceneProvider** in Unreal Engine (the plugin auto-starts its MCP server).
2. **Run the agent**:

```bash
python main.py
```

3. **Describe your cutscene** in the CLI prompt, e.g.:

```
> Two characters face each other. Character A greets Character B, 
> then B responds with a surprised expression. Camera starts wide, 
> then cuts to a close-up of B's reaction.
```

The agent will plan an outline, query available assets, generate audio, and orchestrate the full sequence in UE.

## MCP Tool Reference

### AIGCAssetTools (Stdio Server)

Tools provided by `mcp_servers/aigc_asset_tools.py`:

| Tool                         | Status   | Description                                |
| ---------------------------- | -------- | ------------------------------------------ |
| `get_available_tone`       | 🔧 Stub  | List available TTS voice tones             |
| `tts_function`             | 🔧 Stub  | Generate speech audio from text            |
| `audio_to_face_expression` | 🔧 Stub  | Generate facial animation from audio       |
| `video_understanding`      | 🔧 Stub  | Analyze video via vision LLM               |
| `push_file_to_ue`          | ✅ Ready | Bridge local files to UE via base64 import |

> **Stub tools** raise `NotImplementedError` by default. Implement them by connecting to your own services. See [Custom Service Integration](#custom-service-integration) below.

### CutsceneProvider (UE Plugin)

Provided by the CutsceneProvider plugin running inside Unreal Engine. Key tools include:

| Category                 | Tools                                                                                                                                                                      |
| ------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Characters**     | `add_character`, `orient_character_to_center`                                                                                                                          |
| **Audio**          | `add_character_audio`, `add_character_facial_animation`                                                                                                                |
| **Animations**     | `add_character_animation`                                                                                                                                                |
| **Cameras**        | `add_camera`, `set_active_camera`, `apply_camera_template`                                                                                                           |
| **Asset Queries**  | `get_available_characters`, `get_available_animations`, `get_available_camera_templates`, `get_queryable_asset_kinds`, `get_query_instruction`, `query_assets` |
| **Dynamic Import** | `get_importable_asset_types`, `get_import_guide`, `import_dynamic_asset`                                                                                             |
| **Viewport**       | `move_view`, `take_editor_screenshot`, `take_camera_screenshot`                                                                                                      |
| **Sequence**       | `get_sequence_content`, `clear_sequence`, `save_sequence_as`                                                                                                         |

See [CutsceneProvider documentation](link-to-docs) for the full tool reference.

## Custom Service Integration

The stub tools in AIGCAssetTools are designed to be replaced with your own service integrations.

### TTS (Text-to-Speech)

Edit `mcp_servers/aigc_asset_tools.py` and replace the `tts_function_tool` implementation:

```python
@mcp_app.tool(name="tts_function", ...)
async def tts_function_tool(text, gender, tone, emotion) -> dict:
    # Call your TTS API here
    audio_bytes = await your_tts_api.synthesize(text, voice=tone, emotion=emotion)
  
    # Save to local file
    output_path = BASE_DIR / "asset" / "generated_audio" / f"{identifier}.wav"
    output_path.write_bytes(audio_bytes)
  
    return {
        "status": "success",
        "file_path": str(output_path),
        "audio_duration": duration,
        "audio_sample_rate": sample_rate,
        "text": text,
        "gender": gender,
    }
```

The returned `file_path` can then be used with `push_file_to_ue` to import the audio into UE.

### Facial Expression Generation

Replace `audio_to_face_expression_tool` similarly. The output should be a `.npy` file containing blendshape weights, which is then pushed to UE via `push_file_to_ue`.

### Video Understanding

Replace `video_understanding_tool` with a call to any vision-capable LLM (e.g. GPT-4o, Gemini).

## Project Structure

```
cutscene_agent/
├── main.py                     # CLI entry point
├── .env.example                # Environment variable template
├── requirements.txt            # Python dependencies
│
├── core/
│   ├── cutscene_agent.py       # Main CutsceneAgent orchestrator
│   ├── subagent_runner.py      # Sub-agent template system & execution
│   ├── session_recorder.py     # Session recording (events, conversation snapshots)
│   └── sub_agents/
│       └── photographer.py     # Vision-based viewport composition agent
│
├── prompt/
│   ├── __init__.py             # Exports: PromptManager, ContextBlock, etc.
│   ├── manager.py              # Priority-driven prompt assembly with token budget
│   ├── elements.py             # SystemInstruction, ContextBlock, TextElement
│   ├── base.py                 # PromptElement base classes
│   ├── utils.py                # Token counting utilities
│   └── templates/
│       ├── cutscene.py         # Cutscene creation rules & workflow prompts
│       └── common.py           # Identity, safety, formatting instructions
│
├── mcp_servers/
│   └── aigc_asset_tools.py     # AIGCAssetTools MCP server (TTS, face, bridge)
│
└── doc/                        # Documentation
```

## Citation

If you find this work useful, please cite our paper:

```bibtex
@article{he2026cutscene,
  title={Cutscene Agent: An LLM Agent Framework for Automated 3D Cutscene Generation},
  author={He, Lanshan and Pang, Haozhou and Gan, Qi and Shen, Xin and Zhang, Ziwei and Liu, Yibo and Fang, Gang and Liu, Bo and Sheng, Kai and Zeng, Shengfeng and Li, Chaofan and Hui, Zhen and Zhou, Keer and Zhou, Lan and Dai, Shujun},
  journal={arXiv preprint arXiv:2604.25318},
  year={2026}
}
```

## License

See [LICENSE](LICENSE) for details.
