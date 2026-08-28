"""AI model router for LabPilot.

Routes each request to the appropriate Ollama model based on content analysis:
- Coder model (qwen2.5-coder): GUI generation, AnalyseNode code, DSL
- Instruct model (mistral/llama3.1): Conversation, instrument setup, planning

Simple substring matching approach - no ML needed for reliable routing.
"""

from __future__ import annotations

import logging
from typing import Literal

__all__ = ["ModelRouter"]

log = logging.getLogger(__name__)


class ModelRouter:
    """Routes requests to appropriate AI model.

    Uses simple pattern matching to determine whether user request needs:
    - Code generation capabilities (coder model)
    - General conversation and reasoning (instruct model)

    Example:
        >>> router = ModelRouter()
        >>> model = router.route("show me a spectrum plot")
        >>> assert model == "coder"
        >>>
        >>> model = router.route("how do I connect my device?")
        >>> assert model == "instruct"
    """

    # Triggers that indicate code/GUI generation is needed
    CODER_TRIGGERS = [
        # DSL generation
        "generate", "create a panel", "show me", "interface for",
        "display", "plot", "graph", "chart", "window", "gui",

        # Specific DSL functions
        "spectrum_plot", "image_view", "waveform_plot", "scatter_plot",
        "volume_view", "slider", "button", "toggle", "dropdown",

        # Code generation
        "analyse", "analysis", "function", "code", "script",
        "write code", "create function", "implement",

        # UI/visualization requests
        "visualization", "visualize", "live view", "real-time",
        "monitor", "dashboard", "control panel",

        # Programming terms
        "python", "numpy", "matplotlib", "scipy", "pandas",
        "programming", "algorithm", "calculate",
    ]

    # Triggers that indicate conversation/instruction is needed
    INSTRUCT_TRIGGERS = [
        # Questions and help
        "how", "what", "why", "when", "where", "which", "who",
        "help", "explain", "describe", "tell me", "what is",

        # Setup and configuration
        "connect", "setup", "configure", "install", "settings",
        "troubleshoot", "problem", "error", "issue", "fix",

        # Planning and workflow
        "workflow", "plan", "experiment", "procedure", "steps",
        "should I", "recommend", "suggest", "best practice",

        # General conversation
        "hello", "hi", "thanks", "thank you", "please",
        "can you", "could you", "would you", "I need",
    ]

    def __init__(self) -> None:
        """Initialize model router."""
        pass

    def route(self, user_message: str) -> Literal["coder", "instruct"]:
        """Route user message to appropriate model.

        Args:
            user_message: User's input message.

        Returns:
            Model type: "coder" for code generation, "instruct" for conversation.

        Algorithm:
        1. Count matches for coder and instruct triggers
        2. Apply weights based on trigger strength
        3. Use coder model if coder score > instruct score
        4. Default to instruct model (safer for ambiguous cases)
        """
        message_lower = user_message.lower()

        # Count trigger matches
        coder_score = self._calculate_score(message_lower, self.CODER_TRIGGERS)
        instruct_score = self._calculate_score(message_lower, self.INSTRUCT_TRIGGERS)

        # Apply additional scoring rules
        coder_score += self._apply_coder_rules(message_lower)
        instruct_score += self._apply_instruct_rules(message_lower)

        # Route based on scores
        if coder_score > instruct_score:
            model = "coder"
        else:
            model = "instruct"

        log.debug(
            f"Model routing: '{user_message[:50]}...' -> {model} "
            f"(coder: {coder_score}, instruct: {instruct_score})"
        )

        return model

    def _calculate_score(self, message: str, triggers: list[str]) -> float:
        """Calculate score based on trigger matches.

        Args:
            message: Lowercase user message.
            triggers: List of trigger phrases.

        Returns:
            Weighted score based on matches.
        """
        score = 0.0

        for trigger in triggers:
            if trigger in message:
                # Weight by trigger length (longer = more specific)
                weight = len(trigger.split())
                score += weight

                # Bonus for exact word matches (not substrings)
                words = message.split()
                if trigger in words:
                    score += 0.5

        return score

    def _apply_coder_rules(self, message: str) -> float:
        """Apply additional scoring rules for coder model.

        Args:
            message: Lowercase user message.

        Returns:
            Additional score for coder model.
        """
        bonus = 0.0

        # Strong indicators for code generation
        if any(phrase in message for phrase in [
            "dsl", "qt", "pyqt", "gui code", "write a function",
            "analysis code", "def analyse"
        ]):
            bonus += 3.0

        # Programming language mentions
        if any(lang in message for lang in [
            "python", "numpy", "scipy", "matplotlib", "pandas"
        ]):
            bonus += 1.0

        # UI component mentions
        if any(component in message for component in [
            "window", "plot", "graph", "chart", "image", "display"
        ]):
            bonus += 1.5

        # Code-like patterns
        if any(pattern in message for pattern in [
            "def ", "import ", "from ", "class ", "return ",
            "()", "[]", "{}", "="
        ]):
            bonus += 2.0

        return bonus

    def _apply_instruct_rules(self, message: str) -> float:
        """Apply additional scoring rules for instruct model.

        Args:
            message: Lowercase user message.

        Returns:
            Additional score for instruct model.
        """
        bonus = 0.0

        # Question patterns
        if message.startswith(("how ", "what ", "why ", "when ", "where ")):
            bonus += 2.0

        if message.endswith("?"):
            bonus += 1.0

        # Conversation starters
        if any(phrase in message for phrase in [
            "hello", "hi", "hey", "good morning", "good afternoon"
        ]):
            bonus += 2.0

        # Help requests
        if any(phrase in message for phrase in [
            "help me", "can you help", "I need help", "how do I",
            "please help", "assist me"
        ]):
            bonus += 1.5

        # Setup and troubleshooting
        if any(phrase in message for phrase in [
            "not working", "error", "problem", "issue", "broken",
            "can't connect", "won't start", "failed to"
        ]):
            bonus += 1.5

        # Planning and guidance
        if any(phrase in message for phrase in [
            "should I", "recommend", "best way", "how to approach",
            "what's the best", "which option"
        ]):
            bonus += 1.0

        return bonus

    def get_model_config(self, model_type: Literal["coder", "instruct"]) -> dict[str, str]:
        """Get model configuration for given type.

        Args:
            model_type: Type of model needed.

        Returns:
            Dictionary with model configuration.
        """
        if model_type == "coder":
            return {
                "model": "qwen2.5-coder:7b",
                "description": "Specialized for code generation and GUI creation",
                "temperature": 0.1,  # Lower for more deterministic code
                "capabilities": ["code_generation", "dsl", "python", "analysis"]
            }
        else:  # instruct
            return {
                "model": "mistral",
                "description": "General conversation and reasoning",
                "temperature": 0.7,  # Higher for more creative responses
                "capabilities": ["conversation", "planning", "troubleshooting", "explanation"]
            }

    def explain_routing(self, user_message: str) -> dict[str, any]:
        """Explain why a message was routed to a specific model.

        Args:
            user_message: User's input message.

        Returns:
            Dictionary with routing explanation.

        Useful for debugging and understanding routing decisions.
        """
        message_lower = user_message.lower()

        # Calculate scores with details
        coder_matches = [t for t in self.CODER_TRIGGERS if t in message_lower]
        instruct_matches = [t for t in self.INSTRUCT_TRIGGERS if t in message_lower]

        coder_score = self._calculate_score(message_lower, self.CODER_TRIGGERS)
        instruct_score = self._calculate_score(message_lower, self.INSTRUCT_TRIGGERS)

        coder_bonus = self._apply_coder_rules(message_lower)
        instruct_bonus = self._apply_instruct_rules(message_lower)

        final_coder = coder_score + coder_bonus
        final_instruct = instruct_score + instruct_bonus

        selected_model = "coder" if final_coder > final_instruct else "instruct"

        return {
            "message": user_message,
            "selected_model": selected_model,
            "scores": {
                "coder": {
                    "triggers": final_coder,
                    "base_score": coder_score,
                    "bonus": coder_bonus,
                    "matches": coder_matches
                },
                "instruct": {
                    "triggers": final_instruct,
                    "base_score": instruct_score,
                    "bonus": instruct_bonus,
                    "matches": instruct_matches
                }
            },
            "model_config": self.get_model_config(selected_model)
        }
