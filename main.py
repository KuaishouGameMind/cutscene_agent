import os
import asyncio
from core.cutscene_agent import CutsceneAgent, CutsceneAgentSettings, EventType

async def run_cli():
    """Run CutsceneAgent in command-line interface mode."""
    settings = CutsceneAgentSettings(
        base_url=os.getenv("LLM_BASE_URL", "http://localhost:11434/v1"),
        api_key=os.getenv("LLM_API_KEY", ""),
        model_name=os.getenv("LLM_MODEL_NAME", "claude-sonnet-4-20250514"),
        ue_mcp_server_url=os.getenv("UE_MCP_URL", "http://localhost:8100/mcp"),
        auto_managed_message_role=os.getenv("AUTO_MANAGED_MSG_ROLE", "system"),
        toolcall_history_length=int(os.getenv("TOOLCALL_HISTORY_LENGTH", "999")),
    )
    cutscene_agent = CutsceneAgent(settings)
    async for _ in cutscene_agent.initialize():
        pass

    await cutscene_agent.run_cli_loop()
    await cutscene_agent.close()


if __name__ == "__main__":
    asyncio.run(run_cli())