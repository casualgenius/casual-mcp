# TODO - Code Improvements

**Last Updated**: 2025-12-03 (after casual-llm migration)

## ✅ Completed Issues

### ~~1. Ollama Provider Not Implemented~~ ✅ RESOLVED
**Status**: Removed local providers, now using fully-implemented casual-llm providers

**Completed**:
- [x] Migrated to casual-llm library (v0.1.0+)
- [x] Removed `src/casual_mcp/providers/ollama_provider.py` (183 lines)
- [x] Removed `src/casual_mcp/providers/openai_provider.py` (184 lines)
- [x] Removed `src/casual_mcp/providers/abstract_provider.py` (23 lines)
- [x] Updated ProviderFactory to use casual-llm's `create_provider()`

---

### ~~2. Infinite Loop Risk in Ollama Provider~~ ✅ RESOLVED
**Status**: Old ollama_provider.py removed, now handled by casual-llm

**Completed**:
- [x] Removed problematic recursive call code
- [x] Ollama provider now managed by casual-llm with proper error handling

---

### ~~9. Type Annotation Gaps~~ ✅ COMPLETED
**Status**: All mypy type errors fixed

**Completed**:
- [x] Fixed all 37 mypy type errors across 7 files
- [x] Removed duplicate models (`tool_call.py`, `messages.py`)
- [x] All code now passes `mypy --strict`
- [x] Added return type annotations to all functions
- [x] Added proper type hints throughout codebase

**Remaining**:
- [ ] Enable mypy in pre-commit hooks

---

### ~~15. Unused Code Cleanup~~ ✅ COMPLETED
**Status**: Removed 437+ lines of duplicate code

**Completed**:
- [x] Ran `ruff check --fix src/` - all checks pass
- [x] Removed old provider implementations
- [x] Removed duplicate message models
- [x] Removed unused imports

---

### ~~16. Synchronous Ollama Client~~ ✅ RESOLVED
**Status**: Handled by casual-llm's async implementation

**Completed**:
- [x] Old synchronous Ollama client removed
- [x] casual-llm handles async operations properly

---

## 🔴 Critical Issues (Priority 1)

### 1. Global Session State Without Thread Safety
**File**: `src/casual_mcp/mcp_tool_chat.py:21`

```python
sessions: dict[str, list[ChatMessage]] = {}
```

**Status**: Documented as dev/test only in README.md and CLAUDE.md, but still a production concern

**Issues**:
- [ ] Not thread-safe for concurrent API requests
- [ ] No session cleanup/expiry mechanism
- [ ] Memory leak potential (sessions never deleted)
- [ ] Race conditions possible

**Options**:
- [ ] Add threading locks or asyncio locks
- [ ] Move to Redis/database for production
- [ ] Add session expiry/TTL
- [ ] Add max session size limit

**Documentation**:
- [x] Documented as dev/test only in README
- [x] Documented as dev/test only in CLAUDE.md
- [x] Clarified in API endpoint descriptions

---

## 🟡 Important Issues (Priority 2)

### 2. Test Coverage (PARTIALLY COMPLETED)
**Status**: Basic test structure exists with 7 passing tests

**Completed**:
- [x] Set up pytest structure (`tests/` directory)
- [x] Add tests for tool conversion functions (7 tests in test_tools.py)

**Still Needed**:
- [ ] Add tests for tool cache behavior (TTL, refresh, version, prime, invalidate)
- [ ] Add tests for provider factory (caching, creation, error handling)
- [ ] Add tests for config loading/validation
- [ ] Add tests for utils functions (format_tool_call_result, render_system_prompt)
- [ ] Add tests for session management (get_session_messages, add_messages_to_session)
- [ ] Add integration test for McpToolChat.chat() loop
- [ ] Add integration test for McpToolChat.generate()
- [ ] Add integration test for McpToolChat.execute()
- [ ] Add tests for error handling in tool execution
- [ ] Set up CI/CD with test runs
- [ ] Add coverage reporting (aim for >80%)

---

### 3. Template Path Resolution
**File**: `src/casual_mcp/utils.py:92`

```python
TEMPLATE_DIR = Path("prompt-templates").resolve()
```

**Issue**: Relative path depends on current working directory

**Fix**:
- [ ] Use `Path(__file__).parent.parent.parent / "prompt-templates"`
- [ ] Or make template directory configurable via env var
- [ ] Add validation that template directory exists

---

### 4. Missing API Security
**File**: `src/casual_mcp/main.py`

**Missing**:
- [ ] Authentication/authorization (API keys, OAuth, etc.)
- [ ] Rate limiting per user/IP
- [ ] CORS configuration
- [ ] Input validation/sanitization
- [ ] Request size limits
- [ ] Timeout configuration

**Recommendation**: Start with simple API key authentication

---

### 5. Error Message Leakage to LLM
**File**: `src/casual_mcp/mcp_tool_chat.py:139-143`

```python
return ToolResultMessage(
    name=tool_call.function.name,
    tool_call_id=tool_call.id,
    content=str(e),  # Raw exception exposed to LLM
)
```

**Fix**:
- [ ] Sanitize error messages before sending to LLM
- [ ] Remove file paths, API keys, internal details
- [ ] Provide generic error messages to LLM
- [ ] Log full errors server-side only

---

