import mcp
from casual_llm import Tool

from casual_mcp.logging import get_logger

logger = get_logger("convert_tools")

# MCP format converters (for interop with MCP libraries)
def tool_from_mcp(mcp_tool: mcp.Tool) -> Tool:
    """
    Convert an MCP Tool to casual-llm Tool format.

    Args:
        mcp_tool: MCP Tool object (from mcp library)

    Returns:
        casual-llm Tool instance

    Raises:
        ValueError: If MCP tool is missing required fields

    Examples:
        >>> # Assuming mcp_tool is an MCP Tool object
        >>> # tool = tool_from_mcp(mcp_tool)
        >>> # assert tool.name == mcp_tool.name
        pass
    """
    if not mcp_tool.name or not mcp_tool.description:
        raise ValueError(
            f"MCP tool missing required fields: "
            f"name={mcp_tool.name}, description={mcp_tool.description}"
        )

    input_schema = getattr(mcp_tool, "inputSchema", {})
    if not isinstance(input_schema, dict):
        input_schema = {}

    return Tool.from_input_schema(
        name=mcp_tool.name,
        description=mcp_tool.description,
        input_schema=input_schema
    )


def tools_from_mcp(mcp_tools: list[mcp.Tool]) -> list[Tool]:
    """
    Convert multiple MCP Tools to casual-llm format.

    Args:
        mcp_tools: List of MCP Tool objects

    Returns:
        List of casual-llm Tool instances

    Examples:
        >>> # tools = tools_from_mcp(mcp_tool_list)
        >>> # assert len(tools) == len(mcp_tool_list)
        pass
    """
#    logger.debug(f"Converting {len(mcp_tools)} MCP tools to casual-llm format")
    tools = []

    for mcp_tool in mcp_tools:
        try:
            tool = tool_from_mcp(mcp_tool)
            tools.append(tool)
        except ValueError as e:
            logger.warning(f"Skipping invalid MCP tool: {e}")

    return tools
