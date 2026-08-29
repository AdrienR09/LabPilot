"""AI session manager for LabPilot.

High-level interface for AI interactions that combines provider,
context building, tool execution, and conversation management.
"""

from __future__ import annotations

import json
import time
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING, Any

from core.ai.context_builder import ContextBuilder
from core.ai.ollama_provider import OllamaProvider
from core.ai.provider import (
    AIMessage,
    AIProvider,
    AIResponse,
    AITool,
)
from core.ai.tool_registry import ToolExecutionError, ToolRegistry
from core.events import Event, EventKind
from core.session import Session

# TYPE_CHECKING-only: core.config imports core.ai.ai_session at module
# level (for AIConversation) — a real, module-level import of
# core.config.workflow_sets here would be circular. Only ever used as
# __init__'s parameter type hints (passed straight through to
# ToolRegistry), never instantiated in this file.
if TYPE_CHECKING:
    from core.config import ConfigPersistence
    from core.config.workflow_sets import WorkflowSetPersistence
    from core.workflow.engine import WorkflowEngine
    from core.workflow.store import WorkflowStore

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

    def __init__(
        self,
        session: Session,
        workflow_store: WorkflowStore | None = None,
        workflow_engine: WorkflowEngine | None = None,
        workflow_set_store: WorkflowSetPersistence | None = None,
        config_persistence: ConfigPersistence | None = None,
    ):
        """Initialize AI session.

        Args:
            session: LabPilot session for device and workflow access.
            workflow_store: Passed through to ToolRegistry so workflow
                tools (create_workflow, add_node, ...) actually work —
                without it they register but fail with a clear error when
                called, instead of a confusing arity TypeError.
            workflow_engine: Passed through to ToolRegistry for
                start_workflow/stop_workflow.
            workflow_set_store: Passed through to ToolRegistry so
                AI-created/written workflows are registered as "loaded"
                (visible in the Workflows tab), not just saved.
            config_persistence: Used to persist each conversation to disk
                (ConfigPersistence.save_conversation, already implemented
                but previously never called) and to hydrate one back into
                memory on first access after a restart — lets a
                workflow-scoped chat (see core/server.py's ChatRequest.workflow_id)
                survive a backend restart instead of starting blank every
                time. None disables persistence (in-memory only, today's
                behavior).
        """
        self.session = session
        self.provider: AIProvider | None = None
        self.context_builder = ContextBuilder(session)
        self.tool_registry = ToolRegistry(session, workflow_store, workflow_engine, workflow_set_store)
        self.config_persistence = config_persistence
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
        workflow_id: str | None = None,
    ) -> tuple[str, int]:
        """Send a chat message and get response.

        Args:
            message: User message.
            conversation_id: Conversation ID for context.
            use_tools: Whether to enable tool calling.
            max_tool_calls: Maximum number of tool calls to execute.
            workflow_id: If set, scopes the system context to this workflow
                (its graph + script text, see ContextBuilder._get_current_workflow)
                so the model can see and modify the real code rather than
                generating blind — passed from the frontend when the chat
                was opened from a specific workflow (see openAIChat()).

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
            context_messages = self._build_context_messages(conversation, workflow_id)

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
            self._save_conversation(conversation)

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
        workflow_id: str | None = None,
    ) -> AsyncGenerator[str, None]:
        """Stream chat response.

        Args:
            message: User message.
            conversation_id: Conversation ID for context.
            use_tools: Whether to enable tool calling (limited in streaming).
            workflow_id: See chat()'s workflow_id — same scoping.

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
            context_messages = self._build_context_messages(conversation, workflow_id)

            # Stream response
            response_text = ""
            async for chunk in self.provider.stream_complete(context_messages):
                response_text += chunk
                yield chunk

            # Add complete response to conversation
            assistant_message = AIMessage(role="assistant", content=response_text)
            conversation.add_message(assistant_message)
            self._save_conversation(conversation)

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

    def _build_context_messages(
        self, conversation: AIConversation, workflow_id: str | None = None
    ) -> list[AIMessage]:
        """Build context messages with system prompts and history.

        Args:
            conversation: Conversation for context.
            workflow_id: Active workflow to scope the system context to.

        Returns:
            List of messages for generation.
        """
        # Build system context
        context_messages = self.context_builder.build_context(current_workflow_id=workflow_id)

        # Add conversation history (recent messages) after system messages
        context_messages.extend(conversation.get_context_messages())

        return context_messages

    def _get_conversation(self, conversation_id: str) -> AIConversation:
        """Get, hydrate-from-disk, or create a conversation.

        Args:
            conversation_id: Conversation ID.

        Returns:
            AIConversation instance.
        """
        if conversation_id not in self._conversations:
            loaded = self.config_persistence.load_conversation(conversation_id) if self.config_persistence else None
            self._conversations[conversation_id] = loaded or AIConversation(conversation_id)
        return self._conversations[conversation_id]

    def get_conversation_messages(self, conversation_id: str) -> list[AIMessage]:
        """This conversation's message history — hydrating from disk (see
        _get_conversation) if it isn't already in memory, so a
        workflow-scoped chat reopened after a restart still shows its
        prior messages instead of appearing empty. Used by
        GET /api/ai/conversations/{conversation_id}."""
        return list(self._get_conversation(conversation_id).messages)

    def _save_conversation(self, conversation: AIConversation) -> None:
        if self.config_persistence:
            try:
                self.config_persistence.save_conversation(conversation)
            except Exception as e:
                print(f"Failed to save conversation '{conversation.id}': {e}")

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

        # Requests implying real control flow (loops/conditionals/several
        # instruments in sequence) fit write_workflow_script's "just write
        # the Python" model better than building a node graph one call at
        # a time via create_workflow/add_node.
        # Any request that's really "visit N steps/positions and read
        # something at each one" is a loop even if the user never says the
        # word "loop" — stepping/scanning language counts too. Since
        # write_workflow_script (not the node-by-node create_workflow/
        # add_node path) is the only one that can express that loop at
        # all, this needs to catch the request BEFORE create_workflow's
        # broader keyword match below can outrank it.
        script_shaped = any(keyword in message_lower for keyword in [
            "loop", "repeat", "sweep", "for each", "if ", "condition", "then measure",
            "script", "python code", "step", "position", "scan", "each ",
        ])

        for tool in all_tools:
            tool_name = tool["function"]["name"]

            # Ranking create_workflow/add_node/connect_nodes lower than
            # write_workflow_script isn't enough on its own — the model
            # still sometimes picks the node-by-node tool anyway just
            # because its name reads as a closer match to "create a
            # workflow", even when it's ranked last. For a script-shaped
            # request, don't offer that path at all: only
            # write_workflow_script can express a loop over steps, so
            # there's no reason to let the model choose the one that can't.
            if script_shaped and tool_name in ("create_workflow", "add_node", "connect_nodes"):
                continue

            priority = 0

            if tool_name == "write_workflow_script" and (
                script_shaped or any(keyword in message_lower for keyword in [
                    "create", "workflow", "measure", "record", "acquire", "experiment", "measurement"
                ])
            ):
                priority = 200 if script_shaped else 90

            elif tool_name == "create_workflow" and any(keyword in message_lower for keyword in [
                "create", "workflow", "measure", "record", "acquire", "experiment", "measurement"
            ]) and not script_shaped:
                priority = 100

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
            ]) and ("workflow" in tool_name or "node" in tool_name):
                priority = 80

            elif any(keyword in message_lower for keyword in [
                "start", "run", "execute"
            ]) and "start" in tool_name:
                priority = 70

            # Low priority - always include some basic tools
            elif tool_name in ["list_adapters", "connect_device", "create_workflow", "write_workflow_script"]:
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
