# =============================================================================
# CollabBoard — FastAPI Application Entry Point
# =============================================================================
# Owner : M1 (Server & DevOps)
# Sprint: Day 2 — WebSocket hello handshake
#
# This module creates the FastAPI application, registers the health-check HTTP
# endpoint, implements the WebSocket route with hello/hello_ack handshake,
# and configures application lifespan events (startup / shutdown).
#
# Day 2 changes:
#   - Replaced WebSocket stub with real hello/hello_ack handshake
#   - Integrated ConnectionManager for client tracking
#   - Implemented session state machine (Connected → Identified)
#   - Added ping/pong app-level heartbeat support
#   - Wired active_connections count into /health endpoint
#
# Reference:
#   - IMPLEMENTATION_PLAN.md §1, §2
#   - API_CONTRACT.md §1 (hello), §3 (ping/pong), §GET /health
#   - WEBSOCKET_PROTOCOL_EXTENSION.md §1 (lifecycle), §8 (heartbeat)
#   - DOCKER_DEPLOYMENT.md §8 (backend responsibilities)
# =============================================================================

from __future__ import annotations

import json
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
from pydantic import ValidationError

from backend.connection import ConnectionManager, SessionState
from backend.models import ErrorMessage, HelloAckMessage, HelloMessage

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
# Connection Manager (singleton for this backend instance)
# ---------------------------------------------------------------------------
manager = ConnectionManager()


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
            "active_connections": manager.active_count,
            "active_rooms": 0,         # TODO: wire to RoomManager (Day 3)
            "postgres": "pending",     # TODO: check asyncpg pool
            "redis": "pending",        # TODO: check Redis connection
        },
    )


# ---------------------------------------------------------------------------
# Helper — send error and close WebSocket
# ---------------------------------------------------------------------------
async def _send_error_and_close(
    websocket: WebSocket,
    code: str,
    message: str,
    ws_close_code: int = 1008,
) -> None:
    """
    Send an error JSON message and then close the WebSocket.

    Used during the hello phase where errors are terminal
    (per WEBSOCKET_PROTOCOL_EXTENSION.md §1).

    Args:
        websocket: The active WebSocket connection.
        code: Machine-readable error code (e.g. ``"INVALID_USERNAME"``).
        message: Human-readable description.
        ws_close_code: WebSocket close status code (default 1008 Policy Violation).
    """
    error = ErrorMessage(code=code, message=message)
    try:
        await websocket.send_text(error.model_dump_json())
        await websocket.close(code=ws_close_code)
    except Exception:
        pass  # Connection may already be gone


