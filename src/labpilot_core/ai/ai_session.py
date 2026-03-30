"""AI session manager for LabPilot.

High-level interface for AI interactions that combines provider,
context building, tool execution, and conversation management.
"""

from __future__ import annotations

import json
import time
from collections.abc import AsyncGenerator
from typing import Any

from labpilot_core.ai.context_builder import ContextBuilder
from labpilot_core.ai.ollama_provider import OllamaProvider
from labpilot_core.ai.provider import (
    AIMessage,
    AIProvider,
    AIResponse,
    AITool,
)
from labpilot_core.ai.tool_registry import ToolExecutionError, ToolRegistry
from labpilot_core.core.events import Event, EventKind
from labpilot_core.core.session import Session

__all__ = ["AIConversation", "AISession", "AISessionError"]


class AIConversation:
    """A conversation thread with message history."""

    def __init__(self, conversation_id: str):
        self.id = conversation_id
        self.messages: list[AIMessage] = []
        self.created_at = time.time()

    def add_message(self, message: AIMessage) -> None:
        """Add message to conversation history."""
        self.messages.append(message)

    def get_context_messages(self, max_messages: int = 20) -> list[AIMessage]:
        """Get recent messages for context.

        Args:
            max_messages: Maximum number of messages to include.

        Returns:
            List of recent messages.
        """
        return self.messages[-max_messages:] if max_messages > 0 else self.messages


class AISessionError(Exception):
    """Raised when AI session operations fail."""


