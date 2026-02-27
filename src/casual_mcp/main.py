import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from casual_llm import ChatMessage
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from casual_mcp import McpToolChat
from casual_mcp.logging import configure_logging, get_logger
from casual_mcp.models.config import Config
from casual_mcp.models.toolset_config import ToolSetConfig
from casual_mcp.tool_filter import ToolSetValidationError
from casual_mcp.utils import load_config

# Load environment variables
load_dotenv()

# Configure logging
configure_logging(os.getenv("LOG_LEVEL", "INFO"))
logger = get_logger("main")

default_system_prompt = """You are a helpful assistant.

You have access to up-to-date information through the tools, but you must never mention that tools were used.

Respond naturally and confidently, as if you already know all the facts.

**Never mention your knowledge cutoff, training data, or when you were last updated.**

You must not speculate or guess about dates — if a date is given to you by a tool, assume it is correct and respond accordingly without disclaimers.

Always present information as current and factual.
"""


class AppState:
    """Holds application-wide state initialised during the lifespan."""

    config: Config
    chat_instance: McpToolChat


state = AppState()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Initialise shared resources on startup; clean up on shutdown."""
    state.config = load_config("casual_mcp_config.json")
    state.chat_instance = McpToolChat.from_config(state.config, system=default_system_prompt)
    async with state.chat_instance:
        logger.info("Application started")
        yield
        logger.info("Application shut down")


app = FastAPI(lifespan=lifespan)


class ChatRequest(BaseModel):
    model: str = Field(title="Model to use")
    system_prompt: str | None = Field(default=None, title="System Prompt to use")
    messages: list[ChatMessage] = Field(title="Previous messages to supply to the LLM")
    include_stats: bool = Field(default=False, title="Include usage statistics in response")
    tool_set: str | None = Field(default=None, title="Name of toolset to use")


def resolve_tool_set(tool_set_name: str | None) -> ToolSetConfig | None:
    """Resolve a tool set name to its configuration.

    Args:
        tool_set_name: Name of the tool set, or None

    Returns:
        ToolSetConfig if found, None if tool_set_name is None

    Raises:
        HTTPException: If tool set name is provided but not found
    """
    if tool_set_name is None:
        return None

    if tool_set_name not in state.config.tool_sets:
        raise HTTPException(
            status_code=400,
            detail=f"Toolset '{tool_set_name}' not found. "
            f"Available: {list(state.config.tool_sets.keys())}",
        )

    return state.config.tool_sets[tool_set_name]


@app.post("/chat")
async def chat(req: ChatRequest) -> dict[str, Any]:
    tool_set_config = resolve_tool_set(req.tool_set)

    try:
        messages = await state.chat_instance.chat(
            req.messages,
            tool_set=tool_set_config,
            model=req.model,
            system=req.system_prompt,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ToolSetValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error in /chat: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

    if not messages:
        error_result: dict[str, Any] = {"messages": [], "response": ""}
        if req.include_stats:
            error_result["stats"] = state.chat_instance.get_stats()
        raise HTTPException(
            status_code=500,
            detail={"error": "No response generated", **error_result},
        )

    result: dict[str, Any] = {"messages": messages, "response": messages[-1].content}
    if req.include_stats:
        result["stats"] = state.chat_instance.get_stats()
    return result


@app.get("/toolsets")
async def list_toolsets() -> dict[str, dict[str, Any]]:
    """List all available toolsets."""
    return {
        name: {
            "description": ts.description,
            "servers": list(ts.servers.keys()),
        }
        for name, ts in state.config.tool_sets.items()
    }
