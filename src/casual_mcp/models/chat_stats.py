"""Usage statistics models for chat sessions."""

from pydantic import BaseModel, Field, computed_field


class TokenUsageStats(BaseModel):
    """Token usage statistics accumulated across all LLM calls."""

    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def total_tokens(self) -> int:
        """Total tokens (prompt + completion)."""
        return self.prompt_tokens + self.completion_tokens


class ToolUsageStats(BaseModel):
    """Statistics about tool usage during a chat session."""

    by_tool: dict[str, int] = Field(default_factory=dict)
    by_server: dict[str, int] = Field(default_factory=dict)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def total_tool_calls(self) -> int:
        """Total number of tool calls made."""
        return sum(self.by_tool.values())


class ChatStats(BaseModel):
    """Combined statistics from a chat session."""

    tokens: TokenUsageStats = Field(default_factory=TokenUsageStats)
    tools: ToolUsageStats = Field(default_factory=ToolUsageStats)
    llm_calls: int = Field(default=0, ge=0, description="Number of LLM calls made")
