# =============================================================================
# CollabBoard — FastAPI Application Entry Point
# =============================================================================
# Owner : M1 (Server & DevOps)
# Sprint: Day 1 — Skeleton
#
# This module creates the FastAPI application, registers the health-check HTTP
# endpoint, stubs the WebSocket route, and configures application lifespan
# events (startup / shutdown) for future DB pool and Redis connections.
#
# Reference:
#   - IMPLEMENTATION_PLAN.md §1, §2
#   - API_CONTRACT.md §GET /health
#   - DOCKER_DEPLOYMENT.md §8 (backend responsibilities)
# =============================================================================

from __future__ import annotations

import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

try:
    from dotenv import load_dotenv  # Optional: only needed for local dev
except ModuleNotFoundError:
    def load_dotenv() -> None:  # type: ignore[misc]
        """No-op fallback when python-dotenv is not installed."""

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------
load_dotenv()  # Load .env for local dev; Docker uses env injection

SERVER_ID: str = os.getenv("SERVER_ID", "local-dev")
SERVER_VERSION: str = "2.0"
DATABASE_URL: str = os.getenv("DATABASE_URL", "")
REDIS_URL: str = os.getenv("REDIS_URL", "")

# ---------------------------------------------------------------------------
# Application start time (for /health uptime calculation)
# ---------------------------------------------------------------------------
_start_time: float = time.time()

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIR = PROJECT_ROOT / "frontend"


# ---------------------------------------------------------------------------
# Lifespan — startup / shutdown hooks
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.

    Startup:
        - Initialize asyncpg connection pool (M3, Day 1) ✅
        - TODO (Day 3):   Initialize Redis connection pool (M1)
        - TODO (Day 5):   Start Redis pub/sub subscriber task (M1)
        - TODO (Day 9):   Start autosave background task (M3)
        - TODO (Day 9):   Start cleanup scheduler (M3)

    Shutdown:
        - Close asyncpg pool (M3, Day 1) ✅
        - TODO: Close Redis connection
        - TODO: Cancel background tasks
    """
    # -- Startup --------------------------------------------------------------
    print(f"[{SERVER_ID}] CollabBoard backend starting...")
    print(f"[{SERVER_ID}] DATABASE_URL = {DATABASE_URL}")
    print(f"[{SERVER_ID}] REDIS_URL    = {REDIS_URL}")
    print(f"[{SERVER_ID}] Serving frontend from: {FRONTEND_DIR}")

    # Initialize asyncpg connection pool (M3)
    try:
        from backend.db import init_db_pool
        await init_db_pool()
    except Exception as exc:
        print(f"[{SERVER_ID}] WARNING: Failed to initialize DB pool: {exc}")
        print(f"[{SERVER_ID}] Server will start without database connectivity.")

    yield  # Application is running

    # -- Shutdown -------------------------------------------------------------
    print(f"[{SERVER_ID}] CollabBoard backend shutting down...")

    # Close asyncpg connection pool (M3)
    try:
        from backend.db import close_db_pool
        await close_db_pool()
    except Exception as exc:
        print(f"[{SERVER_ID}] WARNING: Error closing DB pool: {exc}")


# ---------------------------------------------------------------------------
# FastAPI Application
# ---------------------------------------------------------------------------
app = FastAPI(
    title="CollabBoard",
    version=SERVER_VERSION,
    docs_url=None,       # Disable Swagger UI in production
    redoc_url=None,      # Disable ReDoc in production
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# HTTP — Health Check
# ---------------------------------------------------------------------------
@app.get("/health")
async def health_check():
    """
    Health endpoint for Docker HEALTHCHECK and Nginx upstream monitoring.

    Returns 200 with status info when server is up.
    Full implementation (with DB/Redis connectivity checks) will be added
    when connection pools are wired up (Day 3+).

    Reference: API_CONTRACT.md §GET /health
    """
    uptime = int(time.time() - _start_time)

    return JSONResponse(
        status_code=200,
        content={
            "status": "ok",
            "server_id": SERVER_ID,
            "server_version": SERVER_VERSION,
            "uptime_seconds": uptime,
            "active_connections": 0,   # TODO: wire to ConnectionManager
            "active_rooms": 0,         # TODO: wire to RoomManager
            "postgres": "pending",     # TODO: check asyncpg pool
            "redis": "pending",        # TODO: check Redis connection
        },
    )


# ---------------------------------------------------------------------------
# WebSocket — Main Endpoint (Stub)
# ---------------------------------------------------------------------------
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    Primary WebSocket endpoint for all client communication.

    Day 1: Accept connection and immediately close with a placeholder message.

    Full implementation (Day 2+):
        - hello / hello_ack handshake
        - Session state management (Redis)
        - Room join/leave flow
        - Op routing (add/modify/delete)
        - Cursor relay
        - Cursor chat relay

    Reference:
        - WEBSOCKET_PROTOCOL_EXTENSION.md
        - API_CONTRACT.md §1–§11
    """
    await websocket.accept()
    try:
        # Stub: echo the connection confirmation, then listen until disconnect
        await websocket.send_json({
            "type": "error",
            "code": "NOT_IMPLEMENTED",
            "message": "WebSocket endpoint is a Day 1 stub. Full implementation coming Day 2.",
        })
        # Keep connection open so the client can test connectivity
        while True:
            data = await websocket.receive_text()
            # Day 1: just acknowledge receipt — no business logic yet
            await websocket.send_json({
                "type": "error",
                "code": "NOT_IMPLEMENTED",
                "message": f"Received message of length {len(data)}. Processing not yet implemented.",
            })
    except WebSocketDisconnect:
        pass


# ---------------------------------------------------------------------------
# Static Files — Frontend
# ---------------------------------------------------------------------------
# Mount the frontend directory so the backend serves HTML/CSS/JS directly.
# In production, Nginx can serve static files, but for dev this is convenient.
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
