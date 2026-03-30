"""
LabPilot Backend API Server
Handles Qt interface launching and instrument management
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path
import uvicorn

# Import route modules
from routes.qt_interface import router as qt_interface_router
from routes.ai_routes import router as ai_routes_router
from routes.device_routes import router as device_routes_router

# Create FastAPI app
app = FastAPI(
    title="LabPilot API",
    description="Laboratory Automation System API",
    version="1.0.0"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(qt_interface_router, prefix="/api")
app.include_router(ai_routes_router, prefix="/api")
app.include_router(device_routes_router, prefix="/api")

# Serve static files (Qt frontend)
qt_frontend_path = Path(__file__).parent.parent / "qt_frontend"
if qt_frontend_path.exists():
    app.mount("/qt_frontend", StaticFiles(directory=qt_frontend_path), name="qt_frontend")

@app.get("/")
async def root():
    return {"message": "LabPilot API Server", "version": "1.0.0"}

@app.get("/health")
async def health():
    return {"status": "healthy", "service": "labpilot-api"}

# Session status endpoint for frontend
@app.get("/api/session/status")
async def get_session_status():
    """Get session status for frontend initialization."""
    try:
        # Check if AI is available by trying to import and connect
        from routes.ai_routes import OllamaProvider
        provider = OllamaProvider(host="http://localhost:11434", default_model="mistral")
        ai_available = await provider.health_check()

        return {
            "success": True,
            "data": {
                "session_id": f"web_session_{int(__import__('time').time())}",
                "devices_connected": 0,
                "ai_available": ai_available,
                "workflow_engine_running": 0
            }
        }
    except Exception as e:
        return {
            "success": True,
            "data": {
                "session_id": f"web_session_{int(__import__('time').time())}",
                "devices_connected": 0,
                "ai_available": False,
                "workflow_engine_running": 0,
                "error": str(e)
            }
        }

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
        log_level="info"
    )