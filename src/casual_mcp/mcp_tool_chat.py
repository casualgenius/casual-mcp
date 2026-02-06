import json
import os
from typing import Any

from casual_llm import (
    AssistantToolCall,
    ChatMessage,
    Model,
    SystemMessage,
    ToolResultMessage,
    UserMessage,
)
from fastmcp import Client

from casual_mcp.convert_tools import tools_from_mcp
from casual_mcp.logging import get_logger
from casual_mcp.models.chat_stats import ChatStats
from casual_mcp.models.toolset_config import ToolSetConfig
from casual_mcp.tool_cache import ToolCache
from casual_mcp.tool_filter import filter_tools_by_toolset
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
    ):
        self.model = model
        self.mcp_client = mcp_client
        self.system = system
        self.tool_cache = tool_cache or ToolCache(mcp_client)
        self.server_names = server_names or set()
        self._tool_cache_version = -1
        self._last_stats: ChatStats | None = None

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

    def _extract_server_from_tool_name(self, tool_name: str) -> str:
        """
        Extract server name from a tool name.

        With multiple servers, fastmcp prefixes tools as "serverName_toolName".
        With a single server, tools are not prefixed.

        Returns the server name or "default" if it cannot be determined.
        """
        if "_" in tool_name:
            return tool_name.split("_", 1)[0]
        return "default"

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

        # Add a system message if required
        has_system_message = any(message.role == "system" for message in messages)
        if self.system and not has_system_message:
            # Insert the system message at the start of the messages
            logger.debug("Adding System Message")
            messages.insert(0, SystemMessage(content=self.system))

        logger.info("Start Chat")
        response_messages: list[ChatMessage] = []
        while True:
            logger.info("Calling the LLM")
            ai_message = await self.model.chat(messages=messages, tools=tools_from_mcp(tools))

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
                # Track tool call stats
                tool_name = tool_call.function.name
                self._last_stats.tool_calls.by_tool[tool_name] = (
                    self._last_stats.tool_calls.by_tool.get(tool_name, 0) + 1
                )
                server_name = self._extract_server_from_tool_name(tool_name)
                self._last_stats.tool_calls.by_server[server_name] = (
                    self._last_stats.tool_calls.by_server.get(server_name, 0) + 1
                )

                try:
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
