from datetime import datetime, timedelta, date
from zoneinfo import ZoneInfo
from typing import Annotated
from fastmcp import FastMCP, utilities
from pydantic import Field
import dateparser
import calendar

mcp = FastMCP("Time and Date 🚀")


@mcp.tool()
def current_time(
    timezone: Annotated[
        str,
        Field(
            description="A valid IANA timezone string, e.g., 'UTC', 'Asia/Bangkok'. Use 'Asia/Bangkok' timezone if no timezone provided by the user."
        ),
    ],
) -> str:
    """Get the current time in the specified timezone."""
    now = datetime.now(ZoneInfo(timezone))
    return now.isoformat()


@mcp.tool()
def time_since(
    past_date: Annotated[
        str, Field(description="A past datetime in ISO 8601 format, e.g. '2024-01-01T00:00:00Z'")
    ],
) -> str:
    """Get human-readable time since a given datetime."""
    past = datetime.fromisoformat(past_date.replace("Z", "+00:00"))
    delta = datetime.now(datetime.utcnow().astimezone().tzinfo) - past
    return f"{delta.days} days, {delta.seconds // 3600} hours ago"


@mcp.tool()
def add_days(
    days: Annotated[int, Field(description="Number of days to add to the current date")],
) -> str:
    """Get a future date by adding days to today."""
    future = datetime.now().date() + timedelta(days=days)
    return future.isoformat()


@mcp.tool()
def subtract_days(
    days: Annotated[int, Field(description="Number of days to subtract from the current date")],
) -> str:
    """Get a past date by subtracting days from today."""
    past = datetime.now().date() - timedelta(days=days)
    return past.isoformat()


@mcp.tool()
def date_diff(
    start: Annotated[str, Field(description="Start date in ISO format, e.g., '2024-01-01'")],
    end: Annotated[str, Field(description="End date in ISO format, e.g., '2025-01-01'")],
) -> str:
    """Calculate the number of days between two dates."""
    start_date = datetime.fromisoformat(start).date()
    end_date = datetime.fromisoformat(end).date()
    diff = (end_date - start_date).days
    return f"{diff} days"


@mcp.tool()
def next_weekday(
    weekday: Annotated[
        str, Field(description="The name of the weekday (e.g., 'Monday', 'Friday')")
    ],
) -> str:
    """Get the date of the next given weekday."""
    weekdays = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    weekday = weekday.lower()
    if weekday not in weekdays:
        raise ValueError("Invalid weekday name.")
    today = date.today()
    today_idx = today.weekday()
    target_idx = weekdays.index(weekday)
    days_ahead = (target_idx - today_idx + 7) % 7
    if days_ahead == 0:
        days_ahead = 7
    return (today + timedelta(days=days_ahead)).isoformat()


@mcp.tool()
def is_leap_year(year: Annotated[int, Field(description="The year to check")]) -> bool:
    """Check if a year is a leap year."""
    return calendar.isleap(year)


@mcp.tool()
def week_number(
    date_str: Annotated[str, Field(description="Date in ISO format (e.g., '2025-05-15')")],
) -> int:
    """Get the ISO week number of the given date."""
    return datetime.fromisoformat(date_str).isocalendar().week


@mcp.tool()
def parse_human_date(
    description: Annotated[
        str, Field(description="A natural language description of a date, e.g. 'next Friday'")
    ],
) -> str:
    """Parse a human-readable date expression."""
    parsed = dateparser.parse(description)
    if not parsed:
        raise ValueError("Could not parse the date description.")
    return parsed.date().isoformat()


if __name__ == "__main__":
    utilities.logging.configure_logging(level="WARNING")
    mcp.run()
