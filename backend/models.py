# =============================================================================
# CollabBoard — Pydantic Models
# =============================================================================
# Owner : M3 (Data/Sync) + M1 (Server & DevOps)
# Sprint: Day 2 — Hello handshake models
#
# This module defines Pydantic v2 models for WebSocket message validation.
# Day 2 covers the hello/hello_ack handshake and generic error messages.
# Additional models will be added in future sprints as features are built.
#
# Reference:
#   - API_CONTRACT.md §1 (hello / hello_ack)
#   - API_CONTRACT.md §Error Message Contract
#   - IMPLEMENTATION_PLAN.md §Appendix A (Frozen Contracts)
# =============================================================================
"""
Pydantic models for request validation.

Day 2 (implemented):
    - HelloMessage, HelloAckMessage, ErrorMessage

TODO (Day 3+):
    - CreateRoom, RoomCreated
    - JoinRoom, JoinAck, JoinRejected
    - LeaveRoom, LeaveAck
    - OpMessage (add/modify/delete), OpAck, OpBroadcast, OpRejected
    - CursorMove, CursorUpdate
    - CursorChat, CursorChatBroadcast
    - CanvasSnapshot
    - ImageRequest, ImageResponse
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Client → Server: hello
# ---------------------------------------------------------------------------
class HelloMessage(BaseModel):
    """
    Validates the incoming ``hello`` message from a client.

    Reference: API_CONTRACT.md §1

    Fields:
        type: Must be the literal string ``"hello"``.
        username: Non-empty, max 32 chars, printable characters only.
    """

    type: Literal["hello"]
    username: str = Field(..., min_length=1, max_length=32)

    @field_validator("username")
    @classmethod
    def username_must_be_printable(cls, v: str) -> str:
        """Reject non-printable characters and whitespace-only usernames."""
        stripped = v.strip()
        if not stripped:
            raise ValueError("Username cannot be empty or whitespace-only")
        if not stripped.isprintable():
            raise ValueError("Username must contain only printable characters")
        return stripped


# ---------------------------------------------------------------------------
# Server → Client: hello_ack
# ---------------------------------------------------------------------------
class HelloAckMessage(BaseModel):
    """
    The server's success response to a valid ``hello`` message.

    Reference: API_CONTRACT.md §1

    Fields:
        type: Always ``"hello_ack"``.
        user_id: UUID v4 string assigned by the server.
        server_version: Semantic version string (e.g. ``"2.0"``).
    """

    type: Literal["hello_ack"] = "hello_ack"
    user_id: str
    server_version: str


# ---------------------------------------------------------------------------
# Server → Client: error
# ---------------------------------------------------------------------------
class ErrorMessage(BaseModel):
    """
    Generic error message sent by the server.

    Reference: API_CONTRACT.md §Error Message Contract

    Error codes used during the hello phase:
        - ``INVALID_USERNAME``: Empty, too long, or non-printable username.
        - ``SERVER_FULL``: Max connections reached.

    Fields:
        type: Always ``"error"``.
        code: Machine-readable error code (e.g. ``"INVALID_USERNAME"``).
        message: Human-readable description.
    """

    type: Literal["error"] = "error"
    code: str
    message: str
