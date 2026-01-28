"""
Example: Generate with session management.

Demonstrates multi-turn conversations using session_id.
"""

import asyncio
import os

from dotenv import load_dotenv

from casual_mcp.logging import configure_logging
from casual_mcp.mcp_tool_chat import McpToolChat
from casual_mcp.provider_factory import ProviderFactory
from casual_mcp.utils import load_config, load_mcp_client

load_dotenv()
configure_logging(level=os.getenv("LOG_LEVEL", "INFO"))  # type: ignore

MODEL_NAME = os.getenv("MODEL_NAME", "gpt-4.1-nano")


async def main():
    config = load_config("casual_mcp_config.json")
    mcp_client = load_mcp_client(config)

    if MODEL_NAME not in config.models:
        print(f"Model '{MODEL_NAME}' not found in config. Available models:")
        for name in config.models:
            print(f"  - {name}")
        return

    model_config = config.models[MODEL_NAME]
    provider_factory = ProviderFactory()
    provider = await provider_factory.get_provider(MODEL_NAME, model_config)

    print(f"Model: {MODEL_NAME} ({model_config.provider})")

    chat = McpToolChat(
        mcp_client=mcp_client,
        provider=provider,
    )

    session_id = "demo-session"

    # First turn
    print("\nUser: What time is it now?\n")
    await chat.generate("What time is it now?", session_id=session_id)

    # Second turn - uses context from first
    print("\nUser: What about in Tokyo?\n")
    await chat.generate("What about in Tokyo?", session_id=session_id)

    # Show session info
    session = McpToolChat.get_session(session_id)
    if session:
        print(f"\nSession '{session_id}' has {len(session)} messages")

    # Clean up MCP client connections
    await mcp_client.close()


if __name__ == "__main__":
    asyncio.run(main())
