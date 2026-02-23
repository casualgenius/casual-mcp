# PRD: Tool Discovery System for casual-mcp

**Author:** Alex

**Status:** Draft

**Created:** 2026-02-23

---

## 1. Overview

### 1.1 Problem Statement

When multiple MCP servers are connected, all tool definitions are loaded into the LLM context on every call. Tool definitions are token-heavy — a modest setup of 30-50 tools can consume 10-20K tokens of context before any conversation even starts. This has two consequences:

1. **Wasted tokens** — Most requests only need 2-3 tools, but the LLM pays for all of them on every call.
2. **Degraded tool selection** — LLM accuracy at choosing the correct tool drops significantly beyond 30-50 tools in context.

Anthropic offers a server-side Tool Search Tool (beta) that solves this, but it's Anthropic-only and requires their specific API. Since casual-mcp targets multiple providers (OpenAI, OpenRouter, Anthropic), a provider-agnostic solution is needed.

### 1.2 Proposed Solution

Add an **opt-in tool discovery system** to casual-mcp that:

- Injects a synthetic `search_tools` meta-tool into the LLM's available tools
- Generates a compressed **server manifest** (server names + tool names + descriptions) embedded in the search tool's description, so the LLM knows what's available to search for
- Uses **BM25 search** over tool names and descriptions to match capability queries
- Supports **direct lookup** by server name or tool name for precise loading
- Intercepts `search_tools` calls in the tool loop and handles them internally (never forwarded to MCP)
- Dynamically expands the tool set mid-conversation as tools are discovered
- Once discovered, tools **stay loaded** for the remainder of the session

### 1.3 Goals

| Goal | Metric |
| --- | --- |
| Significant token reduction | >50% fewer tool-definition tokens on first LLM call for setups with 10+ deferred tools |
| No degradation in tool selection | LLM correctly identifies and loads the right tools in >95% of cases |
| Provider-agnostic | Works with OpenAI, OpenRouter, Anthropic — any provider casual-llm supports |
| Opt-in, zero breaking changes | Existing users unaffected. Feature activated via config. |
| Minimal dependencies | Only `rank-bm25` added |

### 1.4 Non-Goals

- Embedding-based semantic search (BM25 is sufficient for tool-scale corpora)
- Automatic deferral heuristics (user explicitly configures which servers to defer)
- Per-turn tool eviction / expiry (discovered tools stay loaded)
- Anthropic-specific `defer_loading` / `tool_reference` wire format integration

---

## 2. Design

### 2.1 Configuration

Tool discovery is configured in the MCP server config, off by default:

```json
{
  "tool_discovery": {
    "enabled": true,
    "defer_all": false,
    "max_search_results": 5
  },
  "mcpServers": {
    "weather": {
      "command": "weather-server",
      "defer_loading": true
    },
    "notion": {
      "command": "notion-server",
      "defer_loading": false
    },
    "home-automation": {
      "command": "home-server",
      "defer_loading": true
    }
  }
}
```

- `tool_discovery.enabled` — Master switch. When false, all tools load normally.
- `tool_discovery.defer_all` — When true, overrides per-server settings; all servers are deferred. The `search_tools` meta-tool is always loaded.
- `tool_discovery.max_search_results` — Max tools returned per search query (default 5).
- Per-server `defer_loading` — When true, this server's tools are hidden from the LLM until discovered. When false (or absent), tools load into context normally.

### 2.2 Server Manifest

When tool discovery is enabled, casual-mcp auto-generates a compressed manifest from connected MCP server metadata. This manifest is embedded in the `search_tools` tool description so the LLM knows what's available.

Manifest format:

```
Available tool servers (use this tool to load their definitions):

- weather (3 tools): get_current_weather, get_forecast, get_alerts
  Current conditions, forecasts, and severe weather alerts

- home-automation (8 tools): get_lights, set_lights, get_temperature, set_thermostat, get_sensors, lock_door, unlock_door, get_camera_snapshot
  Control lights, thermostat, locks, sensors, and cameras
```

For servers with many tools (>10), the manifest summarizes rather than listing every tool name, to keep the manifest compact:

```
- notion (15 tools): search, create_page, update_page, create_database, ... and 11 more
  Search, create, and manage Notion pages, databases, comments, and users
```

The manifest is regenerated when tool discovery is initialized (at `McpToolChat` construction or when the tool cache refreshes).

### 2.3 The `search_tools` Meta-Tool

A synthetic tool injected into the LLM's available tools alongside any non-deferred tools.

**Tool definition:**

