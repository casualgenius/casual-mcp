import json
import os
from collections.abc import Sequence
from typing import Any

from casual_llm import (
    AssistantToolCall,
    ChatMessage,
    Model,
    SystemMessage,
    ToolResultMessage,
    UserMessage,
)
import mcp
from fastmcp import Client

from casual_mcp.convert_tools import tools_from_mcp
from casual_mcp.logging import get_logger
from casual_mcp.models.chat_stats import ChatStats
from casual_mcp.models.config import Config
from casual_mcp.models.tool_discovery_config import ToolDiscoveryConfig
from casual_mcp.models.toolset_config import ToolSetConfig
from casual_mcp.search_tools_tool import SearchToolsTool
from casual_mcp.synthetic_tool import SyntheticTool
from casual_mcp.tool_cache import ToolCache
from casual_mcp.tool_discovery import build_tool_server_map, partition_tools
from casual_mcp.tool_filter import extract_server_and_tool, filter_tools_by_toolset
from casual_mcp.tool_search_index import ToolSearchIndex
from casual_mcp.utils import format_tool_call_result

logger = get_logger("mcp_tool_chat")
sessions: dict[str, list[ChatMessage]] = {}

# Type alias for metadata dictionary
MetaDict = dict[str, Any]


def get_session_messages(session_id: str) -> list[ChatMessage]:
    global sessions

    if session_id not in sessions:
        logger.info(f"Starting new session {session_id}")
        sessions[session_id] = []
    else:
        logger.info(f"Retrieving session {session_id} of length {len(sessions[session_id])}")
    return sessions[session_id].copy()


def add_messages_to_session(session_id: str, messages: list[ChatMessage]) -> None:
    global sessions
    sessions[session_id].extend(messages.copy())


