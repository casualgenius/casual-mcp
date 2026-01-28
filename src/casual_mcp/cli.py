import asyncio
from typing import Any

import mcp
import typer
import uvicorn
from fastmcp import Client
from rich.console import Console
from rich.table import Table

from casual_mcp.models.mcp_server_config import RemoteServerConfig
from casual_mcp.utils import load_config, load_mcp_client

app = typer.Typer()
console = Console()


@app.command()
def serve(host: str = "0.0.0.0", port: int = 8000, reload: bool = True) -> None:
    """
    Start the Casual MCP API server.
    """
    uvicorn.run("casual_mcp.main:app", host=host, port=port, reload=reload, app_dir="src")


@app.command()
def servers() -> None:
    """
    Return a table of all configured servers
    """
    config = load_config("casual_mcp_config.json")
    table = Table("Name", "Type", "Command / Url", "Env")

    for name, server in config.servers.items():
        server_type = "stdio"
        if isinstance(server, RemoteServerConfig):
            server_type = "remote"

        path = ""
        if isinstance(server, RemoteServerConfig):
            path = server.url
        else:
            path = f"{server.command} {' '.join(server.args)}"
        env = ""

        table.add_row(name, server_type, path, env)

    console.print(table)


@app.command()
def models() -> None:
    """
    Return a table of all configured models
    """
    config = load_config("casual_mcp_config.json")
    table = Table("Name", "Provider", "Model", "Endpoint")

    for name, model in config.models.items():
        endpoint = model.endpoint or ""
        table.add_row(name, model.provider, model.model, str(endpoint))

    console.print(table)


@app.command()
def tools() -> None:
    config = load_config("casual_mcp_config.json")
    mcp_client = load_mcp_client(config)
    table = Table("Name", "Description")
    # async with mcp_client:
    tools = asyncio.run(get_tools(mcp_client))
    for tool in tools:
        table.add_row(tool.name, tool.description)
    console.print(table)


async def get_tools(client: Client[Any]) -> list[mcp.Tool]:
    async with client:
        return await client.list_tools()


if __name__ == "__main__":
    app()