class AISession:
    """High-level AI session manager.

    Features:
    - Provider management (Ollama, OpenAI, etc.)
    - Context building with system prompts
    - Tool calling and execution
    - Conversation tracking and history
    - Event emission for UI updates
    - Error handling and recovery

    Usage:
        ai_session = AISession(session)
        await ai_session.initialize(provider_config)

        # Simple chat
        response = await ai_session.chat("Connect to the laser device")

        # Streaming chat
        async for chunk in ai_session.chat_stream("Analyze the recent data"):
            print(chunk)

        # Tool-enabled conversations
        response = await ai_session.chat(
            "Create a workflow to measure power vs time",
            use_tools=True
        )
    """

    def __init__(self, session: Session):
        """Initialize AI session.

        Args:
            session: LabPilot session for device and workflow access.
        """
        self.session = session
        self.provider: AIProvider | None = None
        self.context_builder = ContextBuilder(session)
        self.tool_registry = ToolRegistry(session)
        self._conversations: dict[str, AIConversation] = {}
        self._default_conversation = "default"

    async def initialize(self, provider_config: dict[str, Any]) -> None:
        """Initialize AI provider.

        Args:
            provider_config: Provider configuration dict.

        Raises:
            AISessionError: If initialization fails.
        """
        try:
            provider_type = provider_config.get("type", "ollama")

            if provider_type == "ollama":
                self.provider = OllamaProvider(
                    host=provider_config.get("base_url") or provider_config.get("host", "http://localhost:11434"),
                    default_model=provider_config.get("model", "mistral"),
                    timeout=provider_config.get("timeout", 120.0),
                )
            else:
                raise AISessionError(f"Unknown provider type: {provider_type}")

            # Test provider connection
            await self._test_provider()

            # Create default conversation
            self._conversations[self._default_conversation] = AIConversation(self._default_conversation)

            # Emit initialization event
            await self.session.bus.emit(Event(
                kind=EventKind.AI_INITIALIZED,
                data={"provider": provider_type, "model": provider_config.get("model")}
            ))

        except Exception as e:
            raise AISessionError(f"AI initialization failed: {e}")

    async def _test_provider(self) -> None:
        """Test provider connection with health check."""
        if not self.provider:
            raise AISessionError("No provider configured")

        try:
            is_healthy = await self.provider.health_check()
            if not is_healthy:
                raise AISessionError("Provider health check failed")
        except Exception as e:
            raise AISessionError(f"Provider test failed: {e}")

    async def chat(
        self,
        message: str,
        conversation_id: str = "default",
        use_tools: bool = True,
        max_tool_calls: int = 5,
    ) -> tuple[str, int]:
        """Send a chat message and get response.

        Args:
            message: User message.
            conversation_id: Conversation ID for context.
            use_tools: Whether to enable tool calling.
            max_tool_calls: Maximum number of tool calls to execute.

        Returns:
            Tuple of (response_text, tool_calls_made)

        Raises:
            AISessionError: If chat fails.
        """
        if not self.provider:
            raise AISessionError("AI not initialized")

        # Get or create conversation
        conversation = self._get_conversation(conversation_id)

        try:
            # Add user message to conversation
            user_message = AIMessage(role="user", content=message)
            conversation.add_message(user_message)

            # Build context with system prompts and conversation history
            context_messages = self._build_context_messages(conversation)

            # Get tools if enabled - FILTER for Mistral's limitations (max ~5 tools)
            if use_tools:
                all_tools = self.tool_registry.get_function_schemas()
                tools = self._filter_relevant_tools(message, all_tools)
                print(f"[DEBUG] Filtered to {len(tools)} relevant tools (from {len(all_tools)})")
            else:
                tools = []

            # Generate response with potential tool calls
            response, tool_calls_made = await self._generate_with_tools(
                context_messages, tools, max_tool_calls
            )

            # Add assistant response to conversation
            assistant_message = AIMessage(role="assistant", content=response.content)
            conversation.add_message(assistant_message)

            # Emit chat event
            await self.session.bus.emit(Event(
                kind=EventKind.AI_MESSAGE_RECEIVED,
                data={
                    "conversation_id": conversation_id,
                    "message": message,
                    "response": response.content,
                    "tool_calls": tool_calls_made,
                }
            ))

            return response.content, tool_calls_made

        except Exception as e:
            raise AISessionError(f"Chat failed: {e}")

    async def chat_stream(
        self,
        message: str,
        conversation_id: str = "default",
        use_tools: bool = False,  # Streaming typically doesn't use tools
    ) -> AsyncGenerator[str, None]:
        """Stream chat response.

        Args:
            message: User message.
            conversation_id: Conversation ID for context.
            use_tools: Whether to enable tool calling (limited in streaming).

        Yields:
            Response text chunks.

        Raises:
            AISessionError: If streaming fails.
        """
        if not self.provider:
            raise AISessionError("AI not initialized")

        conversation = self._get_conversation(conversation_id)

        try:
            # Add user message
            user_message = AIMessage(role="user", content=message)
            conversation.add_message(user_message)

            # Build context
            context_messages = self._build_context_messages(conversation)

            # Stream response
            response_text = ""
            async for chunk in self.provider.stream_complete(context_messages):
                response_text += chunk
                yield chunk

            # Add complete response to conversation
            assistant_message = AIMessage(role="assistant", content=response_text)
            conversation.add_message(assistant_message)

        except Exception as e:
            raise AISessionError(f"Streaming chat failed: {e}")

    async def _generate_with_tools(
        self,
        messages: list[AIMessage],
        tools: list[dict[str, Any]],
        max_tool_calls: int,
    ) -> tuple[AIResponse, int]:
        """Generate response with tool calling support.

        Args:
            messages: Conversation messages.
            tools: Available tools (raw dicts from tool_registry).
            max_tool_calls: Maximum tool calls to execute.

        Returns:
            Tuple of (AI response with tool call results, number of tool calls made).
        """
        # Convert tool dicts to AITool objects for provider
        ai_tools = []
        for tool_dict in tools:
            if "function" in tool_dict:
                func = tool_dict["function"]
                ai_tools.append(AITool(
                    name=func["name"],
                    description=func["description"],
                    parameters=func.get("parameters", {})
                ))

        current_messages = messages.copy()
        tool_calls_made = 0

        while tool_calls_made < max_tool_calls:
            # Generate response
            response = await self.provider.complete(current_messages, ai_tools)

            # If no tool calls, we're done
            if not response.tool_calls:
                return response, tool_calls_made

            # Add assistant message with tool calls (before tool results)
            # Convert AIToolCall objects to dicts for AIMessage
            tool_calls_dict = [
                {
                    "id": tc.id,
                    "name": tc.name,
                    "parameters": tc.parameters
                }
                for tc in response.tool_calls
            ]

            assistant_message = AIMessage(
                role="assistant",
                content=response.content or "",
                tool_calls=tool_calls_dict,
            )
            current_messages.append(assistant_message)

            # Execute tool calls
            for tool_call in response.tool_calls:
                try:
                    # Execute tool
                    result = await self.tool_registry.execute_tool(
                        tool_call.name, tool_call.parameters
                    )

                    # Add tool result message
                    tool_result_message = AIMessage(
                        role="tool",
                        content=json.dumps(result, default=str),
                        tool_call_id=tool_call.id,
                    )
                    current_messages.append(tool_result_message)

                    tool_calls_made += 1

                except ToolExecutionError as e:
                    # Add error message
                    error_message = AIMessage(
                        role="tool",
                        content=f"Tool execution error: {e}",
                        tool_call_id=tool_call.id,
                    )
                    current_messages.append(error_message)

        # Generate final response without tools
        final_response = await self.provider.complete(current_messages)
        return final_response, tool_calls_made

    def _build_context_messages(self, conversation: AIConversation) -> list[AIMessage]:
        """Build context messages with system prompts and history.

        Args:
            conversation: Conversation for context.

        Returns:
            List of messages for generation.
        """
        # Build system context
        context_messages = self.context_builder.build_context()

        # Add conversation history (recent messages) after system messages
        context_messages.extend(conversation.get_context_messages())

        return context_messages

    def _get_conversation(self, conversation_id: str) -> AIConversation:
        """Get or create conversation.

        Args:
            conversation_id: Conversation ID.

        Returns:
            AIConversation instance.
        """
        if conversation_id not in self._conversations:
            self._conversations[conversation_id] = AIConversation(conversation_id)
        return self._conversations[conversation_id]

    def list_conversations(self) -> list[str]:
        """List all conversation IDs.

        Returns:
            List of conversation IDs.
        """
        return list(self._conversations.keys())

    def get_conversation_history(self, conversation_id: str) -> list[dict[str, Any]]:
        """Get conversation message history.

        Args:
            conversation_id: Conversation ID.

        Returns:
            List of message dicts.
        """
        conversation = self._conversations.get(conversation_id)
        if not conversation:
            return []

        return [
            {
                "role": msg.role,
                "content": msg.content,
                "timestamp": getattr(msg, 'timestamp', None),
            }
            for msg in conversation.messages
        ]

    def _filter_relevant_tools(self, user_message: str, all_tools: list[dict]) -> list[dict]:
        """Filter tools based on user message relevance.

        Mistral works better with fewer tools (~5 max). This filters the most
        relevant tools based on keywords in the user message.

        Args:
            user_message: User's request message
            all_tools: All available tools from registry

        Returns:
            Filtered list of most relevant tools (max 5)
        """
        message_lower = user_message.lower()

        # Define tool priorities based on message keywords
        tool_priorities = []

        for tool in all_tools:
            tool_name = tool["function"]["name"]
            description = tool["function"]["description"].lower()
            priority = 0

            # HIGHEST priority - workflow generation from natural language
            if "generate_workflow" in tool_name and any(keyword in message_lower for keyword in [
                "create", "workflow", "scan", "measure", "record", "acquire", "experiment", "measurement"
            ]):
                priority = 200  # Highest priority for workflow generation

            # High priority matching
            elif any(keyword in message_lower for keyword in [
                "list", "show", "display", "available", "adapters", "instruments"
            ]) and "list_adapters" in tool_name:
                priority = 100

            elif (any(keyword in message_lower for keyword in [
                "connect", "add device", "instrument"
            ]) and "connect" in tool_name) or (any(keyword in message_lower for keyword in [
                "disconnect", "remove device"
            ]) and "disconnect" in tool_name):
                priority = 90

            elif any(keyword in message_lower for keyword in [
                "workflow", "create", "experiment"
            ]) and ("workflow" in tool_name or "create_workflow" in tool_name):
                priority = 80

            elif any(keyword in message_lower for keyword in [
                "start", "run", "execute"
            ]) and "start" in tool_name:
                priority = 70

            # Medium priority - workflow template tools
            elif "workflow_template" in tool_name or "list_workflow" in tool_name:
                priority = 65

            # Medium priority - partial keyword match
            elif any(keyword in message_lower for keyword in [
                "generate", "ui", "interface"
            ]) and "generate" in tool_name:
                priority = 60

            # Low priority - always include some basic tools
            elif tool_name in ["list_adapters", "connect_device", "create_workflow"]:
                priority = 20

            # Default priority for other tools
            else:
                priority = 10

            tool_priorities.append((priority, tool))

        # Sort by priority and take top 5 tools
        tool_priorities.sort(key=lambda x: x[0], reverse=True)
        filtered_tools = [tool for priority, tool in tool_priorities[:5]]

        return filtered_tools

    def clear_conversation(self, conversation_id: str) -> None:
        """Clear conversation history.

        Args:
            conversation_id: Conversation ID to clear.
        """
        if conversation_id in self._conversations:
            del self._conversations[conversation_id]

    async def shutdown(self) -> None:
        """Shutdown AI session and cleanup resources."""
        if self.provider:
            await self.provider.shutdown()
        self._conversations.clear()

        # Emit shutdown event
        await self.session.bus.emit(Event(
            kind=EventKind.AI_SHUTDOWN,
            data={}
        ))
