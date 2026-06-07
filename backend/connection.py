# =============================================================================
# CollabBoard — Connection Manager
# =============================================================================
# Owner : M1 (Server & DevOps)
# Sprint: Day 2 — WebSocket connection tracking & hello handshake
#
# This module manages active WebSocket connections, tracks client session
# state, and provides broadcast utilities for room-level messaging.
#
# Day 2 scope:
#   - In-memory client registry (dict[user_id, ClientState])
#   - hello / hello_ack handshake with UUID assignment
#   - Session state machine: Connected → Identified
#   - SERVER_FULL enforcement
#   - Graceful disconnect cleanup
#
# Day 3 will add Redis session state (HSET session:{user_id}) with 300s TTL.
#
# Reference:
#   - IMPLEMENTATION_PLAN.md §B2
#   - WEBSOCKET_PROTOCOL_EXTENSION.md §1 (lifecycle), §10 (broadcast)
#   - API_CONTRACT.md §1 (hello / hello_ack)
# =============================================================================
"""
ConnectionManager: manages active WebSocket connections.

Provides:
    - Client registration / deregistration with UUID assignment
    - hello / hello_ack handshake orchestration
    - Session state tracking (Connected → Identified → InRoom)
    - Broadcast to room members (exclude-sender pattern)
    - SERVER_FULL capacity enforcement

TODO (Day 3):
    - Integrate Redis session state (HSET session:{user_id}, TTL 300s)
    - Map active connections to their respective backend SERVER_ID
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from fastapi import WebSocket


# ---------------------------------------------------------------------------
# Session State Machine
# ---------------------------------------------------------------------------
class SessionState(str, Enum):
    """
    WebSocket session states per WEBSOCKET_PROTOCOL_EXTENSION.md §1.

    Connected  → Only ``hello`` is accepted.
    Identified → ``create_room``, ``join_room``, ``ping`` allowed.
    InRoom     → Full message set (ops, cursors, save/load, etc.)
    """

    CONNECTED = "connected"
    IDENTIFIED = "identified"
    IN_ROOM = "in_room"


# ---------------------------------------------------------------------------
# Client State
# ---------------------------------------------------------------------------
@dataclass
class ClientState:
    """
    Represents a single connected client's server-side state.

    Attributes:
        websocket: The active FastAPI WebSocket instance.
        user_id: UUID v4 assigned during hello handshake.
        username: Display name provided by the client.
        room_id: Current room (None if not in a room).
        state: Current session state in the lifecycle.
    """

    websocket: WebSocket
    user_id: str
    username: str
    room_id: Optional[str] = None
    state: SessionState = field(default=SessionState.IDENTIFIED)


# ---------------------------------------------------------------------------
# Connection Manager
# ---------------------------------------------------------------------------
class ConnectionManager:
    """
    Manages all active WebSocket connections for this backend instance.

    Thread-safety note: FastAPI runs in a single asyncio event loop, so
    no locks are needed for the ``clients`` dict. All access is
    sequential within the event loop.

    Attributes:
        MAX_CONNECTIONS: Upper limit on simultaneous connections.
        clients: Mapping of user_id → ClientState for all identified users.
    """

    MAX_CONNECTIONS: int = 100

    def __init__(self) -> None:
        self.clients: dict[str, ClientState] = {}

    # -- Properties -----------------------------------------------------------

    @property
    def active_count(self) -> int:
        """Number of currently connected and identified clients."""
        return len(self.clients)

    @property
    def is_full(self) -> bool:
        """Whether the server has reached its connection capacity."""
        return self.active_count >= self.MAX_CONNECTIONS

    # -- Registration ---------------------------------------------------------

    def register(self, websocket: WebSocket, username: str) -> ClientState:
        """
        Register a new client after a successful hello handshake.

        Generates a UUID v4 ``user_id``, creates a ``ClientState``, and adds
        it to the ``clients`` registry.

        Args:
            websocket: The WebSocket connection for this client.
            username: Validated display name from the hello message.

        Returns:
            The newly created ``ClientState``.
        """
        user_id = str(uuid.uuid4())
        client = ClientState(
            websocket=websocket,
            user_id=user_id,
            username=username,
        )
        self.clients[user_id] = client
        return client

    def disconnect(self, user_id: str) -> Optional[ClientState]:
        """
        Remove a client from the registry.

        Called on WebSocket disconnect (graceful or abrupt). Returns the
        removed ``ClientState`` so callers can perform additional cleanup
        (e.g., broadcasting ``user_left`` to the room).

        Args:
            user_id: The UUID of the disconnecting client.

        Returns:
            The removed ``ClientState``, or ``None`` if not found.
        """
        return self.clients.pop(user_id, None)

    def get_client(self, user_id: str) -> Optional[ClientState]:
        """Look up a client by user_id. Returns None if not found."""
        return self.clients.get(user_id)

    # -- Broadcast ------------------------------------------------------------

    async def broadcast_to_room(
        self,
        room_id: str,
        message: dict,
        exclude_user_id: Optional[str] = None,
    ) -> None:
        """
        Send a JSON message to all clients in a room.

        Implements the sender-exclusion pattern from
        WEBSOCKET_PROTOCOL_EXTENSION.md §10.

        Args:
            room_id: Target room identifier.
            message: Dict payload to JSON-serialize and send.
            exclude_user_id: Optional user_id to skip (e.g., the sender).
        """
        msg_str = json.dumps(message)
        for client in self.clients.values():
            if client.room_id == room_id and client.user_id != exclude_user_id:
                try:
                    await client.websocket.send_text(msg_str)
                except Exception:
                    # Connection may have died; disconnect handler will clean up
                    pass

    async def send_to_client(self, user_id: str, message: dict) -> None:
        """
        Send a JSON message to a specific client by user_id.

        Args:
            user_id: Target client's UUID.
            message: Dict payload to JSON-serialize and send.
        """
        client = self.clients.get(user_id)
        if client is not None:
            try:
                await client.websocket.send_text(json.dumps(message))
            except Exception:
                pass
