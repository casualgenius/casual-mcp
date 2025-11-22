import json
from typing import Any

import mcp
import ollama
from ollama import ChatResponse, Client, ResponseError

from casual_mcp.logging import get_logger
from casual_mcp.models.generation_error import GenerationError
from casual_mcp.models.messages import AssistantMessage, ChatMessage
from casual_mcp.providers.abstract_provider import CasualMcpProvider

logger = get_logger("providers.ollama")

def convert_tools(mcp_tools: list[mcp.Tool]) -> list[ollama.Tool]:
    """Convert MCP tools to Ollama-compatible tools."""
    logger.info("Converting MCP tools to Ollama format")

    tools: list[ollama.Tool] = []

    for mcp_tool in mcp_tools:
        if mcp_tool.name and mcp_tool.description:
            tool = ollama.Tool(
                function=ollama.Tool.Function(
                    name=mcp_tool.name,
                    description=mcp_tool.description,
                    parameters=ollama.Tool.Function.Parameters(
                        properties=mcp_tool.inputSchema.get("properties", {}),
                        required=mcp_tool.inputSchema.get("required", []),
                    ),
                )
            )
            tools.append(tool)
        else:
            logger.warning(
                f"Tool missing attributes: name={mcp_tool.name}, description={mcp_tool.description}"
            )

    return tools


def convert_messages(messages: list[ChatMessage]) -> list[ollama.Message]:
    """Convert ChatMessage objects to Ollama messages."""
    if not messages:
        return messages

    logger.info("Converting messages to Ollama format")

    ollama_messages: list[ollama.Message] = []
    for msg in messages:
        match msg.role:
            case "assistant":
                tool_calls = None
                if msg.tool_calls:
                    tool_calls = []
                    for tool_call in msg.tool_calls:
                        tool_calls.append(
                            ollama.Message.ToolCall(
                                function=ollama.Message.ToolCall.Function(
                                    name=tool_call.function.name,
                                    arguments=json.loads(tool_call.function.arguments),
                                )
                            )
                        )
                ollama_messages.append(
                    ollama.Message(role="assistant", content=msg.content, tool_calls=tool_calls)
                )
            case "system":
                ollama_messages.append(ollama.Message(role="system", content=msg.content))
            case "tool":
                ollama_messages.append(ollama.Message(role="tool", content=msg.content))
            case "user":
                ollama_messages.append(ollama.Message(role="user", content=msg.content))

    return ollama_messages


def convert_tool_calls(response_tool_calls: list[ollama.Message.ToolCall]) -> list[dict[str, Any]]:
    """Convert Ollama tool calls into a format used by the application."""
    tool_calls = []

    for i, tool in enumerate(response_tool_calls):
        logger.debug(f"Convert Tool Call: {tool}")

        tool_calls.append(
            {
                "id": str(i),
                "type": "function",
                "function": {
                    "name": tool.function.name,
                    "arguments": json.dumps(tool.function.arguments),
                },
            }
        )

    return tool_calls


class OllamaProvider(CasualMcpProvider):
    def __init__(self, model: str, endpoint: str = None):
        self.model = model
        self.client = Client(
            host=endpoint,
        )

    async def generate(
        self,
        messages: list[ChatMessage],
        tools: list[mcp.Tool]
    ) -> ChatMessage:
        logger.info("Start Generating")
        logger.debug(f"Model: {self.model}")

        # Convert tools to Ollama format
        converted_tools = convert_tools(tools)
        logger.debug(f"Converted Tools: {converted_tools}")
        logger.info(f"Adding {len(converted_tools)} tools")

        # Convert Messages to Ollama format
        converted_messages = convert_messages(messages)
        logger.debug(f"Converted Messages: {converted_messages}")

        # Call Ollama API
        try:
            response: ChatResponse = self.client.chat(
                model=self.model, messages=converted_messages, stream=False, tools=converted_tools
            )
        except ResponseError as e:
            if e.status_code == 404:
                logger.info(f"Model {self.model} not found, pulling")
                self.client.pull(self.model)
                return self.generate(messages, tools)

            raise e
        except Exception as e:
            logger.warning(f"Error in Generation: {e}")
            raise GenerationError(str(e))

        # Convert any tool calls
        tool_calls = []
        if hasattr(response.message, "tool_calls") and response.message.tool_calls:
            logger.debug(f"Assistant requested {len(response.message.tool_calls)} tool calls")
            tool_calls = convert_tool_calls(response.message.tool_calls)

        return AssistantMessage(content=response.message.content, tool_calls=tool_calls)
