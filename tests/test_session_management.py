"""Tests for session management functions."""

from casual_llm import UserMessage
from casual_mcp.mcp_tool_chat import add_messages_to_session, get_session_messages, sessions


class TestSessionManagement:
    """Tests for session management functions."""

    def setup_method(self):
        """Clear sessions before each test."""
        sessions.clear()

    def test_get_session_messages_creates_new_session(self):
        """Test that get_session_messages creates a new session."""
        messages = get_session_messages("session1")

        assert messages == []
        assert "session1" in sessions

    def test_get_session_messages_returns_existing_session(self):
        """Test that get_session_messages returns existing session."""
        # Add a message to session
        sessions["session1"] = [UserMessage(content="Hello")]

        messages = get_session_messages("session1")

        assert len(messages) == 1
        assert messages[0].content == "Hello"

    def test_get_session_messages_returns_copy(self):
        """Test that get_session_messages returns a copy."""
        sessions["session1"] = [UserMessage(content="Hello")]

        messages1 = get_session_messages("session1")
        messages2 = get_session_messages("session1")

        # Should be copies, not same object
        assert messages1 is not messages2

    def test_add_messages_to_session(self):
        """Test adding messages to a session."""
        sessions["session1"] = []
        messages = [UserMessage(content="Hello"), UserMessage(content="World")]

        add_messages_to_session("session1", messages)

        assert len(sessions["session1"]) == 2
        assert sessions["session1"][0].content == "Hello"

    def test_add_messages_to_session_appends(self):
        """Test that add_messages_to_session appends to existing messages."""
        sessions["session1"] = [UserMessage(content="First")]

        add_messages_to_session("session1", [UserMessage(content="Second")])

        assert len(sessions["session1"]) == 2