```json
{
  "name": "search_tools",
  "description": "Search for and load tool definitions from available MCP servers. Use this before calling a tool that isn't currently loaded.\n\n<manifest>\n... auto-generated server manifest ...\n</manifest>",
  "parameters": {
    "type": "object",
    "properties": {
      "query": {
        "type": "string",
        "description": "Natural language capability search across all deferred tools (e.g. 'create a calendar event'). Uses keyword matching."
      },
      "server_name": {
        "type": "string",
        "description": "Filter results to a specific server by name."
      },
      "tool_names": {
        "type": "array",
        "items": { "type": "string" },
        "description": "Load specific tools by exact name. Most token-efficient when you know the tool name from the manifest."
      }
    }
  }
}
```

At least one of `query`, `server_name`, or `tool_names` must be provided.

Parameter combinations:

- `query` alone — BM25 search across all deferred tools, returns top-k
- `server_name` alone — Returns all tools from that server
- `tool_names` alone — Direct lookup, loads exact tools by name
- `server_name` + `query` — BM25 search scoped to one server
- `server_name` + `tool_names` — Direct lookup scoped to one server (validation)
- `query` + `tool_names` — tool_names takes precedence, query as fallback

### 2.4 Search Implementation

BM25 via the `rank-bm25` package, indexing over tool name + description for each deferred tool.

```python
from rank_bm25 import BM25Okapi

class ToolSearchIndex:
    def __init__(self, tools: list[McpTool]):
        self.tools = tools
        corpus = [f"{t.name} {t.description or ''}" for t in tools]
        tokenized = [doc.lower().split() for doc in corpus]
        self.index = BM25Okapi(tokenized)

    def search(self, query: str, max_results: int = 5,
               server_filter: str | None = None) -> list[McpTool]:
        scores = self.index.get_scores(query.lower().split())
        ranked = sorted(range(len(scores)),
                       key=lambda i: scores[i], reverse=True)
        results = []
        for i in ranked:
            if server_filter and self.tools[i].server_name != server_filter:
                continue
            if scores[i] > 0:
                results.append(self.tools[i])
            if len(results) >= max_results:
                break
        return results
```

The index is built once at initialization and rebuilt if the tool cache refreshes.

### 2.5 Search Result Format

When the LLM calls `search_tools`, the result returned is a structured summary of matched tools:

```
Found 2 tools:

- notion:create_page
  Create a new Notion page with properties and content
  Parameters: parent_id (string, required), title (string, required), content (string), properties (object)

- notion:create_comment
  Add a comment to a Notion page
  Parameters: page_id (string, required), text (string, required)

These tools are now loaded and available to call.
```

Critically, the **full tool definitions** (complete JSON schemas) are also injected into the `tools` parameter for the next LLM call in the loop. The search result text gives the LLM a readable summary; the actual definitions enable it to call the tools correctly.

### 2.6 Toolset Compatibility

casual-mcp already supports **toolsets** — named configurations that restrict which tools are available per request:

```json
"tool_sets": {
    "research": {
        "description": "Research tools for weather and words",
        "servers": {
            "weather": true,
            "words": { "exclude": ["random_word"] },
            "fetch": true
        }
    }
}
```

The existing `chat()` method applies toolset filtering early:

```python
tools = await self.tool_cache.get_tools()
if tool_set is not None:
    tools = filter_tools_by_toolset(tools, tool_set, self.server_names, validate=True)
```

Tool discovery **must respect toolset filtering**. The ordering is:

```
all tools → filter by toolset → partition into loaded/deferred → build manifest + search index
```

This means:

- The manifest only shows servers/tools that pass the active toolset filter
- The BM25 index only contains toolset-permitted tools
- A tool excluded by the toolset can never be discovered via search
- Different toolsets produce different manifests (correct behavior — if you're in "research" mode, math tools shouldn't appear)
- When no toolset is specified, all tools are eligible for discovery as normal

The manifest and search index are rebuilt per `chat()` call since the toolset can change between calls. This is cheap — BM25 indexing over a few dozen tools is sub-millisecond.

### 2.7 Tool Loop Integration

The key integration point is in `McpToolChat.chat()`. The tool loop needs two modifications:

1. **Before the loop**: After toolset filtering, partition remaining tools into loaded (non-deferred) and deferred. Inject `search_tools` into the loaded set. Build the BM25 index from deferred tools.
2. **Inside the loop**: When a tool call targets `search_tools`, intercept it — don't forward to MCP. Execute the search, move matched tools from deferred to loaded, and return the result. The next iteration of the loop will include the newly loaded tools.

