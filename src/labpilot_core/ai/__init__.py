"""LabPilot AI Integration.

Provides AI-powered experiment assistance with tool calling, context awareness,
and multiple provider support (Ollama, OpenAI, etc.). Enables natural language
interaction with instruments and automated workflow generation.

Key components:
- AIProvider: Abstract interface for AI models
- OllamaProvider: Local Ollama integration
- ContextBuilder: System prompts and state awareness
- ToolRegistry: Function calling for instruments and workflows
- AISession: High-level conversation management

Usage:
    # Initialize AI session
    ai_session = AISession(session)
    await ai_session.initialize({
        "type": "ollama",
        "model": "llama3.1",
        "base_url": "http://localhost:11434"
    })

    # Chat with tool calling
    response = await ai_session.chat(
        "Connect to the laser and measure power",
        use_tools=True
    )

    # Streaming chat
    async for chunk in ai_session.chat_stream("Explain what devices are available"):
        print(chunk, end='')
"""

from labpilot_core.ai.ai_session import AIConversation, AISession, AISessionError
from labpilot_core.ai.context_builder import ContextBuilder
from labpilot_core.ai.ollama_provider import OllamaProvider
from labpilot_core.ai.provider import AIMessage, AIProvider, AIResponse, AIToolCall
from labpilot_core.ai.tool_registry import AITool, ToolExecutionError, ToolRegistry

__all__ = [
    # Core AI interfaces
    "AIProvider",
    "AIMessage",
    "AIResponse",
    "AIToolCall",

    # Provider implementations
    "OllamaProvider",

    # Context and tools
    "ContextBuilder",
    "ToolRegistry",
    "AITool",
    "ToolExecutionError",

    # Session management
    "AISession",
    "AIConversation",
    "AISessionError",
]
