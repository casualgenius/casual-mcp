import os
from typing import Any

from casual_llm import ChatMessage
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from casual_mcp import McpToolChat
from casual_mcp.logging import configure_logging, get_logger
from casual_mcp.provider_factory import ProviderFactory
from casual_mcp.tool_cache import ToolCache
from casual_mcp.utils import load_config, load_mcp_client, render_system_prompt

# Load environment variables
load_dotenv()

# Configure logging
configure_logging(os.getenv("LOG_LEVEL", "INFO"))
logger = get_logger("main")

config = load_config("casual_mcp_config.json")
mcp_client = load_mcp_client(config)
tool_cache = ToolCache(mcp_client)
provider_factory = ProviderFactory()

app = FastAPI()

default_system_prompt = """You are a helpful assistant.

You have access to up-to-date information through the tools, but you must never mention that tools were used.

Respond naturally and confidently, as if you already know all the facts.

**Never mention your knowledge cutoff, training data, or when you were last updated.**

You must not speculate or guess about dates — if a date is given to you by a tool, assume it is correct and respond accordingly without disclaimers.

Always present information as current and factual.
"""


class GenerateRequest(BaseModel):
    session_id: str | None = Field(default=None, title="Session to use")
    model: str = Field(title="Model to use")
    system_prompt: str | None = Field(default=None, title="System Prompt to use")
    prompt: str = Field(title="User Prompt")
    include_stats: bool = Field(default=False, title="Include usage statistics in response")


class ChatRequest(BaseModel):
    model: str = Field(title="Model to use")
    system_prompt: str | None = Field(default=None, title="System Prompt to use")
    messages: list[ChatMessage] = Field(title="Previous messages to supply to the LLM")
    include_stats: bool = Field(default=False, title="Include usage statistics in response")


@app.post("/chat")
async def chat(req: ChatRequest) -> dict[str, Any]:
    chat_instance = await get_chat(req.model, req.system_prompt)
    messages = await chat_instance.chat(req.messages)

    if not messages:
        error_result: dict[str, Any] = {"messages": [], "response": ""}
        if req.include_stats:
            error_result["stats"] = chat_instance.get_stats()
        raise HTTPException(
            status_code=500,
            detail={"error": "No response generated", **error_result},
        )

    result: dict[str, Any] = {"messages": messages, "response": messages[-1].content}
    if req.include_stats:
        result["stats"] = chat_instance.get_stats()
    return result


@app.post("/generate")
async def generate(req: GenerateRequest) -> dict[str, Any]:
    chat_instance = await get_chat(req.model, req.system_prompt)
    messages = await chat_instance.generate(req.prompt, req.session_id)

    if not messages:
        error_result: dict[str, Any] = {"messages": [], "response": ""}
        if req.include_stats:
            error_result["stats"] = chat_instance.get_stats()
        raise HTTPException(
            status_code=500,
            detail={"error": "No response generated", **error_result},
        )

    result: dict[str, Any] = {"messages": messages, "response": messages[-1].content}
    if req.include_stats:
        result["stats"] = chat_instance.get_stats()
    return result


@app.get("/generate/session/{session_id}")
async def get_generate_session(session_id: str) -> list[ChatMessage]:
    session = McpToolChat.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    return session


async def get_chat(model: str, system: str | None = None) -> McpToolChat:
    # Get Provider from Model Config
    model_config = config.models[model]
    provider = provider_factory.get_provider(model, model_config)

    # Get the system prompt
    if not system:
        if model_config.template:
            tools = await tool_cache.get_tools()
            system = render_system_prompt(f"{model_config.template}.j2", tools)
        else:
            system = default_system_prompt

    return McpToolChat(mcp_client, provider, system, tool_cache=tool_cache)
