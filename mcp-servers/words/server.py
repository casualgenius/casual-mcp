from typing import Annotated
from fastmcp import FastMCP, utilities
from pydantic import Field
import requests

mcp = FastMCP(
    "Dictionary & Thesaurus",
    instructions="Tools for definitions, synonyms, and example usage of English words using the Free Dictionary API.",
)

API_BASE = "https://api.dictionaryapi.dev/api/v2/entries/en/"


@mcp.tool(description="Get the definition(s) of an English word.")
def define(word: Annotated[str, Field(description="The word to define")]) -> dict:
    response = requests.get(f"{API_BASE}{word}")
    data = response.json()
    if isinstance(data, dict) and data.get("title") == "No Definitions Found":
        return {"error": f"No definitions found for '{word}'"}

    meanings = []
    for entry in data:
        for meaning in entry.get("meanings", []):
            meanings.append(
                {
                    "part_of_speech": meaning.get("partOfSpeech"),
                    "definitions": [d.get("definition") for d in meaning.get("definitions", [])],
                }
            )
    return {"word": word, "meanings": meanings}


@mcp.tool(description="Get example usage of a word, if available.")
def example_usage(
    word: Annotated[str, Field(description="The word to look up examples for")],
) -> list:
    response = requests.get(f"{API_BASE}{word}")
    data = response.json()
    if isinstance(data, dict) and data.get("title") == "No Definitions Found":
        return []

    examples = []
    for entry in data:
        for meaning in entry.get("meanings", []):
            for definition in meaning.get("definitions", []):
                ex = definition.get("example")
                if ex:
                    examples.append(ex)
    return examples


@mcp.tool(description="Get synonyms for a word, if available.")
def synonyms(word: Annotated[str, Field(description="The word to find synonyms for")]) -> list:
    response = requests.get(f"{API_BASE}{word}")
    data = response.json()
    if isinstance(data, dict) and data.get("title") == "No Definitions Found":
        return []

    synonyms_set = set()
    for entry in data:
        for meaning in entry.get("meanings", []):
            for definition in meaning.get("definitions", []):
                for syn in definition.get("synonyms", []):
                    synonyms_set.add(syn)
    return list(synonyms_set)


if __name__ == "__main__":
    utilities.logging.configure_logging(level="WARNING")
    mcp.run()