```python
# Pseudocode for modified chat() loop
async def chat(self, messages, tool_set=None, meta=None):
    all_tools = await self.tool_cache.get_tools()

    # Existing: toolset filtering (unchanged)
    if tool_set is not None:
        all_tools = filter_tools_by_toolset(
            all_tools, tool_set, self.server_names, validate=True
        )

    # New: discovery partitioning (after toolset filter)
    if self.discovery_enabled:
        loaded, deferred = partition_tools(all_tools, self.defer_config)
        search_tool = build_search_tool(deferred)  # manifest from filtered tools only
        loaded.append(search_tool)
        search_index = ToolSearchIndex(deferred)
    else:
        loaded = all_tools

    while True:
        ai_message = await self.model.chat(
            messages=messages,
            tools=tools_from_mcp(loaded)
        )
        # ... stats, append to messages ...

        if not ai_message.tool_calls:
            break

        for tool_call in ai_message.tool_calls:
            if tool_call.name == "search_tools" and self.discovery_enabled:
                # Handle internally
                result, newly_loaded = execute_search(
                    tool_call, search_index, deferred
                )
                # Move discovered tools to loaded set
                loaded.extend(newly_loaded)
                deferred = [t for t in deferred if t not in newly_loaded]
            else:
                result = await self.execute(tool_call, meta=meta)

            messages.append(result)

    return response_messages
```

### 2.8 Synthetic Tool Pattern

This introduces the concept of **synthetic tools** in casual-mcp — tools that are handled internally by the library rather than forwarded to an MCP server. `search_tools` is the first, but the pattern should be generic enough to support future synthetic tools.

Proposed approach:

- A `SyntheticTool` base class or protocol with `name`, `definition` (for the LLM), and `execute(args)` method
- `McpToolChat` maintains a registry of synthetic tools
- In the tool loop, check the registry before forwarding to MCP
- Synthetic tools can modify the tool set (as `search_tools` does) by returning a signal alongside their result

---

## 3. Dependencies

| Package | Purpose | Size |
| --- | --- | --- |
| `rank-bm25` | BM25 search over tool corpus | ~100 lines, pure Python, no transitive deps |

---

## 4. Implementation Plan

### Phase 1: Synthetic Tool Infrastructure

- Add `SyntheticTool` protocol/base class
- Add synthetic tool registry to `McpToolChat`
- Modify tool loop to check registry before MCP dispatch
- Unit tests for synthetic tool interception

### Phase 2: Tool Discovery Core

- Implement `ToolSearchIndex` (BM25 wrapper)
- Implement manifest generation from MCP server metadata
- Build the `search_tools` synthetic tool (definition + execute)
- Configuration parsing (`tool_discovery` + per-server `defer_loading`)
- Unit tests for search, manifest generation, config parsing

### Phase 3: Tool Loop Integration

- Modify `chat()` to partition tools based on defer config
- Inject `search_tools` and manage loaded/deferred sets
- Handle tool set expansion when search returns results
- Integration tests: full tool loop with discovery

### Phase 4: Polish and Release

- Documentation and examples
- Edge case handling (no results, invalid server name, all tools already loaded)
- Stats tracking (tools discovered, search calls, token savings estimate)
- Release as part of casual-mcp minor version bump

---

## 5. Edge Cases

| Case | Behavior |
| --- | --- |
| LLM calls a deferred tool without searching first | Return error message suggesting it use `search_tools` first |
| Search returns no results | Return "No matching tools found" with suggestion to try different query |
| All deferred tools already loaded | `search_tools` still works but returns "already loaded" for matched tools |
| Server name doesn't exist | Return error listing valid server names |
| Tool name doesn't exist | Return error with closest matches |
| `tool_discovery.enabled` but no servers have `defer_loading` | `search_tools` not injected, behaves as normal |
| Tool cache refreshes mid-session | Rebuild index and manifest; already-loaded tools stay loaded |

**Toolset interaction edge cases:**

- **Active toolset excludes a deferred server entirely** — Server doesn't appear in manifest or search index. LLM never sees it.
- **Toolset partially excludes tools from a deferred server** — Only permitted tools are indexed. Manifest shows reduced tool count for that server.
- **No toolset specified** — All connected tools eligible for discovery as normal.

---

## 6. Success Criteria

| Criteria | Target |
| --- | --- |
| Token reduction on first call | >50% fewer tool tokens for 10+ deferred tools |
| Search accuracy | LLM finds correct tools in >95% of test cases |
| No regression for non-discovery users | Zero changes to existing behavior when feature is off |
| Latency overhead | <10ms for search execution (BM25 is fast) |
| Works across providers | Tested with OpenAI, OpenRouter, Anthropic |