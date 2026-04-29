"""AIGC Asset Tools — MCP server for AI-generated content asset services.

Provides tools for:
- TTS (Text-to-Speech) audio generation
- Audio-driven facial expression animation generation
- Pushing local files to Unreal Engine via MCP bridge
- Video understanding via vision LLM

NOTE:
- TTS, facial expression, and video understanding tools require external service integration.
  By default they raise NotImplementedError. See README for integration guide.
- push_file_to_ue is a pure bridge tool and works out of the box.
- When started via stdio, NEVER print to stdout. Use stderr or file logging.
"""
import argparse
import json
import os
import base64
from pathlib import Path
from typing import Literal
from mcp.server.fastmcp import FastMCP

mcp_app = FastMCP(name="AIGCAssetTools")

BASE_DIR = Path(__file__).resolve().parent.parent  # cutscene_agent/
UE_MCP_URL: str | None = None


def _resolve_file_path(file_path: str) -> Path:
    """Resolve *file_path* — absolute paths used as-is, relative paths based on BASE_DIR."""
    p = Path(file_path)
    if p.is_absolute():
        return p
    return BASE_DIR / p


async def _call_ue_import_asset(
    ue_url: str,
    data_source: str,
    source_type: str,
    data_type: str,
    file_extension: str,
    identifier_hint: str = "",
    metadata: dict | None = None,
) -> dict:
    """Call UE's import_dynamic_asset tool to push an asset.

    Parameters map 1:1 to the UE-side import_dynamic_asset tool.
    Returns the UE response dict; raises on failure.
    """
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    arguments: dict = {
        "data_source": data_source,
        "source_type": source_type,
        "data_type": data_type,
        "file_extension": file_extension,
    }
    if identifier_hint:
        arguments["identifier_hint"] = identifier_hint
    if metadata:
        arguments["metadata"] = metadata

    async with streamablehttp_client(url=ue_url) as (read_stream, write_stream, _):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            result = await session.call_tool("import_dynamic_asset", arguments=arguments)
            if result.isError:
                text = result.content[0].text if result.content else "Unknown UE error"
                raise RuntimeError(f"UE rejected asset: {text}")
            return json.loads(result.content[0].text)


# ---------------------------------------------------------------------------
# MCP Tools
# ---------------------------------------------------------------------------

@mcp_app.tool(
    name="get_available_tone",
    title="Get Available Tone",
    description=(
        "Get available TTS voice tones. Returns the available tone file list, "
        "organized by gender. Can optionally filter by character name."
    ),
)
def get_available_tone_tool(character_name: str = "") -> str:
    """Get available TTS voice tones from asset/tts_template.

    Args:
        character_name: Optional character name to filter tones.
            If provided and a matching tone file exists, returns that specific tone.
            Otherwise returns all available tones grouped by gender.

    Returns:
        JSON string with tone information.

    Raises:
        NotImplementedError: This is a stub. Integrate your own TTS tone management
            service to provide voice tone selection. See README for details.
    """
    raise NotImplementedError(
        "TTS tone service not configured. "
        "To use this tool, integrate your own voice tone management. "
        "See README for integration guide."
    )


EmotionLiteral = Literal["neutral", "happy", "sad", "angry", "surprise", "fear", "disgust"]


@mcp_app.tool(
    name="tts_function",
    title="TTS Function",
    description=(
        "Generate audio from text using Text-to-Speech. Returns the local file path "
        "and audio metadata. The file can later be pushed to UE via 'push_file_to_ue'. "
        "Params: text, gender (male/female), tone (optional filename), "
        "emotion (neutral/happy/sad/angry/surprise/fear/disgust)."
    ),
)
async def tts_function_tool(
    text: str,
    gender: str = "male",
    tone: str = "",
    emotion: EmotionLiteral = "neutral",
) -> dict:
    """Generate TTS audio and save locally. Returns file path and audio info.

    Args:
        text: The text to synthesize into speech.
        gender: Speaker gender, either 'male' or 'female'.
        tone: Optional tone/voice reference filename from asset/tts_template/.
        emotion: Emotion for synthesis. One of: neutral, happy, sad, angry,
                 surprise, fear, disgust.

    Returns:
        JSON with status, file_path, audio_duration, audio_sample_rate,
        text, gender, and message.

    Raises:
        NotImplementedError: This is a stub. Integrate your own TTS service
            to enable audio generation. See README for details.
    """
    raise NotImplementedError(
        "TTS service not configured. "
        "To use this tool, integrate your own TTS API endpoint. "
        "See README for integration guide."
    )


@mcp_app.tool(
    name="audio_to_face_expression",
    title="Audio to Face Expression",
    description=(
        "Generate facial expression animation from an audio file. "
        "Returns the local file path of the generated .npy file. "
        "Params: audio_file_path (path to .wav file, absolute or relative to working dir), "
        "emotion (neutral/happy/sad/angry/surprise/fear/disgust)."
    ),
)
async def audio_to_face_expression_tool(
    audio_file_path: str,
    emotion: EmotionLiteral = "neutral",
) -> dict:
    """Generate facial expression animation from audio. Saves locally and returns path.

    Args:
        audio_file_path: Path to the source .wav audio file (absolute or relative
                         to the project root).
        emotion: Target emotion for the facial animation. One of: neutral, happy,
                 sad, angry, surprise, fear, disgust.

    Returns:
        JSON with status, file_path, emotion, and message.

    Raises:
        NotImplementedError: This is a stub. Integrate your own facial animation
            generation service to enable this tool. See README for details.
    """
    raise NotImplementedError(
        "Facial expression generation service not configured. "
        "To use this tool, integrate your own audio-to-face-expression API. "
        "See README for integration guide."
    )


