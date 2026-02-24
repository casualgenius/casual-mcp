"""
Example: Chat with toolsets.

Demonstrates how to use toolsets to limit which tools are available to the LLM.
This is useful for reducing token usage and restricting LLM capabilities.
"""

import asyncio
import os

from dotenv import load_dotenv

from casual_llm import UserMessage

from casual_mcp import McpToolChat, load_config
from casual_mcp.logging import configure_logging
from casual_mcp.models.toolset_config import ExcludeSpec, ToolSetConfig

load_dotenv()
configure_logging(level=os.getenv("LOG_LEVEL", "WARNING"))

MODEL_NAME = os.getenv("MODEL_NAME", "gpt-4.1-nano")


async def main():
    config = load_config("mcp_config_default.json")

    if MODEL_NAME not in config.models:
        print(f"Model '{MODEL_NAME}' not found in config. Available models:")
        for name in config.models:
            print(f"  - {name}")
        return

    chat = McpToolChat.from_config(config)

    print(f"Model: {MODEL_NAME}")

    # Show all available tools
    all_tools = await chat.tool_cache.get_tools()
    print(f"\nAll available tools ({len(all_tools)}):")
    for tool in all_tools:
        print(f"  - {tool.name}")

    # Option 1: Use a toolset defined in config (if available)
    if config.tool_sets:
        toolset_name = next(iter(config.tool_sets))
        toolset = config.tool_sets[toolset_name]
        print(f"\n--- Using toolset from config: '{toolset_name}' ---")
        print(f"Description: {toolset.description}")
        print(f"Servers: {list(toolset.servers.keys())}")

        prompt = "What time is it?"
        print(f"\nUser: {prompt}")

        messages = [UserMessage(content=prompt)]
        response = await chat.chat(messages, model=MODEL_NAME, tool_set=toolset)
        print(f"Assistant: {response[-1].content}")

    # Option 2: Create a toolset programmatically
    print("\n--- Using programmatic toolset ---")

    # Create a toolset that only includes specific tools
    custom_toolset = ToolSetConfig(
        description="Math tools only",
        servers={
            "math": True,  # Include all tools from 'math' server
        },
    )

    # Check if math server exists
    if "math" in config.servers:
        prompt = "What is 42 * 17?"
        print(f"\nUser: {prompt}")
        print(f"Toolset: {custom_toolset.description}")

        messages = [UserMessage(content=prompt)]
        response = await chat.chat(messages, model=MODEL_NAME, tool_set=custom_toolset)
        print(f"Assistant: {response[-1].content}")

        # Show stats
        stats = chat.get_stats()
        if stats:
            print(f"\nStats: {stats.tool_calls.total} tool calls, {stats.llm_calls} LLM calls")
    else:
        print("Note: 'math' server not configured, skipping programmatic toolset example")

    # Option 3: Toolset with exclusions
    print("\n--- Using toolset with exclusions ---")

    # Get first available server
    if config.servers:
        server_name = next(iter(config.servers))
        exclude_toolset = ToolSetConfig(
            description=f"All {server_name} tools except first one",
            servers={
                server_name: ExcludeSpec(exclude=[]),  # All tools (empty exclude)
            },
        )
        print(f"Using server '{server_name}' with no exclusions")
        print(f"Toolset servers: {list(exclude_toolset.servers.keys())}")

    # Clean up
    await chat.mcp_client.close()


if __name__ == "__main__":
    asyncio.run(main())
