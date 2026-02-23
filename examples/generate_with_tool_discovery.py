"""
Example: Generate with tool discovery.

Demonstrates how to use tool discovery to defer tool loading. Instead of
sending all tool definitions to the LLM on every call, deferred tools are
made available through a ``search_tools`` meta-tool that the LLM can invoke
on demand.

Requires a ``casual_mcp_config.json`` with ``tool_discovery`` enabled and at
least one server marked with ``defer_loading: true``. For example:

    {
      "clients": {
        "openai": { "provider": "openai" }
      },
      "models": {
        "gpt-4.1-nano": { "client": "openai", "model": "gpt-4.1-nano" }
      },
      "servers": {
        "time": { "command": "python", "args": ["mcp-servers/time/server.py"] },
        "weather": {
          "command": "python",
          "args": ["mcp-servers/weather/server.py"],
          "defer_loading": true
        }
      },
      "tool_discovery": {
        "enabled": true,
        "max_search_results": 5
      }
    }
"""

import asyncio
import os

from dotenv import load_dotenv

from casual_mcp.logging import configure_logging
from casual_mcp.mcp_tool_chat import McpToolChat
from casual_mcp.model_factory import ModelFactory
from casual_mcp.tool_cache import ToolCache
from casual_mcp.tool_discovery import partition_tools
from casual_mcp.utils import load_config, load_mcp_client

load_dotenv()
configure_logging(level=os.getenv("LOG_LEVEL", "WARNING"))

MODEL_NAME = os.getenv("MODEL_NAME", "gpt-4.1-nano")


async def main():
    config = load_config("casual_mcp_config.json")
    mcp_client = load_mcp_client(config)

    if MODEL_NAME not in config.models:
        print(f"Model '{MODEL_NAME}' not found in config. Available models:")
        for name in config.models:
            print(f"  - {name}")
        return

    model_factory = ModelFactory(config)
    llm_model = model_factory.get_model(MODEL_NAME)

    print(f"Model: {MODEL_NAME}")

    # Pass the full config so McpToolChat can partition tools automatically
    tool_cache = ToolCache(mcp_client)
    server_names = set(config.servers.keys())
    chat = McpToolChat(
        mcp_client=mcp_client,
        model=llm_model,
        tool_cache=tool_cache,
        server_names=server_names,
        config=config,
    )

    # Show the partition: which tools are loaded vs deferred
    all_tools = await tool_cache.get_tools()
    loaded, deferred_by_server = partition_tools(all_tools, config, server_names)

    print(f"\nTotal tools: {len(all_tools)}")
    print(f"Loaded (sent to LLM immediately): {len(loaded)}")
    for tool in loaded:
        print(f"  - {tool.name}")

    if deferred_by_server:
        total_deferred = sum(len(t) for t in deferred_by_server.values())
        print(f"Deferred (available via search_tools): {total_deferred}")
        for server, tools in deferred_by_server.items():
            print(f"  [{server}]")
            for tool in tools:
                print(f"    - {tool.name}")
    else:
        print("\nNo deferred tools. Enable tool_discovery and set defer_loading")
        print("on at least one server to see tool discovery in action.")
        await mcp_client.close()
        return

    # The LLM will automatically use search_tools to find deferred tools
    prompt = "What's the weather in Paris?"
    print(f"\nUser: {prompt}")
    print("(The LLM should call search_tools to find weather tools, then use them)\n")

    response_messages = await chat.generate(prompt)

    # Print the conversation flow to show tool discovery in action
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
        print(f"\nStats: {stats.llm_calls} LLM calls, "
              f"{stats.tool_calls.total} tool calls")
        if stats.discovery:
            print(f"Discovery: {stats.discovery.search_calls} search calls, "
                  f"{stats.discovery.tools_discovered} tools discovered")

    await mcp_client.close()


if __name__ == "__main__":
    asyncio.run(main())
