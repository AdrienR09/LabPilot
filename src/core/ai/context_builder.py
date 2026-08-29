"""AI context builder for LabPilot.

Assembles context information sent to AI providers on each turn.
Includes system prompt, current state, available resources, and conversation history.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from instruments import adapter_registry
from core.ai.provider import AIMessage
from core.session import Session
from core.workflow.store import WorkflowStore

__all__ = ["SYSTEM_PROMPT", "ContextBuilder"]


# System prompt for LabPilot AI assistant
SYSTEM_PROMPT = """You MUST use function calling tools. You are NOT allowed to write code or give explanations.

MANDATORY RULES:
1. For ANY user request - CALL A TOOL FUNCTION
2. NEVER write code examples
3. NEVER explain what you could do
4. ALWAYS call the appropriate function IMMEDIATELY

Available actions and when to use them: list_adapters (user wants to see
available instrument types); create_workflow (a simple workflow, no real
control flow); write_workflow_script (anything with real control flow —
loops, conditionals, several instruments in sequence, or changing an
EXISTING workflow's script shown below — pass the FULL script text, not a
diff, as its "script" argument); connect_device (user wants to connect an
instrument).

Any script passed as write_workflow_script's "script" argument follows
this role-based pattern (full reference: core/workflow_templates/confocal_scanner.py) —
never a hardcoded instrument id:
REQUIRED_INSTRUMENTS = {{"<role>": {{"kind": "motor"|"detector"|"source", "dimensionality": "0D"|"1D"|"2D"|"ND"}}, ...}}
async def run(session) -> dict: ...   # entry point, calls session.get("<role>") using the same role names
Inside the scan loop: await session.report_progress({{...}})  # same shape run() will return
Optional: RESULT_UI = {{"type": "image2d"|"spectrum", "value_key": ..., "x_key": ..., "y_key": ...}}
After writing an actuator's target, poll read() until in tolerance with
`await asyncio.sleep(0.01)` between polls (not sleep(0)) before reading
the detector.

You MUST invoke the action through the real function-calling mechanism,
never by writing its name as text (not "write_workflow_script(...)", not
a description of the call). If your connection cannot deliver a native
function call, respond with ONLY a single JSON object and nothing else
around it — no code fences, no prose before or after:
{{"name": "<action name>", "arguments": {{...its parameters...}}}}

