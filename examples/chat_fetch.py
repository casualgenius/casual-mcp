"""
Example: Chat API with explicit message control.

Demonstrates McpToolChat.chat() with a custom message list.
"""

import asyncio
import os

from dotenv import load_dotenv

from casual_llm import UserMessage, SystemMessage

from casual_mcp.logging import configure_logging
from casual_mcp.mcp_tool_chat import McpToolChat
from casual_mcp.provider_factory import ProviderFactory
from casual_mcp.utils import load_config, load_mcp_client

load_dotenv()
configure_logging(level=os.getenv("LOG_LEVEL", "WARNING"))  # type: ignore

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
    provider = provider_factory.get_provider(MODEL_NAME, model_config)


    chat = McpToolChat(
        mcp_client=mcp_client,
        provider=provider,
    )

    # Build messages manually for full control
    messages = [
        SystemMessage(content="You are a webpage summariser, you will be given a url to fetch and then summarise the content and return it to the user."),
        UserMessage(content="https://www.anthropic.com/news/model-context-protocol"),
    ]

    response_messages = await chat.chat(messages)

    print(f"Model: {MODEL_NAME} ({model_config.provider})")
    print("\nSummarise https://www.anthropic.com/news/model-context-protocol\n")
    tool_count = sum(1 for m in response_messages if m.role == "tool")
    print(f"\nResponse: {len(response_messages)} messages, {tool_count} tool results")

    for msg in reversed(response_messages):
        if msg.role == "assistant" and msg.content:
            print(f"\nFinal: {msg.content}")
            break

    # Clean up MCP client connections
    await mcp_client.close()


if __name__ == "__main__":
    asyncio.run(main())
