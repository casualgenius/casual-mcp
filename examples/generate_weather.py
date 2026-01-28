"""
Example: Generate with weather question.

Demonstrates the simplest usage of McpToolChat.generate().
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
    provider = provider_factory.get_provider(MODEL_NAME, model_config)

    print(f"Model: {MODEL_NAME} ({model_config.provider})")

    chat = McpToolChat(
        mcp_client=mcp_client,
        provider=provider,
    )

    tools = await chat.tool_cache.get_tools()
    print(f"Available tools: {len(tools)}")

    prompt = "What's the weather in Paris?"
    print(f"\nUser: {prompt}\n")

    response_messages = await chat.generate(prompt)

    for msg in reversed(response_messages):
        if msg.role == "assistant" and msg.content:
            print(f"\nFinal: {msg.content}")
            break

    # Clean up MCP client connections
    await mcp_client.close()


if __name__ == "__main__":
    asyncio.run(main())
