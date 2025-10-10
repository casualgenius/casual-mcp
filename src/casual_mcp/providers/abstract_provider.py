from abc import ABC, abstractmethod

import mcp

from casual_mcp.models.messages import ChatMessage


class CasualMcpProvider(ABC):
    @abstractmethod
    async def generate(
        self,
        messages: list[ChatMessage],
        tools: list[mcp.Tool]
    ) -> ChatMessage:
        pass

    def update_tools(self, tools: list[mcp.Tool]) -> None:
        """
        Allow providers to refresh their tool catalogue when it changes.
        Default implementation is a no-op for providers that do not need it.
        """
        return None
