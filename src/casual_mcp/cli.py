import asyncio
import gc
import json
import warnings
from pathlib import Path
from typing import Any

import mcp
import questionary
import typer
import uvicorn
from fastmcp import Client
from rich.console import Console
from rich.table import Table

from casual_mcp.models.mcp_server_config import RemoteServerConfig
from casual_mcp.models.toolset_config import ExcludeSpec, ToolSpec
from casual_mcp.tool_filter import extract_server_and_tool
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
def clients() -> None:
    """
    Return a table of all configured clients
    """
    config = load_config("casual_mcp_config.json")
    table = Table("Name", "Provider", "Base URL", "Timeout")

    for name, client in config.clients.items():
        base_url = client.base_url or "(default)"
        table.add_row(name, client.provider, base_url, str(client.timeout))

    console.print(table)


@app.command()
def models() -> None:
    """
    Return a table of all configured models
    """
    config = load_config("casual_mcp_config.json")
    table = Table("Name", "Client", "Model", "Template")

    for name, model in config.models.items():
        template = model.template or ""
        table.add_row(name, model.client, model.model, template)

    console.print(table)


@app.command()
def tools() -> None:
    config = load_config("casual_mcp_config.json")
    mcp_client = load_mcp_client(config)
    table = Table("Name", "Description")
    tool_list = run_async_with_cleanup(get_tools_and_cleanup(mcp_client))
    for tool in tool_list:
        table.add_row(tool.name, tool.description)
    console.print(table)


def run_async_with_cleanup(coro: Any) -> Any:
    """Run async coroutine with proper subprocess cleanup.

    This wrapper filters/ignores the "Event loop is closed" warning that occurs
    when subprocess transports don't finish cleanup before the event loop closes.
    It also forces gc.collect() after execution to help clean up remaining transports.
    """
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="Event loop is closed")
        try:
            return asyncio.run(coro)
        finally:
            # Force garbage collection to clean up any remaining transports
            gc.collect()


async def get_tools_and_cleanup(client: Client[Any]) -> list[mcp.Tool]:
    """Get tools and ensure proper cleanup to avoid subprocess warnings."""
    try:
        async with client:
            return await client.list_tools()
    finally:
        # Give transports time to close cleanly
        await asyncio.sleep(0.1)


def _build_server_tool_map(tools: list[mcp.Tool], server_names: set[str]) -> dict[str, list[str]]:
    """Build a mapping of server names to their tool names."""
    server_tools: dict[str, list[str]] = {s: [] for s in server_names}
    for tool in tools:
        server_name, base_name = extract_server_and_tool(tool.name, server_names)
        if server_name in server_tools:
            server_tools[server_name].append(base_name)
    return server_tools


def _format_tool_spec(spec: ToolSpec) -> str:
    """Format a tool spec for display.

    Note: Brackets are escaped for Rich console output.
    """
    if spec is True:
        return "\\[all tools]"
    elif isinstance(spec, list):
        return ", ".join(spec)
    elif isinstance(spec, ExcludeSpec):
        return f"\\[all except: {', '.join(spec.exclude)}]"
    return str(spec)


@app.command()
def toolsets() -> None:
    """Interactively manage toolsets - create, edit, and delete."""
    config_path = Path("casual_mcp_config.json")

    while True:
        config = load_config(config_path)

        # Build menu choices
        choices: list[Any] = []

        if config.tool_sets:
            for name, ts in config.tool_sets.items():
                servers = ", ".join(ts.servers.keys()) or "no servers"
                desc = ts.description[:40] + "..." if len(ts.description) > 40 else ts.description
                display = f"{name} - {desc} ({servers})"
                choices.append(questionary.Choice(title=display, value=name))

            choices.append(questionary.Separator())

        choices.append(questionary.Choice(title="➕ Create new toolset", value="__create__"))
        choices.append(questionary.Choice(title="❌ Exit", value="__exit__"))

        selection = questionary.select(
            "Toolsets:" if config.tool_sets else "No toolsets configured:",
            choices=choices,
        ).ask()

        if selection is None or selection == "__exit__":
            return

        if selection == "__create__":
            _create_toolset(config_path)
            continue

        # Selected an existing toolset - show actions
        _toolset_actions(config_path, selection)