# ---------------------------------------------------------------------------
# WebSocket — Main Endpoint
# ---------------------------------------------------------------------------
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    Primary WebSocket endpoint for all client communication.

    Implements the full WebSocket connection lifecycle:
        1. Accept WebSocket connection (state: Connected)
        2. Wait for ``hello`` message, validate username
        3. On success: assign UUID, register in ConnectionManager,
           send ``hello_ack`` (state: Identified)
        4. Enter message loop for post-handshake messages
        5. On disconnect: clean up ConnectionManager

    Error handling during hello phase:
        - Invalid JSON → error + close
        - Missing/wrong ``type`` → error + close
        - Invalid ``username`` → INVALID_USERNAME + close
        - Server at capacity → SERVER_FULL + close

    Reference:
        - WEBSOCKET_PROTOCOL_EXTENSION.md §1 (lifecycle)
        - API_CONTRACT.md §1 (hello / hello_ack)
        - API_CONTRACT.md §3 (ping / pong)
    """
    await websocket.accept()

    user_id: str | None = None

    try:
        # ==================================================================
        # PHASE 1: Hello Handshake (state: Connected)
        # ==================================================================
        # The first message MUST be a valid ``hello``. Anything else is a
        # protocol violation and the connection is closed.
        # ------------------------------------------------------------------

        # Check server capacity before processing the handshake
        if manager.is_full:
            await _send_error_and_close(
                websocket,
                code="SERVER_FULL",
                message="Server is full",
            )
            return

        # Wait for the hello message
        try:
            raw = await websocket.receive_text()
        except WebSocketDisconnect:
            return  # Client disconnected before sending hello

        # Parse JSON
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            await _send_error_and_close(
                websocket,
                code="INVALID_USERNAME",
                message="Invalid JSON payload",
            )
            return

        # Verify message type is "hello"
        if not isinstance(data, dict) or data.get("type") != "hello":
            await _send_error_and_close(
                websocket,
                code="INVALID_USERNAME",
                message="First message must be of type 'hello'",
            )
            return

        # Validate via Pydantic model
        try:
            hello = HelloMessage.model_validate(data)
        except ValidationError as exc:
            # Extract the first human-readable error
            errors = exc.errors()
            detail = errors[0].get("msg", "Invalid username") if errors else "Invalid username"
            await _send_error_and_close(
                websocket,
                code="INVALID_USERNAME",
                message=f"Username validation failed: {detail}",
            )
            return

        # -- Handshake successful: register client ----------------------------
        client = manager.register(websocket, hello.username)
        user_id = client.user_id

        # Build and send hello_ack
        ack = HelloAckMessage(
            user_id=client.user_id,
            server_version=SERVER_VERSION,
        )
        await websocket.send_text(ack.model_dump_json())

        print(
            f"[{SERVER_ID}] Client connected: "
            f"{client.username} ({client.user_id}) "
            f"[{manager.active_count} active]"
        )

        # ==================================================================
        # PHASE 2: Message Loop (state: Identified / InRoom)
        # ==================================================================
        # After the hello handshake, the client is Identified. Messages are
        # routed based on the ``type`` field. Day 2 implements ping/pong.
        # Room and op handling will be added in Day 3–4.
        # ------------------------------------------------------------------

        while True:
            raw = await websocket.receive_text()

            # Parse JSON — malformed messages close the connection
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await _send_error_and_close(
                    websocket,
                    code="INVALID_USERNAME",
                    message="Invalid JSON payload",
                )
                return

            if not isinstance(data, dict):
                await _send_error_and_close(
                    websocket,
                    code="INVALID_USERNAME",
                    message="Message must be a JSON object",
                )
                return

            msg_type = data.get("type")

            # -- ping / pong (app-level heartbeat) ----------------------------
            if msg_type == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))
                continue

            # -- State-gated messages (Day 3+ implementations) ----------------
            # These are recognized message types that are not yet implemented.
            # Respond with a placeholder so the client knows the server is
            # alive but the feature is pending.

            if client.state == SessionState.IDENTIFIED:
                if msg_type in ("create_room", "join_room"):
                    # Day 3 — Room management (M1)
                    await websocket.send_text(json.dumps({
                        "type": "error",
                        "code": "NOT_IMPLEMENTED",
                        "message": f"'{msg_type}' will be implemented in Day 3.",
                    }))
                    continue

                if msg_type in (
                    "op", "cursor_move", "cursor_chat",
                    "save_canvas", "load_canvas", "image_request",
                    "leave_room",
                ):
                    # These require InRoom state
                    await websocket.send_text(json.dumps({
                        "type": "error",
                        "code": "NOT_IN_ROOM",
                        "message": "You must join a room first.",
                    }))
                    continue

            elif client.state == SessionState.IN_ROOM:
                # Day 4+ — op routing, cursor relay, etc.
                if msg_type in (
                    "op", "cursor_move", "cursor_chat",
                    "save_canvas", "load_canvas", "image_request",
                    "leave_room",
                ):
                    await websocket.send_text(json.dumps({
                        "type": "error",
                        "code": "NOT_IMPLEMENTED",
                        "message": f"'{msg_type}' will be implemented in Day 4+.",
                    }))
                    continue

            # -- Unknown message type -----------------------------------------
            await websocket.send_text(json.dumps({
                "type": "error",
                "code": "INVALID_USERNAME",
                "message": f"Unknown message type: '{msg_type}'",
            }))

    except WebSocketDisconnect:
        pass
    except Exception as exc:
        # Catch-all for unexpected errors; log and clean up
        print(f"[{SERVER_ID}] WebSocket error for user {user_id}: {exc}")
    finally:
        # ==================================================================
        # PHASE 3: Cleanup
        # ==================================================================
        if user_id is not None:
            removed = manager.disconnect(user_id)
            if removed:
                print(
                    f"[{SERVER_ID}] Client disconnected: "
                    f"{removed.username} ({removed.user_id}) "
                    f"[{manager.active_count} active]"
                )

            # TODO (Day 3): Clean up Redis session state
            # TODO (Day 4): Broadcast user_left to room if client was in a room


# ---------------------------------------------------------------------------
# Static Files — Frontend
# ---------------------------------------------------------------------------
# Mount the frontend directory so the backend serves HTML/CSS/JS directly.
# In production, Nginx can serve static files, but for dev this is convenient.
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
