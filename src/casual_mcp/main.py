import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from casual_mcp import McpToolChat
from casual_mcp.logging import configure_logging, get_logger
from casual_mcp.models.messages import ChatMessage
from casual_mcp.providers.provider_factory import ProviderFactory
from casual_mcp.utils import load_config, load_mcp_client, render_system_prompt

load_dotenv()

# Configure logging
configure_logging(os.getenv("LOG_LEVEL", 'INFO'))
logger = get_logger("main")

config = load_config("casual_mcp_config.json")
mcp_client = load_mcp_client(config)
provider_factory = ProviderFactory(mcp_client)

app = FastAPI()

default_system_prompt = """You are a helpful assistant.

You have access to up-to-date information through the tools, but you must never mention that tools were used.

Respond naturally and confidently, as if you already know all the facts.

**Never mention your knowledge cutoff, training data, or when you were last updated.**

You must not speculate or guess about dates — if a date is given to you by a tool, assume it is correct and respond accordingly without disclaimers.

Always present information as current and factual.
"""


class GenerateRequest(BaseModel):
    session_id: str | None = Field(
        default=None, title="Session to use"
    )
    model: str = Field(
        title="Model to user"
    )
    system_prompt: str | None = Field(
        default=None, title="System Prompt to use"
    )
    prompt: str = Field(
        title="User Prompt"
    )


class ChatRequest(BaseModel):
    model: str = Field(
        title="Model to user"
    )
    system_prompt: str | None = Field(
        default=None, title="System Prompt to use"
    )
    messages: list[ChatMessage] = Field(
        title="Previous messages to supply to the LLM"
    )

sys.path.append(str(Path(__file__).parent.resolve()))




@app.post("/chat")
async def chat(req: ChatRequest):
    chat = await get_chat(req.model, req.system_prompt)
    messages = await chat.chat(req.messages)

    return {
        "messages": messages,
        "response": messages[len(messages) - 1].content
    }


@app.post("/generate")
async def generate(req: GenerateRequest):
    chat = await get_chat(req.model, req.system_prompt)
    messages = await chat.generate(
        req.prompt,
        req.session_id
    )

    return {
        "messages": messages,
        "response": messages[len(messages) - 1].content
    }


@app.get("/generate/session/{session_id}")
async def get_generate_session(session_id):
    session = McpToolChat.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    return session


async def get_chat(model: str, system: str | None = None) -> McpToolChat:
    # Get Provider from Model Config
    model_config = config.models[model]
    provider = await provider_factory.get_provider(model, model_config)

    # Get the system prompt
    if not system:
        if (model_config.template):
            async with mcp_client:
                system = render_system_prompt(
                    f"{model_config.template}.j2",
                    await mcp_client.list_tools()
                )
        else:
            system = default_system_prompt

    return McpToolChat(mcp_client, provider, system)