def _create_toolset(config_path: Path) -> None:
    """Prompt for name and create a new toolset."""
    config = load_config(config_path)

    name = questionary.text("Toolset name:").ask()
    if not name:
        return

    if name in config.tool_sets:
        console.print(f"[red]Toolset '{name}' already exists[/red]")
        return

    _interactive_toolset_edit(config_path, config, name, is_new=True)


def _toolset_actions(config_path: Path, name: str) -> None:
    """Show actions for an existing toolset."""
    config = load_config(config_path)
    ts = config.tool_sets.get(name)

    if not ts:
        return

    # Show toolset details
    console.print(f"\n[bold]{name}[/bold]")
    console.print(f"Description: {ts.description}")
    console.print("Servers:")
    for server, spec in ts.servers.items():
        console.print(f"  {server}: {_format_tool_spec(spec)}")
    console.print()

    action = questionary.select(
        "Action:",
        choices=[
            questionary.Choice(title="✏️  Edit", value="edit"),
            questionary.Choice(title="🗑️  Delete", value="delete"),
            questionary.Choice(title="← Back", value="back"),
        ],
    ).ask()

    if action is None or action == "back":
        return

    if action == "edit":
        _interactive_toolset_edit(config_path, config, name, is_new=False)
    elif action == "delete":
        _delete_toolset(config_path, name)


def _delete_toolset(config_path: Path, name: str) -> None:
    """Delete a toolset after confirmation."""
    confirmed = questionary.confirm(f"Delete toolset '{name}'?", default=False).ask()
    if not confirmed:
        return

    with config_path.open("r", encoding="utf-8") as f:
        raw = json.load(f)

    # Check if tool_sets exists and contains the toolset
    if "tool_sets" not in raw:
        console.print("[red]No toolsets found in config[/red]")
        return

    if name not in raw["tool_sets"]:
        console.print(f"[red]Toolset '{name}' not found in config[/red]")
        return

    del raw["tool_sets"][name]

    # Remove tool_sets key if empty
    if not raw["tool_sets"]:
        del raw["tool_sets"]

    with config_path.open("w", encoding="utf-8") as f:
        json.dump(raw, f, indent=4)

    console.print(f"[green]Deleted toolset '{name}'[/green]")


def _format_server_status(server: str, spec: ToolSpec | None, tool_count: int) -> str:
    """Format server status for display in the menu."""
    if spec is None:
        return f"{server} ({tool_count} tools) - [dim]not included[/dim]"
    elif spec is True:
        return f"{server} ({tool_count} tools) - [green]all tools[/green]"
    elif isinstance(spec, list):
        return f"{server} ({tool_count} tools) - [cyan]{len(spec)} included[/cyan]"
    elif isinstance(spec, ExcludeSpec):
        return f"{server} ({tool_count} tools) - [yellow]{len(spec.exclude)} excluded[/yellow]"
    return f"{server} ({tool_count} tools)"


