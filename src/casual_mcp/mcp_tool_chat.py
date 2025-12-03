import json
import os
from typing import Any

from casual_llm import (
    AssistantToolCall,
    ChatMessage,
    LLMProvider,
    SystemMessage,
    ToolResultMessage,
    UserMessage,
)
from fastmcp import Client

from casual_mcp.convert_tools import tools_from_mcp
from casual_mcp.logging import get_logger
from casual_mcp.tool_cache import ToolCache
from casual_mcp.utils import format_tool_call_result

logger = get_logger("mcp_tool_chat")
sessions: dict[str, list[ChatMessage]] = {}


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
        provider: LLMProvider,
        system: str | None = None,
        tool_cache: ToolCache | None = None,
    ):
        self.provider = provider
        self.mcp_client = mcp_client
        self.system = system
        self.tool_cache = tool_cache or ToolCache(mcp_client)
        self._tool_cache_version = -1

    @staticmethod
    def get_session(session_id: str) -> list[ChatMessage] | None:
        global sessions
        return sessions.get(session_id)

    async def generate(self, prompt: str, session_id: str | None = None) -> list[ChatMessage]:
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
        response = await self.chat(messages=messages)

        # Add responses to session
        if session_id:
            add_messages_to_session(session_id, response)

        return response

    async def chat(self, messages: list[ChatMessage]) -> list[ChatMessage]:
        tools = await self.tool_cache.get_tools()

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
            ai_message = await self.provider.chat(messages=messages, tools=tools_from_mcp(tools))

            # Add the assistant's message
            response_messages.append(ai_message)
            messages.append(ai_message)

            print("Assistant:")
            print(ai_message)
            if not ai_message.tool_calls:
                break

            if ai_message.tool_calls and len(ai_message.tool_calls) > 0:
                logger.info(f"Executing {len(ai_message.tool_calls)} tool calls")
                result_count = 0
                for tool_call in ai_message.tool_calls:
                    try:
                        result = await self.execute(tool_call)
                    except Exception as e:
                        logger.error(e)
                        return messages
                    if result:
                        messages.append(result)
                        response_messages.append(result)
                        result_count = result_count + 1

                logger.info(f"Added {result_count} tool results")

        logger.debug(f"Final Response: {response_messages[-1].content}")

        return response_messages

    async def execute(self, tool_call: AssistantToolCall) -> ToolResultMessage:
        tool_name = tool_call.function.name
        tool_args = json.loads(tool_call.function.arguments)
        try:
            async with self.mcp_client:
                result = await self.mcp_client.call_tool(tool_name, tool_args)
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
        # Extract text content from result (handle both TextContent and other content types)
        content_item = result.content[0]
        if hasattr(content_item, "text"):
            content_text = content_item.text
        else:
            # Handle non-text content (e.g., ImageContent)
            content_text = f"[Non-text content: {type(content_item).__name__}]"
        content = format_tool_call_result(tool_call, content_text, style=result_format)

        return ToolResultMessage(
            name=tool_call.function.name,
            tool_call_id=tool_call.id,
            content=content,
        )
