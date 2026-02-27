import asyncio
import json
import os
from collections.abc import Sequence
from typing import Any

from casual_llm import (
    AssistantToolCall,
    ChatMessage,
    ChatOptions,
    Model,
    SystemMessage,
    ToolResultMessage,
)
import mcp
from fastmcp import Client

from casual_mcp.convert_tools import tools_from_mcp
from casual_mcp.logging import get_logger
from casual_mcp.models.chat_stats import ChatStats, DiscoveryStats
from casual_mcp.models.config import Config
from casual_mcp.models.tool_discovery_config import ToolDiscoveryConfig
from casual_mcp.models.toolset_config import ToolSetConfig
from casual_mcp.search_tools_tool import SearchToolsTool
from casual_mcp.synthetic_tool import SyntheticTool
from casual_mcp.tool_cache import ToolCache
from casual_mcp.tool_discovery import build_tool_server_map, partition_tools
from casual_mcp.tool_filter import extract_server_and_tool, filter_tools_by_toolset
from casual_mcp.tool_search_index import ToolSearchIndex
from casual_mcp.model_factory import ModelFactory
from casual_mcp.utils import format_tool_call_result, load_mcp_client, render_system_prompt

logger = get_logger("mcp_tool_chat")

# Type alias for metadata dictionary
MetaDict = dict[str, Any]

# Default maximum number of tool-call loop iterations before aborting.
# Can be overridden via the MCP_MAX_CHAT_ITERATIONS environment variable.
DEFAULT_MAX_ITERATIONS = int(os.getenv("MCP_MAX_CHAT_ITERATIONS", "50"))