### 6. Default Parameter Mismatch
**Files**:
- `src/casual_mcp/utils.py:39` - defaults to `"function_result"`
- `src/casual_mcp/mcp_tool_chat.py:149` - uses env var defaulting to `'result'`

**Fix**:
- [ ] Align defaults to same value
- [ ] Document why they differ if intentional
- [ ] Consider using config instead of env var

---

## 🔵 Code Quality Improvements (Priority 3)

### 7. Logging Inconsistencies

**Issues**:
- [ ] Tool conversion logs at INFO on every request (too verbose)
- [ ] Inconsistent use of DEBUG vs INFO
- [ ] Some important operations lack logging

**Recommendations**:
- [ ] Move verbose/repetitive logging to DEBUG
- [ ] Reserve INFO for important lifecycle events
- [ ] Add structured logging (JSON format option)
- [ ] Add correlation IDs for request tracing

**Files**:
- `src/casual_mcp/convert_tools.py`
- `src/casual_mcp/mcp_tool_chat.py`

---

### 8. Hardcoded System Prompt
**File**: `src/casual_mcp/main.py:31-42`

**Fix**:
- [ ] Move default system prompt to `prompt-templates/default-api.j2`
- [ ] Or add to config file
- [ ] Make it easier to customize without code changes

---

### 9. Missing Validation

**Add validation for**:
- [ ] Model exists in config before use (API endpoints)
- [ ] Template files exist when referenced
- [ ] Server commands are executable
- [ ] Required environment variables (OPENAI_API_KEY when using OpenAI)
- [ ] Session IDs (max length, valid characters)
- [ ] Message list not empty
- [ ] Tool names don't conflict across servers

**Files**:
- `src/casual_mcp/utils.py` - config validation
- `src/casual_mcp/main.py` - API validation

---

### 10. Namespace Tools Feature Unused
**File**: `src/casual_mcp/models/config.py:8`

```python
namespace_tools: bool | None = False
```

**Options**:
- [ ] Implement namespace tools feature (prefix tool names with server name)
- [ ] Remove if not needed
- [ ] Document what it's meant to do

---

### 11. Documentation Gaps (PARTIALLY COMPLETED)

**Completed**:
- [x] Updated comprehensive README.md with architecture, patterns, troubleshooting
- [x] Updated CLAUDE.md for development guidance
- [x] Documented casual-llm integration
- [x] Documented sessions as dev/test only

**Still Needed**:
- [ ] Add docstrings to all public methods in `McpToolChat`
- [ ] Add docstrings to ProviderFactory methods
- [ ] Add docstrings to ToolCache methods
- [ ] Add docstrings to config models (explain each field)
- [ ] Add docstrings to utility functions
- [ ] Add examples in docstrings
- [ ] Generate API documentation with Sphinx or mkdocs

---

## 🟢 Minor Improvements (Priority 4)

### 12. CLI Reload Default
**File**: `src/casual_mcp/cli.py:19`

```python
def serve(host: str = "0.0.0.0", port: int = 8000, reload: bool = True) -> None:
```

**Fix**:
- [ ] Change `reload` default to `False`
- [ ] Document `--reload` flag for development use

---

## 📋 Additional Recommendations

### Development Infrastructure
- [ ] Add pre-commit hooks (black, ruff, mypy)
- [ ] Set up GitHub Actions CI/CD
- [ ] Add dependabot for dependency updates
- [ ] Add CHANGELOG.md
- [ ] Add CONTRIBUTING.md

### Configuration
- [ ] Add example config files with comments
- [ ] Validate config schema on load
- [ ] Support multiple config file locations (~/.casual-mcp/, etc.)
- [ ] Add `casual-mcp init` command to create config

### Error Handling
- [ ] Create custom exception hierarchy
- [ ] Add retry logic with exponential backoff for API calls
- [ ] Add circuit breaker for failing MCP servers
- [ ] Better error messages for common issues

### Performance
- [ ] Add metrics/observability (Prometheus, DataDog)
- [ ] Profile tool calling loop for bottlenecks
- [ ] Consider caching LLM responses (optional)
- [ ] Add request/response size limits

### Documentation
- [ ] Add architecture diagrams
- [ ] Add sequence diagrams for tool calling flow
- [ ] Add more usage examples
- [ ] Document common patterns and best practices

---

## Priority Summary

- **Completed**: 5 issues (provider migration, type annotations, code cleanup)
- **Critical (Do First)**: 1 issue
- **Important (Do Soon)**: 5 issues
- **Quality (Do When Stable)**: 5 issues
- **Minor (Nice to Have)**: 1 issue

## Recent Changes (2025-12-03)

### Migration to casual-llm
- ✅ Removed 390+ lines of duplicate provider code
- ✅ Removed 47 lines of duplicate message models
- ✅ Fixed all 37 mypy type errors
- ✅ Passed all ruff linting checks
- ✅ Updated comprehensive documentation (README, CLAUDE.md)
- ✅ Established test infrastructure (7 tests passing)
- ✅ Removed unused asyncio_mode pytest config

### Code Quality Improvements
- All code now type-safe with mypy --strict
- All code passes ruff linting
- Test suite established with pytest
- Documentation significantly improved

**Next Steps**:
1. Expand test coverage (Priority 2, Issue #2)
2. Fix template path resolution (Priority 2, Issue #3)
3. Align default parameters (Priority 2, Issue #6)
4. Add API security (Priority 2, Issue #4)
