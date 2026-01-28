import logging

from rich.console import Console
from rich.logging import RichHandler


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"casual_mcp.{name}")


def configure_logging(
    level: str | int = "INFO",
    logger: logging.Logger | None = None,
) -> None:
    if logger is None:
        logger = logging.getLogger("casual_mcp")

    handler = RichHandler(console=Console(stderr=True), rich_tracebacks=True)
    formatter = logging.Formatter("%(name)s: %(message)s")
    handler.setFormatter(formatter)

    logger.setLevel(level)

    # Remove any existing handlers to avoid duplicates on reconfiguration
    for hdlr in logger.handlers[:]:
        logger.removeHandler(hdlr)

    logger.addHandler(handler)

    # Set logging level on FastMCP and MCP libraries
    logging.getLogger("fastmcp").setLevel(level)
    logging.getLogger("mcp").setLevel(level)

    logger.info("Logging Configured")
