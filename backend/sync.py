# =============================================================================
# CollabBoard — Sync Engine
# =============================================================================
# Owner : M3 (Data/Sync)
# Sprint: Day 4 — handle_op for add operations
#
# This module implements operation dispatch: validates incoming op messages
# against the API contract, writes to PostgreSQL via db.py, and constructs
# the op_ack / op_broadcast / op_rejected response dicts.
#
# The module does NOT perform WebSocket I/O — it returns plain dicts.
# M1's main.py handler is responsible for sending the results over WebSocket
# and broadcasting to the room.
#
# Day 4 scope:
#   - handle_op: dispatches add/modify/delete
#   - _handle_add: validates AddObjectPayload, writes to PG, returns ack/broadcast
#
# Day 5 scope (TODO):
#   - _handle_modify: partial update with JSONB merge
#   - _handle_delete: soft-delete (is_deleted = TRUE)
#
# Reference:
#   - API_CONTRACT.md §9 (add), §10 (modify), §11 (delete)
#   - POSTGRESQL_MIGRATION.md §6 (transaction strategy, seq atomicity)
#   - DATABASE_SCHEMA.md §3.4 (canvas_objects table)
# =============================================================================
"""
SyncEngine: op dispatch, PostgreSQL write, response construction.

Exposes:
    handle_op(user_id, username, room_id, data) → dict
        Returns one of:
            {"status": "ok", "op_ack": {...}, "op_broadcast": {...}}
            {"status": "rejected", "op_rejected": {...}}
"""

from __future__ import annotations

from pydantic import ValidationError

from backend import db
from backend.models import AddObjectPayload


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def handle_op(
    user_id: str,
    username: str,
    room_id: str,
    data: dict,
) -> dict:
    """
    Dispatch an incoming ``op`` message to the correct handler.

    Supported ``op`` values:
        - ``"add"``    — Day 4 (implemented)
        - ``"modify"`` — Day 5 (stub, returns op_rejected)
        - ``"delete"`` — Day 5 (stub, returns op_rejected)

    Args:
        user_id: UUID v4 string of the sending user.
        username: Display name of the sending user.
        room_id: 6-character room code the user is in.
        data: The full parsed JSON message dict.

    Returns:
        A dict with ``"status"`` key set to ``"ok"`` or ``"rejected"``.
        On success, includes ``"op_ack"`` and ``"op_broadcast"`` dicts.
        On rejection, includes ``"op_rejected"`` dict.
    """
    op_type = data.get("op")

    if op_type == "add":
        return await _handle_add(user_id, username, room_id, data)

    if op_type in ("modify", "delete"):
        # Day 5 — not yet implemented
        return _rejected("invalid_properties")

    # Unknown or missing op type
    return _rejected("invalid_object_type")


# ---------------------------------------------------------------------------
# Internal: rejection helper
# ---------------------------------------------------------------------------

def _rejected(reason: str) -> dict:
    """
    Build an ``op_rejected`` response.

    Reference: API_CONTRACT.md §Error Message Contract

    Args:
        reason: One of ``invalid_object_type``, ``invalid_properties``,
                ``image_too_large``, ``object_not_found``.

    Returns:
        ``{"status": "rejected", "op_rejected": {"type": "op_rejected", "seq": null, "reason": ...}}``
    """
    return {
        "status": "rejected",
        "op_rejected": {
            "type": "op_rejected",
            "seq": None,
            "reason": reason,
        },
    }


# ---------------------------------------------------------------------------
# Internal: handle add
# ---------------------------------------------------------------------------

async def _handle_add(
    user_id: str,
    username: str,
    room_id: str,
    data: dict,
) -> dict:
    """
    Handle an ``op: "add"`` message.

    Flow:
        1. Extract ``object`` from the message.
        2. Validate via ``AddObjectPayload`` (Pydantic).
        3. Write to PostgreSQL via ``db.insert_canvas_object`` (atomic
           seq_counter + INSERT in one transaction).
        4. Construct ``op_ack`` (to sender) and ``op_broadcast``
           (to other room members).

    Reference: API_CONTRACT.md §9

    Args:
        user_id: Creator's UUID.
        username: Creator's display name.
        room_id: Room the object belongs to.
        data: Full parsed message dict.

    Returns:
        Success or rejection dict (see ``handle_op`` docstring).
    """
    # --- Step 1: Extract object payload --------------------------------------
    obj_data = data.get("object")
    if not isinstance(obj_data, dict):
        return _rejected("invalid_properties")

    # --- Step 2: Validate via Pydantic ---------------------------------------
    try:
        payload = AddObjectPayload.model_validate(obj_data)
    except ValidationError as exc:
        # Determine the most specific rejection reason
        for err in exc.errors():
            loc = err.get("loc", ())
            if "obj_type" in loc:
                return _rejected("invalid_object_type")
        return _rejected("invalid_properties")

    # --- Step 3: Write to PostgreSQL -----------------------------------------
    try:
        seq, obj_id, created_at = await db.insert_canvas_object(
            room_id=room_id,
            user_id=user_id,
            obj_type=payload.obj_type,
            z_index=payload.z_index,
            color=payload.color,
            stroke_width=payload.stroke_width,
            properties=payload.properties,
        )
    except Exception as exc:
        print(f"[sync] ERROR: insert_canvas_object failed: {exc}")
        return _rejected("invalid_properties")

    # --- Step 4: Build response dicts ----------------------------------------
    op_ack = {
        "type": "op_ack",
        "seq": seq,
        "obj_id": obj_id,
    }

    broadcast_object = {
        "obj_id": obj_id,
        "obj_type": payload.obj_type,
        "created_by": user_id,
        "created_at": created_at,
        "z_index": payload.z_index,
        "color": payload.color,
        "stroke_width": payload.stroke_width,
        "properties": payload.properties,
    }

    op_broadcast = {
        "type": "op_broadcast",
        "op": "add",
        "seq": seq,
        "object": broadcast_object,
    }

    print(
        f"[sync] add: {payload.obj_type} by {username} "
        f"in room {room_id} → seq={seq}, obj_id={obj_id}"
    )

    return {
        "status": "ok",
        "op_ack": op_ack,
        "op_broadcast": op_broadcast,
    }
