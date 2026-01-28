import json
from pathlib import Path
from typing import Any

import mcp
from casual_llm import AssistantToolCall
from fastmcp import Client
from jinja2 import Environment, FileSystemLoader
from pydantic import ValidationError

from casual_mcp.models.config import Config


def load_mcp_client(config: Config) -> Client[Any]:
    servers = {key: value.model_dump() for key, value in config.servers.items()}
    return Client(servers)


def load_config(path: str | Path) -> Config:
    path = Path(path)

    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    try:
        with path.open("r", encoding="utf-8") as f:
            raw_data = json.load(f)

        return Config(**raw_data)
    except ValidationError as ve:
        raise ValueError(f"Invalid config:\n{ve}") from ve
    except json.JSONDecodeError as je:
        raise ValueError(f"Could not parse config JSON:\n{je}") from je


def format_tool_call_result(
    tool_call: AssistantToolCall,
    result: str,
    style: str = "function_result",
    include_id: bool = False,
) -> str:
    """
    Format a tool call and result into a prompt-friendly string.

    Supported styles:
        - "result": Only the result text
        - "function_result": function → result
        - "function_args_result": function(args) → result

    Include ID to add the tool call ID above the result

    Args:
        tool_call (AssistantToolCall): Tool call
        result (str): Output of the tool
        style (str): One of the supported formatting styles
        include_id (bool): Whether to include the tool call ID

    Returns:
        str: Formatted content string
    """
    func_name = tool_call.function.name
    try:
        args = json.loads(tool_call.function.arguments)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"Malformed JSON in tool call arguments for '{func_name}': {e}. "
            f"Payload: {tool_call.function.arguments!r}"
        ) from e

    if style == "result":
        result_str = result

    elif style == "function_result":
        result_str = f"{func_name} → {result}"

    elif style == "function_args_result":
        arg_string = ", ".join(f"{k}={repr(v)}" for k, v in args.items())
        result_str = f"{func_name}({arg_string}) → {result}"

    else:
        raise ValueError(f"Unsupported style: {style}")

    if include_id:
        return f"ID: {tool_call.id}\n{result_str}"

    return result_str


def render_system_prompt(
    template_name: str, tools: list[mcp.Tool], extra: dict[str, Any] | None = None
) -> str:
    """
    Renders a system prompt template with tool definitions.

    :param template_name: e.g. 'stealth_tools_prompt.j2'
    :param tools: list of dicts with 'name' and 'description' (at minimum)
    :param extra: optional additional variables for template
    :return: rendered system prompt
    """
    TEMPLATE_DIR = Path("prompt-templates").resolve()
    env = Environment(loader=FileSystemLoader(TEMPLATE_DIR), autoescape=False)
    template = env.get_template(template_name)
    context = {"tools": tools}
    if extra:
        context.update(extra)
    return template.render(**context)