@mcp_app.tool(
    name="push_file_to_ue",
    title="Push File to UE",
    description=(
        "Read a local file, base64-encode it, and push to Unreal Engine "
        "via the import_dynamic_asset MCP tool. "
        "Params: file_path (absolute or relative to working dir), "
        "data_type (e.g. 'audio_wav', 'facial_animation_npz'), "
        "file_extension (e.g. '.wav', '.npz'), "
        "identifier_hint (optional, used to generate UE identifier), "
        "metadata (optional dict, e.g. {\"text\": \"hello\"}), "
        "ue_mcp_url (optional, overrides default UE MCP URL)."
    ),
)
async def push_file_to_ue_tool(
    file_path: str,
    data_type: str,
    file_extension: str,
    identifier_hint: str = "",
    metadata: dict | None = None,
    ue_mcp_url: str = "",
) -> str:
    """Read a local file and push it to UE as a dynamic asset via base64.

    This is a bridge tool that base64-encodes a local file and sends it to
    Unreal Engine's CutsceneProvider MCP server for import.

    Args:
        file_path: Path to the local file (absolute or relative to project root).
        data_type: Asset type identifier (e.g. 'audio_wav', 'facial_animation_npz').
        file_extension: File extension including dot (e.g. '.wav', '.npz').
        identifier_hint: Optional hint for generating the UE asset identifier.
        metadata: Optional metadata dict to attach to the asset.
        ue_mcp_url: Optional UE MCP server URL override.

    Returns:
        JSON string with the UE import result.
    """
    resolved = _resolve_file_path(file_path)
    if not resolved.exists():
        return json.dumps({
            "status": "error",
            "error": f"File not found: {resolved}",
            "message": f"File not found: {resolved}",
        })

    target_url = ue_mcp_url or UE_MCP_URL
    if not target_url:
        return json.dumps({
            "status": "error",
            "error": "UE MCP URL not configured. Pass ue_mcp_url or start with --ue-mcp-url.",
            "message": "UE MCP URL not configured.",
        })

    try:
        raw_bytes = resolved.read_bytes()
        b64_data = base64.b64encode(raw_bytes).decode("ascii")
        ue_result = await _call_ue_import_asset(
            ue_url=target_url,
            data_source=b64_data,
            source_type="base64",
            data_type=data_type,
            file_extension=file_extension,
            identifier_hint=identifier_hint,
            metadata=metadata,
        )

        return json.dumps(ue_result)
    except Exception as e:
        return json.dumps({
            "status": "error",
            "error": str(e),
            "message": f"Failed to push file to UE: {e}",
        })


@mcp_app.tool(
    name="video_understanding",
    title="Video Understanding",
    description=(
        "Analyze a video file using a vision LLM. "
        "Input a video file path and a text description of the analysis task. "
        "Returns the LLM's text analysis result."
    ),
)
def video_understanding_tool(video_file_path: str, task_description: str) -> str:
    """Analyze video content using a vision-capable LLM.

    Args:
        video_file_path: Path to the video file (e.g. .mp4).
        task_description: Text describing what to analyze in the video.

    Returns:
        LLM text analysis result.

    Raises:
        NotImplementedError: This is a stub. Integrate your own vision LLM
            service to enable video analysis. See README for details.
    """
    raise NotImplementedError(
        "Video understanding service not configured. "
        "To use this tool, integrate your own vision LLM API endpoint. "
        "See README for integration guide."
    )


# ---------------------------------------------------------------------------
# Server Startup
# ---------------------------------------------------------------------------

def run(transport: str = "stdio", host: str = "0.0.0.0", port: int = 8200) -> None:
    if transport == "streamable-http":
        mcp_app.settings.port = port
        mcp_app.settings.host = host
        mcp_app.run(transport="streamable-http")
    else:
        mcp_app.run()


def main():
    parser = argparse.ArgumentParser(description="AIGC Asset Tools — MCP server for AI-generated content services")
    sub = parser.add_subparsers(dest="command")

    # mcp subcommand: start MCP server over stdio
    mcp_cmd = sub.add_parser("mcp", help="Start MCP server over stdio")
    mcp_cmd.add_argument(
        "--ue-mcp-url",
        type=str,
        default="",
        help="UE MCP server URL for pushing assets (e.g. http://localhost:8100/mcp)",
    )

    # http subcommand: start MCP server over Streamable HTTP
    http_cmd = sub.add_parser("http", help="Start MCP server over Streamable HTTP")
    http_cmd.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="Host to bind (default: 0.0.0.0)",
    )
    http_cmd.add_argument(
        "--port",
        type=int,
        default=8200,
        help="Port to listen on (default: 8200)",
    )
    http_cmd.add_argument(
        "--ue-mcp-url",
        type=str,
        default="",
        help="UE MCP server URL for pushing assets (e.g. http://localhost:8100/mcp)",
    )

    args = parser.parse_args()

    global UE_MCP_URL
    if args.command == "mcp":
        UE_MCP_URL = args.ue_mcp_url or None
        run(transport="stdio")
    elif args.command == "http":
        UE_MCP_URL = args.ue_mcp_url or None
        run(transport="streamable-http", host=args.host, port=args.port)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()