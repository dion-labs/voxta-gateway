"""
Main FastAPI application for the Voxta Gateway.

This module provides the HTTP and WebSocket endpoints for the Gateway,
following the API design specified in the architecture document.
"""

import asyncio
import contextlib
import logging
import os
import uuid
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from voxta_gateway.gateway import Gateway

# ... rest of the file ...

# ─────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────

VOXTA_URL = os.getenv("VOXTA_URL", "http://localhost:5384")
GATEWAY_PORT = int(os.getenv("GATEWAY_PORT", "8081"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# Configure logging
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper()),
    format="%(asctime)s | %(name)-20s | %(levelname)-8s | %(message)s",
)
logger = logging.getLogger("VoxtaGateway")

# ─────────────────────────────────────────────────────────────
# Gateway Instance
# ─────────────────────────────────────────────────────────────

gateway: Gateway | None = None


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Manage gateway lifecycle."""
    global gateway
    gateway = Gateway(voxta_url=VOXTA_URL, logger=logger)

    # Start gateway in background task
    task = asyncio.create_task(gateway.start())

    logger.info(f"Voxta Gateway starting on port {GATEWAY_PORT}")
    logger.info(f"Connecting to Voxta at {VOXTA_URL}")

    yield

    # Cleanup
    await gateway.stop()
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task


# ─────────────────────────────────────────────────────────────
# FastAPI App
# ─────────────────────────────────────────────────────────────

app = FastAPI(
    title="Voxta Gateway",
    description="State-mirroring gateway for the Voxta conversational AI platform",
    version="0.1.0",
    lifespan=lifespan,
)

# Static files for debug UI
base_path = os.path.dirname(os.path.abspath(__file__))
static_path = os.path.join(base_path, "..", "static")
if os.path.exists(static_path):
    app.mount("/static", StaticFiles(directory=static_path), name="static")


# ─────────────────────────────────────────────────────────────
# Request/Response Models
# ─────────────────────────────────────────────────────────────


class DialogueRequest(BaseModel):
    """Request body for sending dialogue."""

    text: str
    source: str = "user"  # "user", "game", "twitch"
    author: str | None = None
    immediate_reply: bool | None = None


class ContextRequest(BaseModel):
    """Request body for sending context updates."""

    key: str
    content: str
    description: str | None = None


class ExternalSpeakerStartRequest(BaseModel):
    """Request body for external speaker start."""

    source: str  # "game", "user"
    reason: str | None = None


class ExternalSpeakerStopRequest(BaseModel):
    """Request body for external speaker stop."""

    trigger_response: bool = True


class TTSPlaybackRequest(BaseModel):
    """Request body for TTS playback signals."""

    character_id: str
    message_id: str | None = None


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    voxta_connected: bool


class StateResponse(BaseModel):
    """Gateway state response."""

    connected: bool
    chat_active: bool
    ai_state: str
    external_speaker_active: bool
    external_speaker_source: str | None
    characters: list[dict]


# ─────────────────────────────────────────────────────────────
# HTTP Endpoints - Health & State
# ─────────────────────────────────────────────────────────────


@app.get("/")
async def get_index():
    """Serve the debug UI."""
    index_path = os.path.join(static_path, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "Voxta Gateway API", "docs": "/docs"}


@app.get("/health", response_model=HealthResponse)
async def health():
    """Check gateway health and Voxta connection status."""
    if not gateway:
        raise HTTPException(status_code=503, detail="Gateway not initialized")

    return HealthResponse(
        status="ok",
        voxta_connected=gateway.state.connected,
    )


@app.get("/state", response_model=StateResponse)
async def get_state():
    """Get current gateway state snapshot."""
    if not gateway:
        raise HTTPException(status_code=503, detail="Gateway not initialized")

    snapshot = gateway.state.to_snapshot()
    return StateResponse(**snapshot)


# ─────────────────────────────────────────────────────────────
# HTTP Endpoints - High-Level Actions
# ─────────────────────────────────────────────────────────────


@app.post("/dialogue")
async def send_dialogue(req: DialogueRequest):
    """
    Send dialogue that should appear in chat and potentially trigger AI response.

    Sources:
    - "user": Direct user input (immediate_reply defaults True)
    - "game": In-game NPC dialogue (immediate_reply defaults False)
    - "twitch": Twitch chat messages (immediate_reply defaults False)
    """
    if not gateway:
        raise HTTPException(status_code=503, detail="Gateway not initialized")

    await gateway.send_dialogue(
        text=req.text,
        source=req.source,
        author=req.author,
        immediate_reply=req.immediate_reply,
    )

    return {"status": "ok"}


@app.post("/context")
async def send_context(req: ContextRequest):
    """
    Send context update (not shown in chat, but AI knows about it).

    Use this for:
    - Chess board state updates
    - Game state information
    - Background information updates
    """
    if not gateway:
        raise HTTPException(status_code=503, detail="Gateway not initialized")

    await gateway.send_context(
        key=req.key,
        content=req.content,
        description=req.description,
    )

    return {"status": "ok"}


@app.post("/external_speaker_start")
async def external_speaker_start(req: ExternalSpeakerStartRequest):
    """
    Signal that an external speaker started talking.

    This interrupts the AI and puts the system in "busy" mode.
    Call external_speaker_stop when done.
    """
    if not gateway:
        raise HTTPException(status_code=503, detail="Gateway not initialized")

    await gateway.external_speaker_start(
        source=req.source,
        reason=req.reason,
    )

    return {"status": "ok"}


@app.post("/external_speaker_stop")
async def external_speaker_stop(req: ExternalSpeakerStopRequest | None = None):
    """
    Signal that external speaker stopped talking.

    Releases the "busy" state and optionally triggers AI response.
    """
    if req is None:
        req = ExternalSpeakerStopRequest()

    if not gateway:
        raise HTTPException(status_code=503, detail="Gateway not initialized")

    await gateway.external_speaker_stop(trigger_response=req.trigger_response)

    return {"status": "ok"}


@app.post("/tts_playback_start")
async def tts_playback_start(req: TTSPlaybackRequest):
    """
    Signal that external TTS playback started.

    The avatar bridge calls this when it starts playing audio.
    """
    if not gateway:
        raise HTTPException(status_code=503, detail="Gateway not initialized")

    await gateway.tts_playback_start(
        character_id=req.character_id,
        message_id=req.message_id,
    )

    return {"status": "ok"}


@app.post("/tts_playback_complete")
async def tts_playback_complete(req: TTSPlaybackRequest):
    """
    Signal that external TTS playback finished.

    The avatar bridge calls this when it finishes playing audio.
    """
    if not gateway:
        raise HTTPException(status_code=503, detail="Gateway not initialized")

    await gateway.tts_playback_complete(
        character_id=req.character_id,
        message_id=req.message_id,
    )

    return {"status": "ok"}


# ─────────────────────────────────────────────────────────────
# HTTP Endpoints - Debug
# ─────────────────────────────────────────────────────────────


@app.get("/debug/clients")
async def debug_clients():
    """List all connected WebSocket clients and their subscriptions."""
    if not gateway:
        raise HTTPException(status_code=503, detail="Gateway not initialized")

    return gateway.get_connected_clients()


@app.get("/debug/clients/{client_id}/history")
async def debug_client_history(client_id: str):
    """Get message history for a specific client."""
    if not gateway:
        raise HTTPException(status_code=503, detail="Gateway not initialized")

    history = gateway.get_client_history(client_id)
    if not history and client_id not in gateway.ws_manager.histories:
        raise HTTPException(status_code=404, detail="Client not found")

    return history


@app.post("/debug/clients/{client_id}/clear")
async def debug_clear_client_history(client_id: str):
    """Clear message history for a specific client."""
    if not gateway:
        raise HTTPException(status_code=503, detail="Gateway not initialized")

    gateway.ws_manager.clear_history(client_id)
    return {"status": "ok"}


@app.get("/debug/voxta/history")
async def debug_voxta_history():
    """Get raw Voxta event history."""
    if not gateway:
        raise HTTPException(status_code=503, detail="Gateway not initialized")

    return gateway.get_voxta_history()


# ─────────────────────────────────────────────────────────────
# WebSocket Endpoint
# ─────────────────────────────────────────────────────────────


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for real-time event streaming.

    Connection Protocol:
    1. Connect to /ws
    2. Send subscription message:
       {"type": "subscribe", "client_id": "my-app", "events": ["ai_state_changed"]}
    3. Receive state snapshot:
       {"type": "snapshot", "state": {...}}
    4. Receive subscribed events as they occur
    """
    if not gateway:
        await websocket.close(code=1011, reason="Gateway not initialized")
        return

    await websocket.accept()

    # Wait for subscription message
    try:
        init_msg = await asyncio.wait_for(websocket.receive_json(), timeout=10.0)
    except asyncio.TimeoutError:
        await websocket.close(code=4000, reason="Subscription timeout")
        return

    if init_msg.get("type") != "subscribe":
        await websocket.close(code=4000, reason="First message must be subscribe")
        return

    # Extract subscription info
    client_id = init_msg.get("client_id", f"anon-{uuid.uuid4().hex[:8]}")
    events = init_msg.get("events", ["all"])
    source_filters = init_msg.get("filters", {})  # Optional source filters

    # Register client
    await gateway.ws_manager.connect(websocket, client_id, events, source_filters=source_filters)

    # Send state snapshot
    await websocket.send_json(
        {
            "type": "snapshot",
            "state": gateway.state.to_snapshot(),
        }
    )

    logger.info(f"WebSocket client connected: {client_id}")

    # Keep connection alive and handle client messages
    try:
        while True:
            try:
                data = await websocket.receive_json()

                # Handle subscription updates
                if data.get("type") == "subscribe":
                    new_events = data.get("events", ["all"])
                    new_filters = data.get("filters", {})
                    gateway.ws_manager.update_subscriptions(client_id, new_events, new_filters)

                # Handle ping
                elif data.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})

            except (WebSocketDisconnect, RuntimeError):
                # Re-raise to be caught by the outer block
                raise
            except Exception as e:
                logger.warning(f"Error processing WebSocket message: {e}")

    except WebSocketDisconnect:
        logger.info(f"WebSocket client disconnected: {client_id}")
    except Exception as e:
        logger.error(f"WebSocket error for {client_id}: {e}")
    finally:
        await gateway.ws_manager.remove(client_id)


# ─────────────────────────────────────────────────────────────
# Entry Point
# ─────────────────────────────────────────────────────────────


def run():
    """Run the gateway server."""
    uvicorn.run(
        "voxta_gateway.main:app",
        host="0.0.0.0",
        port=GATEWAY_PORT,
        log_level=LOG_LEVEL.lower(),
        reload=False,
    )


if __name__ == "__main__":
    run()
