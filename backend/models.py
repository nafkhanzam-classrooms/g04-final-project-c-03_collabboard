# =============================================================================
# CollabBoard — Pydantic Models (Stub)
# =============================================================================
# Owner : M3 (Data/Sync) + M1 (Server & DevOps)
# Sprint: Day 2
#
# This module will define Pydantic v2 models for all WebSocket message types,
# used for request validation and serialization.
#
# Reference:
#   - API_CONTRACT.md (all message type definitions)
#   - IMPLEMENTATION_PLAN.md §Appendix A (Frozen Contracts)
# =============================================================================
"""
Pydantic models for request validation.

TODO (Day 2):
    - HelloMessage, HelloAck
    - CreateRoom, RoomCreated
    - JoinRoom, JoinAck, JoinRejected
    - LeaveRoom, LeaveAck
    - OpMessage (add/modify/delete), OpAck, OpBroadcast, OpRejected
    - CursorMove, CursorUpdate
    - CursorChat, CursorChatBroadcast
    - CanvasSnapshot
    - ErrorMessage
    - ImageRequest, ImageResponse
"""
