"""
Example: Chat API with explicit message control.

Demonstrates McpToolChat.chat() with a custom message list.
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
        # Build messages manually for full control
        messages = [
            SystemMessage(
                content="You are a webpage summariser, you will be given a url to fetch and then summarise the content and return it to the user."
            ),
            UserMessage(content="https://www.anthropic.com/news/model-context-protocol"),
        ]

        response_messages = await chat.chat(messages, model=MODEL_NAME)

        print(f"Model: {MODEL_NAME}")
        print("\nSummarise https://www.anthropic.com/news/model-context-protocol\n")
        tool_count = sum(1 for m in response_messages if m.role == "tool")
        print(f"\nResponse: {len(response_messages)} messages, {tool_count} tool results")

        for msg in reversed(response_messages):
            if msg.role == "assistant" and msg.content:
                print(f"\nFinal: {msg.content}")
                break


if __name__ == "__main__":
    # Python <3.12: subprocess transport __del__ fires after the event loop
    # closes, producing harmless "Event loop is closed" RuntimeErrors.
    import sys

    _orig_hook = sys.unraisablehook
    sys.unraisablehook = lambda u: (
        None if "Event loop is closed" in str(u.exc_value) else _orig_hook(u)
    )
    asyncio.run(main())