def _interactive_toolset_edit(
    config_path: Path,
    config: Any,
    name: str,
    is_new: bool,
) -> None:
    """Interactive toolset creation/editing with arrow-key navigation."""
    from casual_mcp.models.config import Config

    config = Config.model_validate(config.model_dump())

    # Get available tools from servers
    mcp_client = load_mcp_client(config)
    tools = run_async_with_cleanup(get_tools_and_cleanup(mcp_client))
    server_names = set(config.servers.keys())
    server_tools = _build_server_tool_map(tools, server_names)

    # Get existing config if editing
    existing = config.tool_sets.get(name)
    existing_description = existing.description if existing else ""
    existing_servers: dict[str, Any] = dict(existing.servers) if existing else {}

    # Working copy of server configs
    new_servers: dict[str, Any] = dict(existing_servers)

    if is_new:
        console.print(f"[green]Creating new toolset '{name}'[/green]\n")
    else:
        console.print(f"[yellow]Editing toolset '{name}'[/yellow]\n")

    # Get description
    description = questionary.text(
        "Description:",
        default=existing_description,
    ).ask()

    if description is None:
        raise typer.Abort()

    # Main loop - configure servers one at a time
    sorted_servers = sorted(server_names)

    while True:
        console.print("\n[bold]Server Configuration:[/bold]")
        console.print("[dim]Configure each server, then select 'Save and exit' when done.[/dim]\n")

        # Build menu choices showing current status
        choices = []
        for server in sorted_servers:
            spec = new_servers.get(server)
            tool_count = len(server_tools[server])
            status = _format_server_status(server, spec, tool_count)
            # Strip Rich markup for questionary display
            plain_status = (
                status.replace("[dim]", "")
                .replace("[/dim]", "")
                .replace("[green]", "")
                .replace("[/green]", "")
                .replace("[cyan]", "")
                .replace("[/cyan]", "")
                .replace("[yellow]", "")
                .replace("[/yellow]", "")
            )
            choices.append(questionary.Choice(title=plain_status, value=server))

        choices.append(questionary.Separator())
        choices.append(questionary.Choice(title="💾 Save and exit", value="__save__"))
        choices.append(questionary.Choice(title="❌ Cancel", value="__cancel__"))

        selection = questionary.select(
            "Select a server to configure:",
            choices=choices,
        ).ask()

        if selection is None or selection == "__cancel__":
            raise typer.Abort()

        if selection == "__save__":
            break

        # Configure the selected server
        server = selection
        available = server_tools[server]
        existing_spec = new_servers.get(server)

        # Determine current mode for default selection
        if existing_spec is None:
            default_mode = "Don't include"
        elif existing_spec is True:
            default_mode = "All tools"
        elif isinstance(existing_spec, list):
            default_mode = "Include specific tools"
        elif isinstance(existing_spec, ExcludeSpec):
            default_mode = "Exclude specific tools"
        else:
            default_mode = "Don't include"

        mode = questionary.select(
            f"Configure {server} ({len(available)} tools):",
            choices=[
                "Don't include",
                "All tools",
                "Include specific tools",
                "Exclude specific tools",
            ],
            default=default_mode,
        ).ask()

        if mode is None:
            continue  # Go back to server list

        if mode == "Don't include":
            new_servers.pop(server, None)
        elif mode == "All tools":
            new_servers[server] = True
        elif mode == "Include specific tools":
            # Determine which tools were previously selected
            if isinstance(existing_spec, list):
                pre_selected = set(existing_spec)
            else:
                pre_selected = set()

            tool_choices = [
                questionary.Choice(title=tool, value=tool, checked=tool in pre_selected)
                for tool in available
            ]

            console.print("\n[dim]Use space to select, enter to confirm[/dim]")
            selected_tools = questionary.checkbox(
                f"Select tools to include from {server}:",
                choices=tool_choices,
            ).ask()

            if selected_tools is None:
                continue  # Go back to server list

            if selected_tools:
                new_servers[server] = selected_tools
            else:
                new_servers.pop(server, None)  # No tools = don't include
        elif mode == "Exclude specific tools":
            # Determine which tools were previously excluded
            if isinstance(existing_spec, ExcludeSpec):
                pre_excluded = set(existing_spec.exclude)
            else:
                pre_excluded = set()

            tool_choices = [
                questionary.Choice(title=tool, value=tool, checked=tool in pre_excluded)
                for tool in available
            ]

            console.print("\n[dim]Use space to select, enter to confirm[/dim]")
            excluded_tools = questionary.checkbox(
                f"Select tools to exclude from {server}:",
                choices=tool_choices,
            ).ask()

            if excluded_tools is None:
                continue  # Go back to server list

            if excluded_tools:
                new_servers[server] = {"exclude": excluded_tools}
            else:
                new_servers[server] = True  # No exclusions = all tools

    # Check if any servers are configured
    if not new_servers:
        console.print("[yellow]No servers configured - toolset will be empty[/yellow]")
        confirm = questionary.confirm("Save empty toolset?", default=False).ask()
        if not confirm:
            raise typer.Abort()

    # Save to config
    with config_path.open("r", encoding="utf-8") as f:
        raw = json.load(f)

    if "tool_sets" not in raw:
        raw["tool_sets"] = {}

    raw["tool_sets"][name] = {
        "description": description,
        "servers": new_servers,
    }

    with config_path.open("w", encoding="utf-8") as f:
        json.dump(raw, f, indent=4)

    console.print(f"\n[green]Saved toolset '{name}'[/green]")


if __name__ == "__main__":
    app()
