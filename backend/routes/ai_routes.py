"""
AI Chat API Routes
Handles AI assistant interactions, tool calling, and workflow generation
"""

import asyncio
import sys
from pathlib import Path
from typing import Dict, Any, Optional
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

# Add src directory to Python path for imports
src_path = Path(__file__).parent.parent.parent / "src"
sys.path.insert(0, str(src_path))

from labpilot_core.ai.ai_session import AISession
from labpilot_core.ai.ollama_provider import OllamaProvider
from labpilot_core.ai.context_builder import ContextBuilder
from labpilot_core.core.session import Session
# from labpilot_core.workflow.store import WorkflowStore  # Skip for now

router = APIRouter(prefix="/ai", tags=["ai"])

# Global AI session instance
_ai_session: Optional[AISession] = None
_labpilot_session: Optional[Session] = None

class ChatMessage(BaseModel):
    message: str
    conversation_id: Optional[str] = None
    use_tools: bool = True

class ChatResponse(BaseModel):
    success: bool
    data: Dict[str, Any]
    error: Optional[str] = None

async def get_ai_session() -> AISession:
    """Get or create AI session instance."""
    global _ai_session, _labpilot_session

    if _ai_session is None:
        # Initialize LabPilot session
        if _labpilot_session is None:
            _labpilot_session = Session()
            # Initialize session asynchronously if needed
            if hasattr(_labpilot_session, 'initialize') and asyncio.iscoroutinefunction(_labpilot_session.initialize):
                await _labpilot_session.initialize()

        # Create AI session (just with session, provider comes later)
        _ai_session = AISession(_labpilot_session)

        # Initialize with provider config
        provider_config = {
            "type": "ollama",
            "host": "http://localhost:11434",
            "model": "mistral",
            "timeout": 120.0
        }
        await _ai_session.initialize(provider_config)

    return _ai_session

@router.post("/chat")
async def chat_with_ai(message: ChatMessage) -> ChatResponse:
    """Send a message to the AI assistant and get a response with tool execution."""

    try:
        ai_session = await get_ai_session()

        # Process message and execute tools
        response_text, tool_calls_made = await ai_session.chat(
            message.message,
            conversation_id=message.conversation_id or "default",
            use_tools=message.use_tools
        )

        # Get structured prompt if AI generated one
        structured_prompt = None
        if hasattr(ai_session, '_last_structured_prompt') and ai_session._last_structured_prompt:
            structured_prompt = ai_session._last_structured_prompt
            ai_session._last_structured_prompt = None  # Clear it after use

        return ChatResponse(
            success=True,
            data={
                "response": response_text,
                "conversation_id": message.conversation_id or f"conv_{int(asyncio.get_event_loop().time())}",
                "tool_calls": tool_calls_made,
                "structured_prompt": structured_prompt,
                "ai_available": True
            }
        )

    except Exception as e:
        error_msg = f"Chat failed: {str(e)}"
        print(f"[AI CHAT ERROR] {error_msg}")
        import traceback
        traceback.print_exc()

        return ChatResponse(
            success=False,
            data={},
            error=error_msg
        )

@router.get("/status")
async def get_ai_status():
    """Get AI assistant status."""

    try:
        # Check Ollama health
        provider = OllamaProvider(host="http://localhost:11434", default_model="mistral")
        is_healthy = await provider.health_check()

        if is_healthy:
            # Get available models
            available_models = await provider.list_models()

            return JSONResponse({
                "success": True,
                "data": {
                    "ai_available": True,
                    "provider": "ollama",
                    "host": "localhost:11434",
                    "model": "mistral",
                    "available_models": available_models,
                    "tools_available": True
                }
            })
        else:
            return JSONResponse({
                "success": True,
                "data": {
                    "ai_available": False,
                    "provider": "ollama",
                    "host": "localhost:11434",
                    "error": "Ollama service not responding"
                }
            })

    except Exception as e:
        return JSONResponse({
            "success": False,
            "data": {
                "ai_available": False,
                "error": str(e)
            }
        })

@router.get("/tools")
async def list_available_tools():
    """Get list of available AI tools."""

    try:
        ai_session = await get_ai_session()

        # Get tools from AI session
        tools = ai_session.get_available_tools()

        return JSONResponse({
            "success": True,
            "data": {
                "tools": [
                    {
                        "name": tool["function"]["name"],
                        "description": tool["function"]["description"],
                        "parameters": tool["function"]["parameters"]
                    } for tool in tools
                ],
                "tool_count": len(tools)
            }
        })

    except Exception as e:
        return JSONResponse({
            "success": False,
            "data": {},
            "error": str(e)
        })

@router.post("/clear")
async def clear_conversation():
    """Clear the AI conversation history."""

    try:
        ai_session = await get_ai_session()

        # Clear conversation history
        if hasattr(ai_session.context_builder, 'clear_history'):
            ai_session.context_builder.clear_history()

        return JSONResponse({
            "success": True,
            "data": {
                "message": "Conversation cleared"
            }
        })

    except Exception as e:
        return JSONResponse({
            "success": False,
            "data": {},
            "error": str(e)
        })

@router.get("/models")
async def get_available_models():
    """Get list of available AI models."""

    try:
        provider = OllamaProvider(host="http://localhost:11434", default_model="mistral")
        models = await provider.list_models()

        return JSONResponse({
            "success": True,
            "data": {
                "models": models,
                "current_model": "mistral",
                "provider": "ollama"
            }
        })

    except Exception as e:
        return JSONResponse({
            "success": False,
            "data": {},
            "error": str(e)
        })

@router.get("/session/status")
async def get_session_status():
    """Get comprehensive session status including AI and devices."""

    try:
        # Get AI status
        provider = OllamaProvider(host="http://localhost:11434", default_model="mistral")
        ai_available = await provider.health_check()

        # Get LabPilot session info
        session_info = {
            "session_id": f"session_{int(asyncio.get_event_loop().time())}",
            "devices_connected": 0,  # This would come from actual device registry
            "ai_available": ai_available,
            "workflow_engine_running": 0,  # This would come from workflow engine
            "ollama_host": "localhost:11434",
            "model": "mistral"
        }

        return JSONResponse({
            "success": True,
            "data": session_info
        })

    except Exception as e:
        return JSONResponse({
            "success": False,
            "data": {
                "session_id": None,
                "devices_connected": 0,
                "ai_available": False,
                "workflow_engine_running": 0,
                "error": str(e)
            }
        })