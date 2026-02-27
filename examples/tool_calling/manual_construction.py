"""
Example: Manual McpToolChat construction.

Demonstrates how to build McpToolChat from the constructor for full control
over dependencies (custom tool cache, pre-built model, etc.).

Most users should prefer McpToolChat.from_config() instead — see the other
examples for that approach. Use manual construction when you need to:
- Inject a custom ToolCache or ModelFactory
- Use a pre-built Model instance directly
- Control the MCP client lifecycle yourself
"""

import asyncio
import os

from dotenv import load_dotenv

from casual_llm import UserMessage, SystemMessage

from casual_mcp import McpToolChat, ModelFactory, ToolCache, load_config, load_mcp_client
from casual_mcp.logging import configure_logging

load_dotenv()
configure_logging(level=os.getenv("LOG_LEVEL", "WARNING"))

MODEL_NAME = os.getenv("MODEL_NAME", "gpt-4.1-nano")


async def main():
    config = load_config("config.json")

    if MODEL_NAME not in config.models:
        print(f"Model '{MODEL_NAME}' not found in config. Available models:")
        for name in config.models:
            print(f"  - {name}")
        return

    # Build each dependency manually
    mcp_client = load_mcp_client(config)
    tool_cache = ToolCache(mcp_client)
    model_factory = ModelFactory(config)
    server_names = set(config.servers.keys())

    # Construct McpToolChat with explicit dependencies
    chat = McpToolChat(
        mcp_client=mcp_client,
        system="You are a helpful assistant.",
        tool_cache=tool_cache,
        server_names=server_names,
        model_factory=model_factory,
    )

    async with chat:
        print(f"Model: {MODEL_NAME}")

        tools = await tool_cache.get_tools()
        print(f"Available tools: {len(tools)}")

        # Option A: Pass model name — resolved via model_factory
        messages = [UserMessage(content="What is 42 + 17?")]
        print("\nUser: What is 42 + 17?")

        response_messages = await chat.chat(messages, model=MODEL_NAME)

        for msg in reversed(response_messages):
            if msg.role == "assistant" and msg.content:
                print(f"Assistant: {msg.content}")
                break

        # Option B: Pass a pre-built Model instance directly
        llm_model = model_factory.get_model(MODEL_NAME)

        messages = [
            SystemMessage(content="You are a weather expert."),
            UserMessage(content="What's the weather in London?"),
        ]

        print("\nUser: What's the weather in London?")

        response_messages = await chat.chat(messages, model=llm_model)

        for msg in reversed(response_messages):
            if msg.role == "assistant" and msg.content:
                print(f"Assistant: {msg.content}")
                break

        # Show stats
        stats = chat.get_stats()
        if stats:
            print(f"\nStats: {stats.tool_calls.total} tool calls, {stats.llm_calls} LLM calls")


if __name__ == "__main__":
    # Python <3.12: subprocess transport __del__ fires after the event loop
    # closes, producing harmless "Event loop is closed" RuntimeErrors.
    import sys

    _orig_hook = sys.unraisablehook
    sys.unraisablehook = lambda u: (
        None if "Event loop is closed" in str(u.exc_value) else _orig_hook(u)
    )
    asyncio.run(main())