class McpToolChat:
    def __init__(
        self,
        mcp_client: Client[Any],
        model: Model,
        system: str | None = None,
        tool_cache: ToolCache | None = None,
        server_names: set[str] | None = None,
        synthetic_tools: Sequence[SyntheticTool] = (),
        config: Config | None = None,
        tool_discovery_config: ToolDiscoveryConfig | None = None,
    ):
        self.model = model
        self.mcp_client = mcp_client
        self.system = system
        self.tool_cache = tool_cache or ToolCache(mcp_client)
        self.server_names = server_names or set()
        self._tool_cache_version = -1
        self._last_stats: ChatStats | None = None
        self._synthetic_registry: dict[str, SyntheticTool] = {
            st.name: st for st in synthetic_tools
        }

        # Tool discovery configuration
        self._config = config
        self._tool_discovery_config = tool_discovery_config or (
            config.tool_discovery if config is not None else None
        )

    @staticmethod
    def get_session(session_id: str) -> list[ChatMessage] | None:
        global sessions
        return sessions.get(session_id)

    def get_stats(self) -> ChatStats | None:
        """
        Get usage statistics from the last chat() or generate() call.

        Returns None if no calls have been made yet.
        Stats are reset at the start of each new chat()/generate() call.
        """
        return self._last_stats

    def _is_discovery_enabled(self) -> bool:
        """Check whether tool discovery is enabled."""
        return (
            self._tool_discovery_config is not None
            and self._tool_discovery_config.enabled
            and self._config is not None
        )

    async def generate(
        self,
        prompt: str,
        session_id: str | None = None,
        tool_set: ToolSetConfig | None = None,
        meta: MetaDict | None = None,
    ) -> list[ChatMessage]:
        """
        Generate a response to a prompt, optionally using session history.

        Args:
            prompt: The user prompt to respond to
            session_id: Optional session ID for conversation persistence
            tool_set: Optional tool set configuration to filter available tools
            meta: Optional metadata to pass through to MCP tool calls.
                  Useful for passing context like character_id without
                  exposing it to the LLM. Servers can access this via
                  ctx.request_context.meta.

        Returns:
            List of response messages including any tool calls and results
        """
        # Fetch the session if we have a session ID
        messages: list[ChatMessage]
        if session_id:
            messages = get_session_messages(session_id)
        else:
            messages = []

        # Add the prompt as a user message
        user_message = UserMessage(content=prompt)
        messages.append(user_message)

        # Add the user message to the session
        if session_id:
            add_messages_to_session(session_id, [user_message])

        # Perform Chat
        response = await self.chat(messages=messages, tool_set=tool_set, meta=meta)

        # Add responses to session
        if session_id:
            add_messages_to_session(session_id, response)

        return response

    async def chat(
        self,
        messages: list[ChatMessage],
        tool_set: ToolSetConfig | None = None,
        meta: MetaDict | None = None,
    ) -> list[ChatMessage]:
        """
        Process a conversation with tool calling support.

        Args:
            messages: The conversation messages to process
            tool_set: Optional tool set configuration to filter available tools
            meta: Optional metadata to pass through to MCP tool calls.
                  Useful for passing context like character_id without
                  exposing it to the LLM. Servers can access this via
                  ctx.request_context.meta.

        Returns:
            List of response messages including any tool calls and results
        """
        tools = await self.tool_cache.get_tools()

        # Filter tools if a toolset is specified
        if tool_set is not None:
            tools = filter_tools_by_toolset(tools, tool_set, self.server_names, validate=True)
            logger.info(f"Filtered to {len(tools)} tools using toolset")

        # Reset stats at the start of each chat
        self._last_stats = ChatStats()

        # --- Tool discovery: partition tools and set up search ---
        # Build a per-call synthetic registry that includes both the
        # statically registered synthetic tools and the dynamic search_tools.
        call_synthetic_registry = dict(self._synthetic_registry)

        # Track deferred tool names for error interception
        deferred_tool_names: set[str] = set()

        # The loaded MCP tools list (mutable within the loop)
        loaded_tools: list[mcp.Tool] = list(tools)

        # Track the tool cache version for mid-session change detection
        current_cache_version = self.tool_cache.version

        if self._is_discovery_enabled():
            assert self._config is not None
            assert self._tool_discovery_config is not None

            loaded_tools, deferred_by_server = partition_tools(
                tools, self._config, self.server_names
            )

            if deferred_by_server:
                # Build the deferred tool name set
                for server_tools in deferred_by_server.values():
                    for tool in server_tools:
                        deferred_tool_names.add(tool.name)

                # Build the search index from deferred tools
                all_deferred_tools = [
                    t for server_tools in deferred_by_server.values() for t in server_tools
                ]
                tool_server_map = build_tool_server_map(
                    all_deferred_tools, self.server_names
                )
                search_index = ToolSearchIndex(all_deferred_tools, tool_server_map)

                # Create SearchToolsTool for this call
                deferred_server_names = sorted(deferred_by_server.keys())
                search_tools_tool = SearchToolsTool(
                    deferred_tools=deferred_by_server,
                    server_names=deferred_server_names,
                    search_index=search_index,
                    config=self._tool_discovery_config,
                )

                # Add to per-call synthetic registry
                call_synthetic_registry[search_tools_tool.name] = search_tools_tool

                logger.info(
                    f"Tool discovery enabled: {len(loaded_tools)} loaded, "
                    f"{len(deferred_tool_names)} deferred, search_tools injected"
                )
            else:
                logger.debug(
                    "Tool discovery enabled but no deferred tools - "
                    "search_tools not injected"
                )

        # Add a system message if required
        has_system_message = any(message.role == "system" for message in messages)
        if self.system and not has_system_message:
            # Insert the system message at the start of the messages
            logger.debug("Adding System Message")
            messages.insert(0, SystemMessage(content=self.system))

        # Build combined tool list: MCP tools + synthetic tool definitions
        synthetic_definitions = [st.definition for st in call_synthetic_registry.values()]

        logger.info("Start Chat")
        response_messages: list[ChatMessage] = []
        while True:
            # Check for tool cache version changes mid-session
            if (
                self._is_discovery_enabled()
                and self.tool_cache.version != current_cache_version
            ):
                logger.info("Tool cache version changed mid-session, rebuilding discovery index")
                current_cache_version = self.tool_cache.version
                loaded_tools, deferred_tool_names, call_synthetic_registry = (
                    await self._rebuild_discovery_state(
                        tool_set=tool_set,
                        loaded_tools=loaded_tools,
                        base_synthetic_registry=self._synthetic_registry,
                    )
                )
                synthetic_definitions = [
                    st.definition for st in call_synthetic_registry.values()
                ]

            logger.info("Calling the LLM")
            all_tools = tools_from_mcp(loaded_tools) + synthetic_definitions
            ai_message = await self.model.chat(messages=messages, tools=all_tools)

            # Accumulate token usage stats
            self._last_stats.llm_calls += 1
            usage = self.model.get_usage()
            if usage:
                prompt_tokens = getattr(usage, "prompt_tokens", 0) or 0
                completion_tokens = getattr(usage, "completion_tokens", 0) or 0
                self._last_stats.tokens.prompt_tokens += prompt_tokens
                self._last_stats.tokens.completion_tokens += completion_tokens

            # Add the assistant's message
            response_messages.append(ai_message)
            messages.append(ai_message)

            logger.debug(f"Assistant: {ai_message}")
            if not ai_message.tool_calls:
                break

            logger.info(f"Executing {len(ai_message.tool_calls)} tool calls")
            result_count = 0
            for tool_call in ai_message.tool_calls:
                tool_name = tool_call.function.name

                # Track tool call stats - synthetic tools use "_synthetic" server
                self._last_stats.tool_calls.by_tool[tool_name] = (
                    self._last_stats.tool_calls.by_tool.get(tool_name, 0) + 1
                )
                if tool_name in call_synthetic_registry:
                    server_name = "_synthetic"
                else:
                    server_name, _ = extract_server_and_tool(tool_name, self.server_names)
                self._last_stats.tool_calls.by_server[server_name] = (
                    self._last_stats.tool_calls.by_server.get(server_name, 0) + 1
                )

                try:
                    # Check if this is a deferred tool called without search
                    if tool_name in deferred_tool_names:
                        result = ToolResultMessage(
                            name=tool_name,
                            tool_call_id=tool_call.id,
                            content=(
                                f"Error: Tool '{tool_name}' is not yet loaded. "
                                f"Use the 'search_tools' tool to discover and load "
                                f"it first, then call it again."
                            ),
                        )
                    # Check synthetic registry before forwarding to MCP
                    elif tool_name in call_synthetic_registry:
                        result, newly_loaded = await self._execute_synthetic_with_expansion(
                            tool_call, registry=call_synthetic_registry
                        )
                        # Handle newly loaded tools from search_tools execution
                        if newly_loaded:
                            loaded_tools.extend(newly_loaded)
                            for new_tool in newly_loaded:
                                deferred_tool_names.discard(new_tool.name)
                            # Rebuild synthetic definitions for next iteration
                            synthetic_definitions = [
                                st.definition for st in call_synthetic_registry.values()
                            ]
                            logger.info(
                                f"Expanded loaded tools by {len(newly_loaded)} "
                                f"from search_tools"
                            )
                    else:
                        result = await self.execute(tool_call, meta=meta)
                except Exception as e:
                    logger.error(
                        f"Failed to execute tool '{tool_call.function.name}' "
                        f"(id={tool_call.id}): {e}"
                    )
                    # Surface the failure to the LLM so it knows the tool failed
                    result = ToolResultMessage(
                        name=tool_call.function.name,
                        tool_call_id=tool_call.id,
                        content=f"Error executing tool: {e}",
                    )
                if result:
                    messages.append(result)
                    response_messages.append(result)
                    result_count = result_count + 1

            logger.info(f"Added {result_count} tool results")

        logger.debug(f"Final Response: {response_messages[-1].content}")

        return response_messages

    async def _rebuild_discovery_state(
        self,
        tool_set: ToolSetConfig | None,
        loaded_tools: list[mcp.Tool],
        base_synthetic_registry: dict[str, SyntheticTool],
    ) -> tuple[list[mcp.Tool], set[str], dict[str, SyntheticTool]]:
        """Rebuild tool discovery state after a tool cache version change.

        Fetches fresh tools, re-partitions, and rebuilds the search index
        while preserving tools that were already loaded via search_tools.

        Args:
            tool_set: Optional toolset filter to apply.
            loaded_tools: Currently loaded MCP tools (includes previously
                discovered tools).
            base_synthetic_registry: The static synthetic tool registry
                (excludes per-call search_tools).

        Returns:
            Tuple of (new_loaded_tools, new_deferred_names, new_call_registry).
        """
        assert self._config is not None
        assert self._tool_discovery_config is not None

        fresh_tools = await self.tool_cache.get_tools()
        if tool_set is not None:
            fresh_tools = filter_tools_by_toolset(
                fresh_tools, tool_set, self.server_names, validate=True
            )

        # Track which tools were already loaded by name (from previous discovery)
        previously_loaded_names = {t.name for t in loaded_tools}

        new_loaded, deferred_by_server = partition_tools(
            fresh_tools, self._config, self.server_names
        )

        # Keep tools that were previously discovered (loaded via search)
        # even if they would now be partitioned as deferred
        still_deferred_by_server: dict[str, list[mcp.Tool]] = {}
        for server_name, server_tools in deferred_by_server.items():
            still_deferred: list[mcp.Tool] = []
            for tool in server_tools:
                if tool.name in previously_loaded_names:
                    new_loaded.append(tool)
                else:
                    still_deferred.append(tool)
            if still_deferred:
                still_deferred_by_server[server_name] = still_deferred

        deferred_by_server = still_deferred_by_server

        # Build new deferred names set
        new_deferred_names: set[str] = set()
        for server_tools in deferred_by_server.values():
            for tool in server_tools:
                new_deferred_names.add(tool.name)

        # Build new call registry
        new_call_registry = dict(base_synthetic_registry)

        if deferred_by_server:
            all_deferred = [
                t for server_tools in deferred_by_server.values() for t in server_tools
            ]
            tool_server_map = build_tool_server_map(all_deferred, self.server_names)
            search_index = ToolSearchIndex(all_deferred, tool_server_map)
            deferred_server_names = sorted(deferred_by_server.keys())
            search_tools_tool = SearchToolsTool(
                deferred_tools=deferred_by_server,
                server_names=deferred_server_names,
                search_index=search_index,
                config=self._tool_discovery_config,
            )
            new_call_registry[search_tools_tool.name] = search_tools_tool
            logger.info(
                f"Rebuilt discovery: {len(new_loaded)} loaded, "
                f"{len(new_deferred_names)} deferred"
            )

        return new_loaded, new_deferred_names, new_call_registry

    async def _execute_synthetic_with_expansion(
        self,
        tool_call: AssistantToolCall,
        registry: dict[str, SyntheticTool] | None = None,
    ) -> tuple[ToolResultMessage, list[mcp.Tool]]:
        """Execute a synthetic tool call and return newly loaded tools.

        This is used by the chat loop to both produce the ToolResultMessage
        and capture any ``newly_loaded_tools`` for dynamic tool expansion.

        Args:
            tool_call: The tool call to execute via the synthetic tool registry.
            registry: Optional registry to use instead of self._synthetic_registry.

        Returns:
            Tuple of (ToolResultMessage, newly_loaded_tools). The list is
            empty when the synthetic tool does not load new tools.

        Raises:
            KeyError: If the tool is not in the synthetic registry.
        """
        effective_registry = registry or self._synthetic_registry
        tool_name = tool_call.function.name
        synthetic_tool = effective_registry[tool_name]
        tool_args = json.loads(tool_call.function.arguments)

        logger.info(f"Executing synthetic tool: {tool_name}")
        result = await synthetic_tool.execute(tool_args)

        message = ToolResultMessage(
            name=tool_name,
            tool_call_id=tool_call.id,
            content=result.content,
        )

        return message, result.newly_loaded_tools

    async def _execute_synthetic(
        self,
        tool_call: AssistantToolCall,
        registry: dict[str, SyntheticTool] | None = None,
    ) -> ToolResultMessage:
        """Execute a synthetic tool call.

        Convenience wrapper around ``_execute_synthetic_with_expansion``
        that discards the ``newly_loaded_tools`` list. Used by callers
        that do not need dynamic tool expansion.

        Args:
            tool_call: The tool call to execute via the synthetic tool registry.
            registry: Optional registry to use instead of self._synthetic_registry.

        Returns:
            ToolResultMessage with the synthetic tool execution result.

        Raises:
            KeyError: If the tool is not in the synthetic registry.
        """
        message, _ = await self._execute_synthetic_with_expansion(tool_call, registry)
        return message

    async def execute(
        self,
        tool_call: AssistantToolCall,
        meta: MetaDict | None = None,
    ) -> ToolResultMessage:
        """
        Execute a single tool call.

        Args:
            tool_call: The tool call to execute
            meta: Optional metadata to pass to the MCP server.
                  Servers can access this via ctx.request_context.meta.

        Returns:
            ToolResultMessage with the tool execution result
        """
        tool_name = tool_call.function.name
        tool_args = json.loads(tool_call.function.arguments)
        try:
            async with self.mcp_client:
                result = await self.mcp_client.call_tool(tool_name, tool_args, meta=meta)
        except Exception as e:
            if isinstance(e, ValueError):
                logger.warning(e)
            else:
                logger.error(f"Error calling tool: {e}")

            return ToolResultMessage(
                name=tool_call.function.name,
                tool_call_id=tool_call.id,
                content=str(e),
            )

        logger.debug(f"Tool Call Result: {result}")

        result_format = os.getenv("TOOL_RESULT_FORMAT", "result")

        # Prefer structuredContent when available (machine-readable format)
        # Note: MCP types use camelCase (structuredContent), mypy stubs may differ
        structured = getattr(result, "structuredContent", None)
        if structured is not None:
            try:
                content_text = json.dumps(structured)
            except (TypeError, ValueError):
                content_text = str(structured)
        elif not result.content:
            content_text = "[No content returned]"
        else:
            # Fall back to processing content items
            content_parts: list[Any] = []
            for content_item in result.content:
                if content_item.type == "text":
                    try:
                        parsed = json.loads(content_item.text)
                        content_parts.append(parsed)
                    except json.JSONDecodeError:
                        content_parts.append(content_item.text)
                elif hasattr(content_item, "mimeType"):
                    # Image or audio content
                    content_parts.append(f"[{content_item.type}: {content_item.mimeType}]")
                else:
                    content_parts.append(str(content_item))

            content_text = json.dumps(content_parts)

        content = format_tool_call_result(tool_call, content_text, style=result_format)

        return ToolResultMessage(
            name=tool_call.function.name,
            tool_call_id=tool_call.id,
            content=content,
        )
