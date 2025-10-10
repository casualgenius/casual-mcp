from typing import Any

import mcp
from openai import OpenAI
from openai.types.chat import (
    ChatCompletionAssistantMessageParam,
    ChatCompletionMessageParam,
    ChatCompletionMessageToolCall,
    ChatCompletionMessageToolCallParam,
    ChatCompletionSystemMessageParam,
    ChatCompletionToolMessageParam,
    ChatCompletionToolParam,
    ChatCompletionUserMessageParam,
)

from casual_mcp.logging import get_logger
from casual_mcp.models.generation_error import GenerationError
from casual_mcp.models.messages import AssistantMessage, ChatMessage
from casual_mcp.models.tool_call import AssistantToolCall, AssistantToolCallFunction
from casual_mcp.providers.abstract_provider import CasualMcpProvider

logger = get_logger("providers.openai")

MessageType = dict[str, Any]


def convert_tools(mcp_tools: list[mcp.Tool]) -> list[ChatCompletionToolParam]:
    logger.info("Converting MCP tools to OpenAI format")
    tools = []

    # Convert all the tools
    for i, mcp_tool in enumerate(mcp_tools):
        if mcp_tool.name and mcp_tool.description:
            # Convert the tool
            tool = convert_tool(mcp_tool)
            tools.append(tool)
        else:
            logger.warning(
                f"Tool missing attributes: name = {mcp_tool.name}, description = {mcp_tool.description}"  # noqa: E501
            )

    return tools


def convert_tool(mcp_tool: mcp.Tool) -> ChatCompletionToolParam | None:
    logger.debug(f"Converting: {mcp_tool.name}")
    tool = {
        "type": "function",
        "function": {
            "name": mcp_tool.name,
            "description": mcp_tool.description,
            "parameters": {
                "type": "object",
                "properties": mcp_tool.inputSchema["properties"],
                "required": mcp_tool.inputSchema.get("required", []),
            },
        },
    }
    return ChatCompletionToolParam(**tool)


def convert_messages(messages: list[ChatMessage]) -> list[ChatCompletionMessageParam]:
    if not messages:
        return messages

    logger.info("Converting messages to OpenAI format")

    openai_messages: list[ChatCompletionMessageParam] = []
    for msg in messages:
        match msg.role:
            case "assistant":
                tool_calls = None
                if msg.tool_calls:
                    tool_calls = []
                    for tool_call in msg.tool_calls:
                        function = {
                            "name": tool_call.function.name,
                            "arguments": tool_call.function.arguments
                        }
                        tool_calls.append(
                            ChatCompletionMessageToolCallParam(
                                id=tool_call.id,
                                type=tool_call.type,
                                function=function
                            )
                        )
                openai_messages.append(
                    ChatCompletionAssistantMessageParam(
                        role="assistant", content=msg.content, tool_calls=tool_calls
                    )
                )
            case "system":
                openai_messages.append(
                    ChatCompletionSystemMessageParam(role="system", content=msg.content)
                )
            case "tool":
                openai_messages.append(
                    ChatCompletionToolMessageParam(
                        role="tool", content=msg.content, tool_call_id=msg.tool_call_id
                    )
                )
            case "user":
                openai_messages.append(
                    ChatCompletionUserMessageParam(role="user", content=msg.content)
                )

    return openai_messages


def convert_tool_calls(
    response_tool_calls: list[ChatCompletionMessageToolCall],
) -> list[AssistantToolCall]:
    tool_calls = []

    for i, tool in enumerate(response_tool_calls):
        logger.debug(f"Convert Tool: {tool}")

        # Create the tool object in the format expected by client.py
        tool_call = AssistantToolCall(
            id=tool.id,
            function=AssistantToolCallFunction(
                name=tool.function.name,
                type="function",
                arguments=tool.function.arguments
            )
        )
        tool_calls.append(tool_call)

    return tool_calls


class OpenAiProvider(CasualMcpProvider):
    def __init__(self, model: str, api_key: str, tools: list[mcp.Tool], endpoint: str = None):

        # Convert MCP Tools to OpenAI format
        self.tools = convert_tools(tools)
        logger.debug(f"Converted Tools: {self.tools}")
        logger.info(f"Adding {len(self.tools)} tools")
        self.model = model
        self.client = OpenAI(
            base_url=endpoint,
            api_key=api_key,
        )

    async def generate(
        self,
        messages: list[ChatMessage],
        tools: list[mcp.Tool]
    ) -> AssistantMessage:
        logger.info("Start Generating")
        logger.debug(f"Model: {self.model}")

        # Convert Messages to OpenAI format
        converted_messages = convert_messages(messages)
        logger.debug(f"Converted Messages: {converted_messages}")

        # Call OpenAi API
        try:
            logger.info(f"Calling LLM with {len(converted_messages)} messages")
            result = self.client.chat.completions.create(
                model=self.model, messages=converted_messages, tools=self.tools
            )

            response = result.choices[0]
        except Exception as e:
            logger.warning(f"Error in Generation: {e}")
            raise GenerationError(str(e))

        logger.info(f"LLM Response received")
        logger.debug(response)

        # Convert any tool calls
        tool_calls = None
        if hasattr(response.message, "tool_calls") and response.message.tool_calls:
            logger.debug(f"Assistant requested {len(response.message.tool_calls)} tool calls")
            tool_calls = convert_tool_calls(response.message.tool_calls)
            logger.debug(f"Converted {len(tool_calls)} tool calls")

        return AssistantMessage(content=response.message.content, tool_calls=tool_calls)

    def update_tools(self, tools: list[mcp.Tool]) -> None:
        self.tools = convert_tools(tools)
        logger.info(f"Provider tool catalogue refreshed with {len(self.tools)} tools")