State: {connected_devices} | {current_workflow}"""


class ContextBuilder:
    """Builds context for AI providers on each turn.

    Assembles all relevant state information including:
    - Current connected instruments
    - Available adapter registry
    - Active workflows
    - Recent system events
    - Conversation history

    Manages context size to stay within token limits.
    """

    def __init__(
        self,
        session: Session,
        workflow_store: WorkflowStore | None = None,
        max_context_tokens: int = 8192,
    ):
        """Initialize context builder.

        Args:
            session: LabPilot session for device/event access.
            workflow_store: Workflow store for listing workflows.
            max_context_tokens: Maximum context window size.
        """
        self.session = session
        self.workflow_store = workflow_store
        self.max_context_tokens = max_context_tokens
        self._conversation_history: list[AIMessage] = []

    def add_message(self, message: AIMessage) -> None:
        """Add message to conversation history.

        Args:
            message: AI message to add.
        """
        self._conversation_history.append(message)

        # Trim history if too long (keep last 50 messages)
        if len(self._conversation_history) > 50:
            # Keep system message + recent messages
            system_messages = [msg for msg in self._conversation_history if msg.role == "system"]
            recent_messages = [msg for msg in self._conversation_history if msg.role != "system"][-49:]
            self._conversation_history = system_messages + recent_messages

    def build_context(
        self,
        current_workflow_id: str | None = None,
        include_full_history: bool = True,
    ) -> list[AIMessage]:
        """Build complete context for AI provider.

        Args:
            current_workflow_id: Active workflow ID to include in context.
            include_full_history: Whether to include conversation history.

        Returns:
            List of messages forming the complete context.
        """
        # Start with system message
        system_message = self._build_system_message(current_workflow_id)
        messages = [system_message]

        # Add conversation history if requested
        if include_full_history:
            # Skip system messages from history (we have current one)
            history = [msg for msg in self._conversation_history if msg.role != "system"]
            messages.extend(history)

        return messages

    def _build_system_message(self, current_workflow_id: str | None = None) -> AIMessage:
        """Build system message with current state."""
        # Get connected devices
        connected_devices = self._get_connected_devices()

        # Get available adapters
        available_adapters = self._get_available_adapters()

        # Get current workflow
        current_workflow = self._get_current_workflow(current_workflow_id)

        # Get recent events
        recent_events = self._get_recent_events()

        # Get workflow library
        workflow_library = self._get_workflow_library()

        # Format system prompt
        system_content = SYSTEM_PROMPT.format(
            connected_devices=connected_devices,
            current_workflow=current_workflow,
        )

        return AIMessage(
            role="system",
            content=system_content,
            timestamp=time.time(),
        )

    def _get_connected_devices(self) -> str:
        """Get connected devices summary."""
        # Get devices from session (placeholder - session needs device registry)
        devices = []

        if not devices:
            return "No devices currently connected."

        lines = ["Connected devices:"]
        for device in devices:
            status = "✅ Connected" if device.get("connected") else "❌ Disconnected"
            lines.append(f"  • {device['name']} ({device['adapter']}) - {status}")

        return "\n".join(lines)

    def _get_available_adapters(self) -> str:
        """Get available adapters summary."""
        try:
            adapters = adapter_registry.list()

            if not adapters:
                return "No adapters available."

            # Group by category
            categories = {}
            for adapter_key, adapter_cls in adapters.items():
                try:
                    # Create temporary instance to get schema
                    instance = adapter_cls()
                    schema = instance.schema
                    category = schema.kind or "general"

                    if category not in categories:
                        categories[category] = []

                    categories[category].append({
                        "key": adapter_key,
                        "name": schema.name,
                        "tags": schema.tags[:3],  # Limit tags
                    })
                except Exception:
                    # Skip adapters that can't be instantiated
                    continue

            # Format output
            lines = [f"Available adapters ({len(adapters)} total):"]
            for category, items in categories.items():
                lines.append(f"  {category.upper()}:")
                for item in items[:5]:  # Limit items per category
                    tags = ", ".join(item["tags"]) if item["tags"] else ""
                    lines.append(f"    • {item['key']} - {tags}")
                if len(items) > 5:
                    lines.append(f"    ... and {len(items) - 5} more")

            return "\n".join(lines)

        except Exception as e:
            return f"Error loading adapters: {e}"

    def _get_current_workflow(self, workflow_id: str | None = None) -> str:
        """Get current workflow JSON — plus its script's actual source when
        it has one (a role-based/externally_authored workflow has no
        `nodes`, so `to_json()` alone would show an empty graph and hide
        the real code the user is asking to modify)."""
        if not workflow_id or not self.workflow_store:
            return "No active workflow."

        try:
            workflow = self.workflow_store.load(workflow_id)
            parts = [f"Active workflow '{workflow.name}':\n```json\n{workflow.to_json()}\n```"]
            script_path = workflow.metadata.get("script_path")
            if script_path:
                try:
                    script_text = Path(script_path).read_text()
                    parts.append(
                        f"Its current script ({script_path}) — modify this in place with "
                        f"write_workflow_script() rather than starting over, unless asked "
                        f"to replace it entirely:\n```python\n{script_text}\n```"
                    )
                except OSError as e:
                    parts.append(f"(Could not read script file {script_path}: {e})")
            return "\n\n".join(parts)
        except Exception as e:
            return f"Error loading workflow {workflow_id}: {e}"

    def _get_recent_events(self, limit: int = 10) -> str:
        """Get recent system events."""
        try:
            # Get recent events from session event bus
            recent = self.session.bus.recent(n=limit) if hasattr(self.session.bus, 'recent') else []

            if not recent:
                return "No recent events."

            lines = ["Recent system events:"]
            for event in recent[-limit:]:
                timestamp = time.strftime("%H:%M:%S", time.localtime(event.timestamp))
                lines.append(f"  {timestamp} - {event.kind.value}: {event.data}")

            return "\n".join(lines)

        except Exception as e:
            return f"Error loading events: {e}"

    def _get_workflow_library(self, limit: int = 10) -> str:
        """Get workflow library summary."""
        if not self.workflow_store:
            return "No workflow store available."

        try:
            workflows = self.workflow_store.list_all()

            if not workflows:
                return "No saved workflows."

            lines = [f"Workflow library ({len(workflows)} workflows):"]
            for wf in workflows[:limit]:
                created = time.strftime("%m/%d", time.localtime(wf.created_at))
                lines.append(f"  • {wf.name} (v{wf.current_version}, {created})")

            if len(workflows) > limit:
                lines.append(f"  ... and {len(workflows) - limit} more workflows")

            return "\n".join(lines)

        except Exception as e:
            return f"Error loading workflow library: {e}"

    def estimate_tokens(self, messages: list[AIMessage]) -> int:
        """Estimate token count for messages.

        Args:
            messages: Messages to estimate.

        Returns:
            Estimated token count (rough approximation).
        """
        # Rough estimation: 1 token ≈ 4 characters for English text
        total_chars = sum(len(msg.content) for msg in messages)
        return total_chars // 4

    def trim_context(self, messages: list[AIMessage]) -> list[AIMessage]:
        """Trim context to fit within token limit.

        Args:
            messages: Messages to trim.

        Returns:
            Trimmed messages that fit within limit.
        """
        estimated_tokens = self.estimate_tokens(messages)

        if estimated_tokens <= self.max_context_tokens:
            return messages

        # Keep system message + recent user/assistant messages
        system_messages = [msg for msg in messages if msg.role == "system"]
        other_messages = [msg for msg in messages if msg.role != "system"]

        # Remove oldest messages until we fit
        while estimated_tokens > self.max_context_tokens and other_messages:
            removed = other_messages.pop(0)
            estimated_tokens -= self.estimate_tokens([removed])

        return system_messages + other_messages

    def clear_history(self) -> None:
        """Clear conversation history."""
        self._conversation_history.clear()

    def get_history_summary(self) -> dict[str, Any]:
        """Get summary of conversation history.

        Returns:
            Dict with history statistics.
        """
        total_messages = len(self._conversation_history)
        by_role = {}

        for msg in self._conversation_history:
            by_role[msg.role] = by_role.get(msg.role, 0) + 1

        return {
            "total_messages": total_messages,
            "by_role": by_role,
            "estimated_tokens": self.estimate_tokens(self._conversation_history),
        }
