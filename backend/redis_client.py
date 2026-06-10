# =============================================================================
# CollabBoard — Async Redis Client
# =============================================================================
# Owner : M1 (Server & DevOps)
# Sprint: Day 3 — Redis session state
#
# This module manages the async Redis connection lifecycle and provides
# session state helpers for the WebSocket handshake flow.
#
# Redis key schema (from DISTRIBUTED_SYSTEM_DESIGN.md §8.1):
#   session:{user_id}  → HASH { server_id, username, room_id }  TTL 300s
#
# Reference:
#   - DISTRIBUTED_SYSTEM_DESIGN.md §2 (Tier 2: Redis)
#   - DISTRIBUTED_SYSTEM_DESIGN.md §7 (Session Lifecycle)
#   - DISTRIBUTED_SYSTEM_DESIGN.md §8.1 (Redis Key/Channel Schema)
# =============================================================================
"""
Async Redis client: connection management and session state helpers.

Exposes:
    redis_conn        — Module-level ``redis.asyncio.Redis`` instance (None until init).
    init_redis()      — Create the Redis connection (call from lifespan startup).
    close_redis()     — Close the Redis connection (call from lifespan shutdown).
    create_session()  — HSET session:{user_id} with server_id, username, room_id.
    delete_session()  — DEL session:{user_id}.
    refresh_session_ttl() — EXPIRE session:{user_id} 300.

TODO (Day 4, M1):
    - update_session_room() — HSET session:{user_id} room_id <room_id> on join/leave
TODO (Day 5, M1):
    - Pub/sub helpers (publish_to_room, subscribe_room, unsubscribe_room)
"""

from __future__ import annotations

import os
from typing import Optional

import redis.asyncio as aioredis

# ---------------------------------------------------------------------------
# Module-level connection reference
# ---------------------------------------------------------------------------
# Initialized by init_redis(), consumed by session helpers.
# Other modules import this directly:  from backend.redis_client import redis_conn
redis_conn: Optional[aioredis.Redis] = None

# ---------------------------------------------------------------------------
# Session key constants
# ---------------------------------------------------------------------------
SESSION_KEY_PREFIX: str = "session:"
SESSION_TTL_SECONDS: int = 300  # 5 minutes — per DISTRIBUTED_SYSTEM_DESIGN.md §7


# ---------------------------------------------------------------------------
# Connection Lifecycle
# ---------------------------------------------------------------------------

async def init_redis() -> aioredis.Redis:
    """
    Create the async Redis connection from the ``REDIS_URL`` environment variable.

    Uses ``redis.asyncio.from_url`` which returns a single connection client
    (not a pool), matching the design doc's "aioredis connection per backend"
    specification (DISTRIBUTED_SYSTEM_DESIGN.md §2, Tier 2).

    Verifies connectivity with a ``PING`` command.

    Raises:
        RuntimeError: If ``REDIS_URL`` is not set or empty.
        redis.ConnectionError: If Redis is unreachable.
    """
    global redis_conn

    url = os.getenv("REDIS_URL", "")
    if not url:
        raise RuntimeError(
            "REDIS_URL environment variable is not set. "
            "Ensure .env is configured or the variable is exported."
        )

    redis_conn = aioredis.from_url(
        url,
        decode_responses=True,  # Return str instead of bytes
    )

    # Verify connectivity
    try:
        pong = await redis_conn.ping()
        print(f"[redis] Connected to Redis (PING → {pong})")
    except Exception:
        redis_conn = None
        raise

    return redis_conn


async def close_redis() -> None:
    """
    Gracefully close the async Redis connection.

    Safe to call even if the connection was never initialized (no-op).
    """
    global redis_conn

    if redis_conn is not None:
        await redis_conn.aclose()
        print("[redis] Connection closed")
        redis_conn = None


# ---------------------------------------------------------------------------
# Session State Helpers
# ---------------------------------------------------------------------------

def _session_key(user_id: str) -> str:
    """Build the Redis key for a user's session hash."""
    return f"{SESSION_KEY_PREFIX}{user_id}"


async def create_session(
    user_id: str,
    server_id: str,
    username: str,
) -> bool:
    """
    Create a Redis session hash for a newly connected user.

    Redis command sequence (per DISTRIBUTED_SYSTEM_DESIGN.md §8.1):
        HSET session:{user_id} server_id <id> username <name> room_id ""
        EXPIRE session:{user_id} 300

    Args:
        user_id: UUID v4 string assigned during hello handshake.
        server_id: This backend's SERVER_ID (from environment).
        username: Display name from the hello message.

    Returns:
        True if the session was created successfully, False if Redis
        is unavailable (best-effort — connection still works locally).
    """
    if redis_conn is None:
        return False

    try:
        key = _session_key(user_id)
        await redis_conn.hset(
            key,
            mapping={
                "server_id": server_id,
                "username": username,
                "room_id": "",
            },
        )
        await redis_conn.expire(key, SESSION_TTL_SECONDS)
        return True
    except Exception as exc:
        print(f"[redis] WARNING: Failed to create session for {user_id}: {exc}")
        return False


async def delete_session(user_id: str) -> bool:
    """
    Delete a user's Redis session hash on disconnect.

    Redis command (per DISTRIBUTED_SYSTEM_DESIGN.md §8.1):
        DEL session:{user_id}

    Args:
        user_id: UUID v4 of the disconnecting user.

    Returns:
        True if the key was deleted, False if Redis is unavailable
        or the key did not exist.
    """
    if redis_conn is None:
        return False

    try:
        key = _session_key(user_id)
        deleted = await redis_conn.delete(key)
        return deleted > 0
    except Exception as exc:
        print(f"[redis] WARNING: Failed to delete session for {user_id}: {exc}")
        return False


async def refresh_session_ttl(user_id: str) -> bool:
    """
    Refresh the TTL on a user's session key.

    Called on every operation while the user is connected, per
    DISTRIBUTED_SYSTEM_DESIGN.md §8.1:
        "Any operation while in room → EXPIRE session:{user_id} 300"

    Args:
        user_id: UUID v4 of the active user.

    Returns:
        True if the TTL was set, False if Redis is unavailable
        or the key does not exist.
    """
    if redis_conn is None:
        return False

    try:
        key = _session_key(user_id)
        result = await redis_conn.expire(key, SESSION_TTL_SECONDS)
        return result
    except Exception as exc:
        print(f"[redis] WARNING: Failed to refresh TTL for {user_id}: {exc}")
        return False
