from typing import Annotated, Tuple, List
from fastmcp import FastMCP, utilities
from pydantic import Field
import requests

mcp = FastMCP("Weather", instructions="Weather tools using Open-Meteo.")

location_cache: dict[str, Tuple[float, float]] = {}


def resolve_location(location: str) -> Tuple[float, float]:
    if location.lower() in location_cache:
        return location_cache[location.lower()]

    resp = requests.get("https://geocoding-api.open-meteo.com/v1/search", params={"name": location})
    data = resp.json()
    results = data.get("results")
    if not results:
        raise ValueError(f"Could not resolve location: {location}")

    lat = results[0]["latitude"]
    lon = results[0]["longitude"]
    location_cache[location.lower()] = (lat, lon)
    return lat, lon


weather_codes = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Depositing rime fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    61: "Slight rain",
    63: "Moderate rain",
    65: "Heavy rain",
    80: "Rain showers",
    95: "Thunderstorm",
}

uv_risk_levels = [
    (0, 2, "Low"),
    (3, 5, "Moderate"),
    (6, 7, "High"),
    (8, 10, "Very High"),
    (11, float("inf"), "Extreme"),
]


def get_uv_risk(index: float) -> str:
    for low, high, level in uv_risk_levels:
        if low <= index <= high:
            return level
    return "Unknown"


@mcp.tool(description="Get current temperature, wind speed, and condition for a location.")
def current_weather(location: Annotated[str, Field(description="City or place name")]) -> dict:
    lat, lon = resolve_location(location)
    resp = requests.get(
        "https://api.open-meteo.com/v1/forecast",
        params={"latitude": lat, "longitude": lon, "current_weather": True},
    )
    data = resp.json().get("current_weather", {})
    return {
        "temperature_c": data.get("temperature"),
        "windspeed_kph": data.get("windspeed"),
        "condition": weather_codes.get(data.get("weathercode"), "Unknown"),
        "time": data.get("time"),
    }


@mcp.tool(description="Get the daily weather forecast for the next N days.")
def forecast(
    location: Annotated[str, Field(description="City or place name")],
    days: Annotated[int, Field(ge=1, le=7)] = 3,
) -> List[dict]:
    lat, lon = resolve_location(location)
    params = {
        "latitude": lat,
        "longitude": lon,
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,windspeed_10m_max",
        "timezone": "auto",
    }
    daily = (
        requests.get("https://api.open-meteo.com/v1/forecast", params=params)
        .json()
        .get("daily", {})
    )
    return [
        {
            "date": daily["time"][i],
            "max_temp_c": daily["temperature_2m_max"][i],
            "min_temp_c": daily["temperature_2m_min"][i],
            "rain_mm": daily["precipitation_sum"][i],
            "wind_max_kph": daily["windspeed_10m_max"][i],
        }
        for i in range(min(days, len(daily.get("time", []))))
    ]


@mcp.tool(description="Get UV index forecast and risk level for the next few days.")
def uv_index(location: Annotated[str, Field(description="City or place name")]) -> List[dict]:
    lat, lon = resolve_location(location)
    params = {"latitude": lat, "longitude": lon, "daily": "uv_index_max", "timezone": "auto"}
    daily = (
        requests.get("https://api.open-meteo.com/v1/forecast", params=params)
        .json()
        .get("daily", {})
    )
    return [
        {
            "date": daily["time"][i],
            "uv_index": daily["uv_index_max"][i],
            "risk_level": get_uv_risk(daily["uv_index_max"][i]),
        }
        for i in range(len(daily.get("time", [])))
    ]


@mcp.tool(description="Get air quality index values (PM10, PM2.5, ozone) for a location.")
def air_quality(location: Annotated[str, Field(description="City or place name")]) -> dict:
    lat, lon = resolve_location(location)
    url = "https://air-quality-api.open-meteo.com/v1/air-quality"
    params = {"latitude": lat, "longitude": lon, "hourly": "pm10,pm2_5,ozone", "timezone": "auto"}
    hourly = requests.get(url, params=params).json().get("hourly", {})
    latest = -1
    return {
        "summary": "Air quality data for the latest hour.",
        "values": {
            "pm10": hourly.get("pm10", [None])[latest],
            "pm2_5": hourly.get("pm2_5", [None])[latest],
            "ozone": hourly.get("ozone", [None])[latest],
        },
        "time": hourly.get("time", [None])[latest],
    }


if __name__ == "__main__":
    utilities.logging.configure_logging(level="WARNING")
    mcp.run()
