"""AI provider protocol and response models.

Defines the interface for AI providers (Ollama, Anthropic, OpenAI, etc.)
with support for streaming and tool calling.
"""

from __future__ import annotations

import time
from abc import abstractmethod
from collections.abc import AsyncIterator
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field

__all__ = ["AIMessage", "AIProvider", "AIResponse", "AITool", "AIToolCall", "AIToolResult"]


class AIMessage(BaseModel):
    """Single message in conversation."""

    role: str = Field(description="Message role: system, user, assistant")
    content: str = Field(description="Message content")
    timestamp: float = Field(default_factory=time.time)
    tool_calls: list[dict[str, Any]] | None = Field(default=None)
    tool_results: list[dict[str, Any]] | None = Field(default=None)


class AIToolCall(BaseModel):
    """AI tool call request."""

    id: str = Field(description="Unique tool call ID")
    name: str = Field(description="Tool function name")
    parameters: dict[str, Any] = Field(description="Tool parameters")


class AIToolResult(BaseModel):
    """AI tool call result."""

    call_id: str = Field(description="Corresponding tool call ID")
    success: bool = Field(description="Whether tool call succeeded")
    result: Any = Field(description="Tool return value")
    error: str | None = Field(default=None, description="Error message if failed")


class AITool(BaseModel):
    """AI tool definition for function calling."""

    name: str = Field(description="Tool function name")
    description: str = Field(description="What the tool does")
    parameters: dict[str, Any] = Field(description="JSON schema for parameters")


class AIResponse(BaseModel):
    """AI provider response."""

    content: str = Field(description="Generated text response")
    tool_calls: list[AIToolCall] = Field(default_factory=list)
    finish_reason: str = Field(default="stop", description="Why generation stopped")
    usage: dict[str, Any] | None = Field(default=None, description="Token usage stats")
    model: str | None = Field(default=None, description="Model used")
    provider: str | None = Field(default=None, description="Provider name")


@runtime_checkable
class AIProvider(Protocol):
    """AI provider protocol.

    Defines interface for AI providers supporting both regular completion
    and streaming with optional tool calling.
    """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Provider name (e.g., 'ollama', 'anthropic')."""
        ...

    @property
    @abstractmethod
    def supports_tools(self) -> bool:
        """Whether provider supports function/tool calling."""
        ...

    @abstractmethod
    async def complete(
        self,
        messages: list[AIMessage],
        tools: list[AITool] | None = None,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> AIResponse:
        """Generate completion for messages.

        Args:
            messages: Conversation messages.
            tools: Available tools for function calling.
            model: Model to use (provider-specific).
            temperature: Randomness (0.0-1.0).
            max_tokens: Maximum tokens to generate.

        Returns:
            AI response with content and optional tool calls.

        Raises:
            AIProviderError: If generation fails.
        """
        ...

    @abstractmethod
    async def stream_complete(
        self,
        messages: list[AIMessage],
        tools: list[AITool] | None = None,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        """Stream completion tokens.

        Args:
            messages: Conversation messages.
            tools: Available tools.
            model: Model to use.
            temperature: Randomness.
            max_tokens: Maximum tokens.

        Yields:
            Text chunks as they're generated.

        Raises:
            AIProviderError: If streaming fails.
        """
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """Check if provider is available and responding.

        Returns:
            True if healthy, False otherwise.
        """
        ...


class AIProviderError(Exception):
    """Raised when AI provider operations fail."""

    def __init__(self, message: str, provider: str | None = None, model: str | None = None):
        super().__init__(message)
        self.provider = provider
        self.model = model