class McpToolChat:
    """Orchestrates LLM chat with MCP tool calling and optional tool discovery.

    Manages the recursive loop of sending messages to an LLM, executing any
    tool calls via the MCP client (or synthetic tools), and feeding results
    back until the LLM produces a final answer.

    Use ``from_config()`` to create an instance with tool discovery and
    model resolution wired automatically. When constructed directly, tool
    discovery is not available — callers manage their own tool setup.

    Args:
        mcp_client: The MCP client used to execute tool calls.
        system: Optional default system prompt prepended to conversations.
        tool_cache: Optional ``ToolCache`` for caching tool listings.
        server_names: Known MCP server names (used for tool-name parsing).
        synthetic_tools: Additional synthetic tools handled internally.
        model_factory: Optional ``ModelFactory`` for resolving model names
            to ``Model`` instances at call time.
    """

    def __init__(
        self,
        mcp_client: Client[Any],
        system: str | None = None,
        tool_cache: ToolCache | None = None,
        server_names: set[str] | None = None,
        synthetic_tools: Sequence[SyntheticTool] = (),
        model_factory: ModelFactory | None = None,
    ):
        self.mcp_client = mcp_client
        self.system = system
        self.tool_cache = tool_cache or ToolCache(mcp_client)
        self.server_names = server_names or set()
        self.model_factory = model_factory
        self._tool_cache_version = -1
        self._last_stats: ChatStats | None = None
        self._synthetic_registry: dict[str, SyntheticTool] = {st.name: st for st in synthetic_tools}

        # Tool discovery configuration (set by from_config())
        self._config: Config | None = None
        self._tool_discovery_config: ToolDiscoveryConfig | None = None

    def get_stats(self) -> ChatStats | None:
        """
        Get usage statistics from the last chat() call.

        Returns None if no calls have been made yet.
        Stats are reset at the start of each new chat() call.
        """
        return self._last_stats

    def _is_discovery_enabled(self) -> bool:
        """Check whether tool discovery is enabled."""
        return (
            self._tool_discovery_config is not None
            and self._tool_discovery_config.enabled
            and self._config is not None
        )

    @classmethod
    def from_config(
        cls,
        config: Config,
        system: str | None = None,
        synthetic_tools: Sequence[SyntheticTool] = (),
    ) -> "McpToolChat":
        """Create an ``McpToolChat`` instance from a ``Config`` object.

        Internally builds the MCP client, tool cache, model factory, and
        server names from the configuration. Model selection is deferred
        to ``chat()`` call time.

        Args:
            config: The application configuration.
            system: Optional default system prompt.
            synthetic_tools: Additional synthetic tools handled internally.

        Returns:
            A fully-wired ``McpToolChat`` instance.
        """
        mcp_client = load_mcp_client(config)
        tool_cache = ToolCache(mcp_client)
        model_factory = ModelFactory(config)
        server_names = set(config.servers.keys())

        instance = cls(
            mcp_client=mcp_client,
            tool_cache=tool_cache,
            server_names=server_names,
            model_factory=model_factory,
            system=system,
            synthetic_tools=synthetic_tools,
        )

        # Wire up tool discovery (only available via from_config)
        instance._config = config
        instance._tool_discovery_config = config.tool_discovery

        return instance

    def _resolve_model(self, model: str | Model | None = None) -> Model:
        """Resolve a model argument to a ``Model`` instance.

        Resolution order:
        1. If *model* is already a ``Model`` instance, use it directly.
        2. If *model* is a string name, resolve via ``self.model_factory``.
        3. If ``None``, raise ``ValueError``.
        """
        if model is None:
            raise ValueError("No model specified. Provide a model to chat().")

        if isinstance(model, Model):
            return model

        # It's a string name — resolve via factory
        if self.model_factory is None:
            raise ValueError(
                f"Cannot resolve model name '{model}' without a model_factory. "
                "Either pass a Model instance or provide a model_factory."
            )
        return self.model_factory.get_model(model)

    async def _resolve_system_prompt(
        self,
        system: str | None = None,
        model_name: str | None = None,
    ) -> str | None:
        """Resolve a system prompt for the current call.

        Resolution order:
        1. Explicit *system* param passed to ``chat()``.
        2. If *model_name* is provided and its config has a ``template``,
           render it using the current tool list.
        3. Fall back to ``self.system`` (the constructor default).
        """
        if system is not None:
            return system

        # Try to resolve from model config template
        if model_name and self._config:
            model_config = self._config.models.get(model_name)
            if model_config and model_config.template:
                tools = await self.tool_cache.get_tools()
                return render_system_prompt(f"{model_config.template}.j2", tools)

        return self.system

    def _setup_discovery(
        self,
        tools: list[mcp.Tool],
        stats: ChatStats,
    ) -> tuple[list[mcp.Tool], set[str], dict[str, SyntheticTool], str | None]:
        """Partition tools and build discovery state for a chat call.

        Returns:
            Tuple of (loaded_tools, deferred_tool_names, call_synthetic_registry,
            discovery_system_prompt).  The system prompt is ``None`` when there
            are no deferred tools or discovery is disabled.
        """
        call_synthetic_registry = dict(self._synthetic_registry)
        deferred_tool_names: set[str] = set()
        loaded_tools: list[mcp.Tool] = list(tools)

        if not self._is_discovery_enabled():
            return loaded_tools, deferred_tool_names, call_synthetic_registry, None

        if self._config is None or self._tool_discovery_config is None:
            raise RuntimeError(
                "Tool discovery is enabled but config is not set. "
                "Use McpToolChat.from_config() to enable tool discovery."
            )

        stats.discovery = DiscoveryStats()

        loaded_tools, deferred_by_server = partition_tools(tools, self._config, self.server_names)

        discovery_system_prompt: str | None = None

        if deferred_by_server:
            for server_tools in deferred_by_server.values():
                for tool in server_tools:
                    deferred_tool_names.add(tool.name)

            all_deferred_tools = [
                t for server_tools in deferred_by_server.values() for t in server_tools
            ]
            tool_server_map = build_tool_server_map(all_deferred_tools, self.server_names)
            search_index = ToolSearchIndex(all_deferred_tools, tool_server_map)

            search_tools_tool = SearchToolsTool(
                deferred_tools=deferred_by_server,
                server_names=sorted(deferred_by_server.keys()),
                search_index=search_index,
                config=self._tool_discovery_config,
            )
            call_synthetic_registry[search_tools_tool.name] = search_tools_tool
            discovery_system_prompt = search_tools_tool.system_prompt

            logger.info(
                f"Tool discovery enabled: {len(loaded_tools)} loaded, "
                f"{len(deferred_tool_names)} deferred, search-tools injected"
            )
        else:
            logger.debug("Tool discovery enabled but no deferred tools - search-tools not injected")

        return loaded_tools, deferred_tool_names, call_synthetic_registry, discovery_system_prompt

    async def _execute_tool_call(
        self,
        tool_call: AssistantToolCall,
        *,
        deferred_tool_names: set[str],
        call_synthetic_registry: dict[str, SyntheticTool],
        loaded_tools: list[mcp.Tool],
        stats: ChatStats,
        meta: MetaDict | None,
    ) -> tuple[ToolResultMessage, bool]:
        """Execute a single tool call and return the result.

        Returns:
            Tuple of (result_message, synthetic_definitions_changed).
        """
        tool_name = tool_call.function.name
        definitions_changed = False

        # Track tool call stats
        stats.tool_calls.by_tool[tool_name] = stats.tool_calls.by_tool.get(tool_name, 0) + 1
        if tool_name in call_synthetic_registry:
            server_name = "_synthetic"
        else:
            server_name, _ = extract_server_and_tool(tool_name, self.server_names)
        stats.tool_calls.by_server[server_name] = stats.tool_calls.by_server.get(server_name, 0) + 1

        try:
            if tool_name in deferred_tool_names:
                result = ToolResultMessage(
                    name=tool_name,
                    tool_call_id=tool_call.id,
                    content=(
                        f"Error: Tool '{tool_name}' is not yet loaded. "
                        f"Use the 'search-tools' tool to discover and load "
                        f"it first, then call it again."
                    ),
                )
            elif tool_name in call_synthetic_registry:
                result, newly_loaded = await self._execute_synthetic_with_expansion(
                    tool_call, registry=call_synthetic_registry
                )
                if tool_name == "search-tools" and stats.discovery is not None:
                    stats.discovery.search_calls += 1
                    stats.discovery.tools_discovered += len(newly_loaded)
                if newly_loaded:
                    loaded_tools.extend(newly_loaded)
                    for new_tool in newly_loaded:
                        deferred_tool_names.discard(new_tool.name)
                    definitions_changed = True
                    logger.info(f"Expanded loaded tools by {len(newly_loaded)} from search-tools")
            else:
                result = await self.execute(tool_call, meta=meta)
        except Exception as e:
            logger.error(
                f"Failed to execute tool '{tool_call.function.name}' (id={tool_call.id}): {e}"
            )
            result = ToolResultMessage(
                name=tool_call.function.name,
                tool_call_id=tool_call.id,
                content=f"Error: Tool '{tool_call.function.name}' failed to execute.",
            )

        return result, definitions_changed

    async def chat(
        self,
        messages: list[ChatMessage],
        tool_set: ToolSetConfig | None = None,
        meta: MetaDict | None = None,
        model: str | Model | None = None,
        system: str | None = None,
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
            model: Optional model override — a ``Model`` instance or a string
                name to resolve via the model factory.
            system: Optional system prompt override for this call.

        Returns:
            List of response messages including any tool calls and results
        """
        # Work on a copy so we don't mutate the caller's list
        messages = list(messages)

        # Resolve model and system prompt for this call
        resolved_model = self._resolve_model(model)
        model_name = model if isinstance(model, str) else None
        resolved_system = await self._resolve_system_prompt(system, model_name)

        tools = await self.tool_cache.get_tools()
        if tool_set is not None:
            tools = filter_tools_by_toolset(tools, tool_set, self.server_names, validate=True)
            logger.info(f"Filtered to {len(tools)} tools using toolset")

        # Per-call stats (assigned to self._last_stats at the end)
        stats = ChatStats()

        # Set up tool discovery (partitioning, search index, synthetic registry)
        loaded_tools, deferred_tool_names, call_synthetic_registry, discovery_system_prompt = (
            self._setup_discovery(tools, stats)
        )

        # Track the tool cache version for mid-session change detection
        current_cache_version = self.tool_cache.version

        # Add a system message if required
        has_system_message = any(message.role == "system" for message in messages)
        if resolved_system and not has_system_message:
            logger.debug("Adding System Message")
            messages.insert(0, SystemMessage(content=resolved_system))

        # Inject the discovery manifest as a system message so the LLM knows
        # which deferred tools are available via search-tools.  Placed after
        # any existing system messages but before the first user message.
        if discovery_system_prompt:
            insert_idx = 0
            for i, msg in enumerate(messages):
                if msg.role == "system":
                    insert_idx = i + 1
                else:
                    break
            messages.insert(insert_idx, SystemMessage(content=discovery_system_prompt))

        # Build combined tool list: MCP tools + synthetic tool definitions
        # Cache the converted MCP tools to avoid reconversion every iteration
        converted_mcp_tools = tools_from_mcp(loaded_tools)
        synthetic_definitions = [st.definition for st in call_synthetic_registry.values()]

        logger.info("Start Chat")
        response_messages: list[ChatMessage] = []
        for _iteration in range(DEFAULT_MAX_ITERATIONS):
            # Check for tool cache version changes mid-session
            if self._is_discovery_enabled() and self.tool_cache.version != current_cache_version:
                logger.info("Tool cache version changed mid-session, rebuilding discovery index")
                current_cache_version = self.tool_cache.version
                (
                    loaded_tools,
                    deferred_tool_names,
                    call_synthetic_registry,
                    new_discovery_prompt,
                ) = await self._rebuild_discovery_state(
                    tool_set=tool_set,
                    loaded_tools=loaded_tools,
                    base_synthetic_registry=self._synthetic_registry,
                )
                converted_mcp_tools = tools_from_mcp(loaded_tools)
                synthetic_definitions = [st.definition for st in call_synthetic_registry.values()]
                # Replace the discovery system message if the manifest changed
                if discovery_system_prompt or new_discovery_prompt:
                    messages = [m for m in messages if not (
                        m.role == "system" and hasattr(m, "content")
                        and m.content == discovery_system_prompt
                    )]
                    if new_discovery_prompt:
                        insert_idx = 0
                        for i, msg in enumerate(messages):
                            if msg.role == "system":
                                insert_idx = i + 1
                            else:
                                break
                        messages.insert(insert_idx, SystemMessage(content=new_discovery_prompt))
                    discovery_system_prompt = new_discovery_prompt

            logger.info("Calling the LLM")
            all_tools = converted_mcp_tools + synthetic_definitions
            ai_message = await resolved_model.chat(messages=messages, options=ChatOptions(tools=all_tools))

            # Accumulate token usage stats
            stats.llm_calls += 1
            usage = resolved_model.get_usage()
            if usage:
                prompt_tokens = getattr(usage, "prompt_tokens", 0) or 0
                completion_tokens = getattr(usage, "completion_tokens", 0) or 0
                stats.tokens.prompt_tokens += prompt_tokens
                stats.tokens.completion_tokens += completion_tokens

            response_messages.append(ai_message)
            messages.append(ai_message)

            logger.debug(f"Assistant: {ai_message}")
            if not ai_message.tool_calls:
                break

            logger.info(f"Executing {len(ai_message.tool_calls)} tool calls")

            # Execute tool calls concurrently, then apply results sequentially
            call_results = await asyncio.gather(
                *(
                    self._execute_tool_call(
                        tool_call,
                        deferred_tool_names=deferred_tool_names,
                        call_synthetic_registry=call_synthetic_registry,
                        loaded_tools=loaded_tools,
                        stats=stats,
                        meta=meta,
                    )
                    for tool_call in ai_message.tool_calls
                )
            )

            result_count = 0
            for result, definitions_changed in call_results:
                if definitions_changed:
                    converted_mcp_tools = tools_from_mcp(loaded_tools)
                    synthetic_definitions = [
                        st.definition for st in call_synthetic_registry.values()
                    ]
                if result:
                    messages.append(result)
                    response_messages.append(result)
                    result_count += 1

            logger.info(f"Added {result_count} tool results")

        else:
            # for-loop exhausted without breaking — the LLM never stopped calling tools
            logger.error("Chat loop exceeded maximum iterations (%d)", DEFAULT_MAX_ITERATIONS)
            raise RuntimeError(
                f"Chat loop exceeded maximum {DEFAULT_MAX_ITERATIONS} iterations. "
                "The LLM may be stuck in a tool-calling loop. "
                "Set MCP_MAX_CHAT_ITERATIONS to adjust the limit."
            )

        logger.debug(f"Final Response: {response_messages[-1].content}")

        # Publish stats so get_stats() returns the result of this call
        self._last_stats = stats

        return response_messages

    async def _rebuild_discovery_state(
        self,
        tool_set: ToolSetConfig | None,
        loaded_tools: list[mcp.Tool],
        base_synthetic_registry: dict[str, SyntheticTool],
    ) -> tuple[list[mcp.Tool], set[str], dict[str, SyntheticTool], str | None]:
        """Rebuild tool discovery state after a tool cache version change.

        Fetches fresh tools, re-partitions, and rebuilds the search index
        while preserving tools that were already loaded via search-tools.

        Args:
            tool_set: Optional toolset filter to apply.
            loaded_tools: Currently loaded MCP tools (includes previously
                discovered tools).
            base_synthetic_registry: The static synthetic tool registry
                (excludes per-call search-tools).

        Returns:
            Tuple of (new_loaded_tools, new_deferred_names, new_call_registry,
            discovery_system_prompt).
        """
        if self._config is None or self._tool_discovery_config is None:
            raise RuntimeError(
                "Tool discovery is enabled but config is not set. "
                "Use McpToolChat.from_config() to enable tool discovery."
            )

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
        new_discovery_prompt: str | None = None

        if deferred_by_server:
            all_deferred = [t for server_tools in deferred_by_server.values() for t in server_tools]
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
            new_discovery_prompt = search_tools_tool.system_prompt
            logger.info(
                f"Rebuilt discovery: {len(new_loaded)} loaded, {len(new_deferred_names)} deferred"
            )

        return new_loaded, new_deferred_names, new_call_registry, new_discovery_prompt

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
        try:
            tool_args = json.loads(tool_call.function.arguments)
        except (json.JSONDecodeError, TypeError) as e:
            logger.warning(f"Malformed tool arguments for '{tool_name}': {e}")
            return ToolResultMessage(
                name=tool_call.function.name,
                tool_call_id=tool_call.id,
                content=f"Error: Malformed arguments for tool '{tool_name}'.",
            )
        try:
            async with self.mcp_client:
                result = await self.mcp_client.call_tool(tool_name, tool_args, meta=meta)
        except ValueError as e:
            logger.warning(f"Tool call validation error: {e}")
            return ToolResultMessage(
                name=tool_call.function.name,
                tool_call_id=tool_call.id,
                content=str(e),
            )
        except Exception as e:
            logger.error(f"Error calling tool '{tool_name}': {e}")
            return ToolResultMessage(
                name=tool_call.function.name,
                tool_call_id=tool_call.id,
                content=f"Error: Tool '{tool_name}' failed to execute.",
            )

        logger.debug(f"Tool Call Result: {result}")

        result_format = os.getenv("TOOL_RESULT_FORMAT", "result")

        # Prefer structuredContent when available (machine-readable format)
        # Note: MCP types use camelCase (structuredContent), mypy stubs may differ
        # Todo: Use structured data from FastMCP - https://gofastmcp.com/clients/tools#structured-results
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
