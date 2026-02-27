"""
Example: Tool discovery across multiple MCP servers.

Demonstrates how the LLM discovers and loads tools from more than one deferred
server in a single conversation.  The prompt is crafted so that the LLM needs
tools from both the **weather** and **time** servers, forcing multiple
``search-tools`` calls (or a single call that returns tools from both).

Uses the same ``config.json`` as ``single_server_discovery.py`` — all servers
are deferred via ``defer_all: true``.
"""

import asyncio
import os

from dotenv import load_dotenv

from casual_llm import SystemMessage, UserMessage

from casual_mcp import McpToolChat, load_config
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

    async with McpToolChat.from_config(config) as chat:
        print(f"Model: {MODEL_NAME}")

        # This prompt requires tools from two different servers:
        #   - weather server: current_weather / forecast
        #   - time server: next_weekday / current_time
        messages = [
            SystemMessage(
                content=(
                    "You are a helpful assistant. Use the available tools to answer "
                    "the user's question accurately."
                )
            ),
            UserMessage(
                content=(
                    "I'm planning a weekend trip to Tokyo. "
                    "What date is next Saturday, and what's the weather forecast for Tokyo "
                    "that day?"
                )
            ),
        ]

        print("\nUser: I'm planning a weekend trip to Tokyo.")
        print(
            "      What date is next Saturday, and what's the weather forecast for Tokyo "
            "that day?"
        )
        print(
            "\n(The LLM needs to discover tools from both the 'time' and 'weather' servers)\n"
        )

        response_messages = await chat.chat(messages, model=MODEL_NAME)

        # Show the conversation flow
        for msg in response_messages:
            if msg.role == "assistant":
                if hasattr(msg, "tool_calls") and msg.tool_calls:
                    for tc in msg.tool_calls:
                        print(f"  Tool call: {tc.function.name}({tc.function.arguments})")
                if msg.content:
                    print(f"\nAssistant: {msg.content}")
            elif msg.role == "tool":
                content = msg.content[:200] + "..." if len(msg.content) > 200 else msg.content
                print(f"  Tool result ({msg.name}): {content}")

        # Show discovery stats
        stats = chat.get_stats()
        if stats:
            print(
                f"\nStats: {stats.llm_calls} LLM calls, {stats.tool_calls.total} tool calls"
            )
            if stats.discovery:
                print(
                    f"Discovery: {stats.discovery.search_calls} search calls, "
                    f"{stats.discovery.tools_discovered} tools discovered"
                )


if __name__ == "__main__":
    # Python <3.12: subprocess transport __del__ fires after the event loop
    # closes, producing harmless "Event loop is closed" RuntimeErrors.
    import sys

    _orig_hook = sys.unraisablehook
    sys.unraisablehook = lambda u: (
        None if "Event loop is closed" in str(u.exc_value) else _orig_hook(u)
    )
    asyncio.run(main())
