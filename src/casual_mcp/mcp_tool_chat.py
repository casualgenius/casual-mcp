import json
import os

from fastmcp import Client

from casual_mcp.logging import get_logger
from casual_mcp.models.messages import (
    ChatMessage,
    SystemMessage,
    ToolResultMessage,
    UserMessage,
)
from casual_mcp.models.tool_call import AssistantToolCall
from casual_mcp.providers.provider_factory import LLMProvider
from casual_mcp.utils import format_tool_call_result

logger = get_logger("mcp_tool_chat")
sessions: dict[str, list[ChatMessage]] = {}


def get_session_messages(session_id: str | None):
    global sessions

    if not sessions.get(session_id):
        logger.info(f"Starting new session {session_id}")
        sessions[session_id] = []
    else:
        logger.info(
            f"Retrieving session {session_id} of length {len(sessions[session_id])}"
        )
    return sessions[session_id].copy()


def add_messages_to_session(session_id: str, messages: list[ChatMessage]):
    global sessions
    sessions[session_id].extend(messages.copy())


class McpToolChat:
    def __init__(self, mcp_client: Client, provider: LLMProvider, system: str = None):
        self.provider = provider
        self.mcp_client = mcp_client
        self.system = system

    @staticmethod
    def get_session(session_id) -> list[ChatMessage] | None:
        global sessions
        return sessions.get(session_id)

    async def generate(
        self,
        prompt: str,
        session_id: str | None = None
    ) -> list[ChatMessage]:
        # Fetch the session if we have a session ID
        if session_id:
            messages = get_session_messages(session_id)
        else:
            messages: list[ChatMessage] = []

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


    async def chat(
        self,
        messages: list[ChatMessage]
    ) -> list[ChatMessage]:
        # Add a system message if required
        has_system_message = any(message.role == 'system' for message in messages)
        if self.system and not has_system_message:
            # Insert the system message at the start of the messages
            logger.debug(f"Adding System Message")
            messages.insert(0, SystemMessage(content=self.system))

        logger.info("Start Chat")
        async with self.mcp_client:
            tools = await self.mcp_client.list_tools()

        response_messages: list[ChatMessage] = []
        while True:
            logger.info("Calling the LLM")
            ai_message = await self.provider.generate(messages, tools)

            # Add the assistant's message
            response_messages.append(ai_message)
            messages.append(ai_message)

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


    async def execute(self, tool_call: AssistantToolCall):
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

        result_format = os.getenv('TOOL_RESULT_FORMAT', 'result')
        content = format_tool_call_result(tool_call, result.content[0].text, style=result_format)

        return ToolResultMessage(
            name=tool_call.function.name,
            tool_call_id=tool_call.id,
            content=content,
        )
