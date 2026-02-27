"""
Example: Multi-turn conversation with persistent connection.

Demonstrates managing message history across multiple turns while
keeping the MCP connection alive using `async with`.
"""

import asyncio
import os

from dotenv import load_dotenv

from casual_llm import UserMessage, SystemMessage

from casual_mcp import McpToolChat, load_config
from casual_mcp.logging import configure_logging

load_dotenv()
configure_logging(level=os.getenv("LOG_LEVEL", "WARNING"))  # type: ignore

MODEL_NAME = os.getenv("MODEL_NAME", "gpt-4.1-nano")


async def main():
    config = load_config("config.json")

    if MODEL_NAME not in config.models:
        print(f"Model '{MODEL_NAME}' not found in config. Available models:")
        for name in config.models:
            print(f"  - {name}")
        return

    async with McpToolChat.from_config(config) as chat:
        print(f"Model: {MODEL_NAME}\n")

        messages = [
            SystemMessage(
                content="You are a weather expert. Use the weather tools to get accurate data."
            ),
        ]

        # Turn 1
        user_input = "What is the weather in Sydney?"
        print(f"User: {user_input}")
        messages.append(UserMessage(content=user_input))

        response_messages = await chat.chat(messages, model=MODEL_NAME)
        messages.extend(response_messages)

        for msg in reversed(response_messages):
            if msg.role == "assistant" and msg.content:
                print(f"Assistant: {msg.content}\n")
                break

        # Stats are per-call, so capture after each turn
        turn1_stats = chat.get_stats()

        # Turn 2
        user_input = "How does it compare to Tokyo?"
        print(f"User: {user_input}")
        messages.append(UserMessage(content=user_input))

        response_messages = await chat.chat(messages, model=MODEL_NAME)
        messages.extend(response_messages)

        for msg in reversed(response_messages):
            if msg.role == "assistant" and msg.content:
                print(f"Assistant: {msg.content}\n")
                break

        turn2_stats = chat.get_stats()

        # Show per-turn and total stats
        if turn1_stats and turn2_stats:
            total_tool_calls = turn1_stats.tool_calls.total + turn2_stats.tool_calls.total
            total_llm_calls = turn1_stats.llm_calls + turn2_stats.llm_calls
            print(f"Turn 1: {turn1_stats.tool_calls.total} tool calls, {turn1_stats.llm_calls} LLM calls")
            print(f"Turn 2: {turn2_stats.tool_calls.total} tool calls, {turn2_stats.llm_calls} LLM calls")
            print(f"Total:  {total_tool_calls} tool calls, {total_llm_calls} LLM calls")


if __name__ == "__main__":
    # Python <3.12: subprocess transport __del__ fires after the event loop
    # closes, producing harmless "Event loop is closed" RuntimeErrors.
    import sys

    _orig_hook = sys.unraisablehook
    sys.unraisablehook = lambda u: (
        None if "Event loop is closed" in str(u.exc_value) else _orig_hook(u)
    )
    asyncio.run(main())
