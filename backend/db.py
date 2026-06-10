# =============================================================================
# CollabBoard — Database Layer
# =============================================================================
# Owner : M3 (Data/Sync)
# Sprint: Day 1–3 — Pool Setup + CRUD + Room Membership
#
# This module manages the asyncpg connection pool lifecycle and exposes
# CRUD operations for all database tables.
#
# Pool configuration values are from POSTGRESQL_MIGRATION.md §7:
#   min_size=5, max_size=20, max_inactive_connection_lifetime=60,
#   command_timeout=10
#
# Reference:
#   - IMPLEMENTATION_PLAN.md §B1
#   - DATABASE_SCHEMA.md (source of truth for DDL)
#   - POSTGRESQL_MIGRATION.md §6 (transaction strategy), §7 (pooling)
# =============================================================================
"""
Database: asyncpg pool setup, CRUD operations.

Exposes:
    pool              — Module-level asyncpg.Pool instance (None until init).
    init_db_pool()    — Create the connection pool (call from lifespan startup).
    close_db_pool()   — Close the connection pool (call from lifespan shutdown).
    upsert_user()     — Insert a new user row with a pre-assigned UUID.
    insert_room()     — Insert a new room row.
    next_seq()        — Atomically increment and return a room's seq_counter.
    insert_room_member() — Add a user to a room (with capacity check).
    remove_room_member() — Remove a user from a room.
    count_room_members() — Count current members in a room.
    get_room_members()   — List members with usernames (JOIN).
    RoomFullError        — Raised when a room is at max capacity (8).

TODO (Day 4+, M3):
    - insert_canvas_object, update_object (JSONB merge), soft_delete_object
    - load_canvas snapshot query
"""

from __future__ import annotations

import os
import uuid as _uuid
from typing import List, Optional

import asyncpg


# ---------------------------------------------------------------------------
# Custom Exceptions
# ---------------------------------------------------------------------------

MAX_ROOM_MEMBERS: int = 8
"""Maximum number of users allowed in a single room (spec A3)."""


class RoomFullError(Exception):
    """Raised when a room has reached its maximum capacity of 8 users.

    The M1 WebSocket handler should catch this and send a
    ``join_rejected`` message with reason ``room_full``.
    """

    def __init__(self, room_id: str, current_count: int) -> None:
        self.room_id = room_id
        self.current_count = current_count
        super().__init__(
            f"Room {room_id} is full ({current_count}/{MAX_ROOM_MEMBERS})"
        )

# ---------------------------------------------------------------------------
# Module-level pool reference
# ---------------------------------------------------------------------------
# Initialized by init_db_pool(), consumed by all CRUD functions.
# Other modules import this directly:  from backend.db import pool
pool: Optional[asyncpg.Pool] = None


async def init_db_pool() -> asyncpg.Pool:
    """
    Create and return the asyncpg connection pool.

    Reads the DSN from the ``DATABASE_URL`` environment variable, which is
    expected to be set either via ``.env`` (python-dotenv) for local dev
    or via Docker environment injection in production.

    Pool parameters per POSTGRESQL_MIGRATION.md §7:
        - min_size: 5    — keep 5 warm connections ready
        - max_size: 20   — ceiling for concurrent queries
        - max_inactive_connection_lifetime: 60s — recycle idle connections
        - command_timeout: 10s — abort queries exceeding 10 seconds

    Raises:
        RuntimeError: If ``DATABASE_URL`` is not set or empty.
        asyncpg.PostgresError: If the database is unreachable.
    """
    global pool

    dsn = os.getenv("DATABASE_URL", "")
    if not dsn:
        raise RuntimeError(
            "DATABASE_URL environment variable is not set. "
            "Ensure .env is configured or the variable is exported."
        )

    pool = await asyncpg.create_pool(
        dsn=dsn,
        min_size=5,
        max_size=20,
        max_inactive_connection_lifetime=60,
        command_timeout=10,
    )

    # Quick connectivity verification
    async with pool.acquire() as conn:
        version = await conn.fetchval("SELECT version()")
    print(f"[db] Connection pool created (min=5, max=20)")
    print(f"[db] PostgreSQL: {version}")

    return pool


async def close_db_pool() -> None:
    """
    Gracefully close the asyncpg connection pool.

    Waits for all acquired connections to be released, then closes them.
    Safe to call even if the pool was never initialized (no-op).
    """
    global pool

    if pool is not None:
        await pool.close()
        print("[db] Connection pool closed")
        pool = None


# =========================================================================
# CRUD — users (Day 2, M3)
# =========================================================================

async def upsert_user(
    user_id: str,
    username: str,
    color_hex: str = "#FFFFFF",
) -> asyncpg.Record:
    """
    Insert a new user row with a pre-assigned UUID.

    Called during the hello handshake after M1's ``ConnectionManager`` has
    generated the ``user_id``.  Since the spec enforces "No Authentication"
    (NG1), every new WebSocket connection creates a fresh user row —
    there is no conflict resolution on ``username``.

    Args:
        user_id:   UUID v4 string generated by ConnectionManager.
        username:  Display name (max 32 chars, validated by Pydantic).
        color_hex: RGB hex color string (default ``'#FFFFFF'``).

    Returns:
        The inserted ``asyncpg.Record`` with columns:
        ``user_id``, ``username``, ``color_hex``, ``created_at``.

    Raises:
        RuntimeError: If the connection pool is not initialized.
        asyncpg.UniqueViolationError: If ``user_id`` already exists
            (should never happen with UUID v4).
    """
    if pool is None:
        raise RuntimeError("Database pool is not initialized")

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO users (user_id, username, color_hex)
            VALUES ($1, $2, $3)
            RETURNING user_id, username, color_hex, created_at
            """,
            _uuid.UUID(user_id),
            username,
            color_hex,
        )
    return row


# =========================================================================
# CRUD — rooms (Day 2, M3)
# =========================================================================

async def insert_room(room_id: str) -> asyncpg.Record:
    """
    Insert a new room with the given 6-character alphanumeric code.

    All other columns use their schema defaults (``status='active'``,
    ``seq_counter=0``, ``is_dirty=FALSE``, etc.).  The ``room_id`` is
    generated by the caller (``RoomManager``, Day 3) using
    ``secrets.choice``.

    Args:
        room_id: 6-character alphanumeric room code.

    Returns:
        The inserted ``asyncpg.Record`` with columns:
        ``room_id``, ``created_at``, ``last_activity``,
        ``status``, ``seq_counter``.

    Raises:
        RuntimeError: If the connection pool is not initialized.
        asyncpg.UniqueViolationError: If the ``room_id`` already exists.
        asyncpg.CheckViolationError: If ``room_id`` fails the
            ``^[A-Za-z0-9]{6}$`` regex check.
    """
    if pool is None:
        raise RuntimeError("Database pool is not initialized")

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO rooms (room_id)
            VALUES ($1)
            RETURNING room_id, created_at, last_activity, status, seq_counter
            """,
            room_id,
        )
    return row


# =========================================================================
# CRUD — atomic sequence counter (Day 2, M3)
# =========================================================================

async def next_seq(room_id: str) -> Optional[int]:
    """
    Atomically increment and return the room's sequence counter.

    Also updates ``last_activity`` to ``now()`` and sets
    ``is_dirty = TRUE`` in the same statement, as specified in
    POSTGRESQL_MIGRATION.md §6.

    This is the critical path for every canvas operation — the
    ``RETURNING`` clause eliminates the read-modify-write race that
    would otherwise require advisory locking.

    Reference:
        - DATABASE_SCHEMA.md §6 (Performance Notes — Critical Query Paths)
        - POSTGRESQL_MIGRATION.md §6 (Seq Counter Atomicity)

    Args:
        room_id: 6-character room code.

    Returns:
        The new (incremented) sequence counter value, or ``None`` if
        the ``room_id`` does not exist (UPDATE matched 0 rows).

    Raises:
        RuntimeError: If the connection pool is not initialized.
    """
    if pool is None:
        raise RuntimeError("Database pool is not initialized")

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE rooms
            SET seq_counter   = seq_counter + 1,
                last_activity = now(),
                is_dirty      = TRUE
            WHERE room_id = $1
            RETURNING seq_counter
            """,
            room_id,
        )
    if row is None:
        return None
    return row["seq_counter"]


# =========================================================================
# CRUD — room_members (Day 3, M3)
# =========================================================================

async def insert_room_member(
    user_id: str,
    room_id: str,
) -> asyncpg.Record:
    """
    Add a user to a room, enforcing the 8-user capacity limit.

    Uses a **SERIALIZABLE** transaction to atomically:
        1. ``SELECT COUNT(*) FROM room_members WHERE room_id = $1``
        2. If count >= 8 → raise ``RoomFullError``
        3. ``INSERT INTO room_members (user_id, room_id)``
        4. ``UPDATE rooms SET last_activity = now() WHERE room_id = $1``

    The SERIALIZABLE isolation level prevents the race condition where
    two users join simultaneously and both see count=7, pushing the
    room to 9 users (per POSTGRESQL_MIGRATION.md §6).

    If a serialization conflict occurs (``asyncpg.SerializationError``),
    the caller should retry the operation once.

    Args:
        user_id: UUID v4 string of the joining user.
        room_id: 6-character room code.

    Returns:
        The inserted ``asyncpg.Record`` with columns:
        ``user_id``, ``room_id``, ``joined_at``.

    Raises:
        RoomFullError: If the room already has 8 members.
        RuntimeError: If the connection pool is not initialized.
        asyncpg.SerializationError: On serialization conflict (caller
            should retry).
        asyncpg.ForeignKeyViolationError: If user_id or room_id
            does not exist.
        asyncpg.UniqueViolationError: If the user is already in the room.
    """
    if pool is None:
        raise RuntimeError("Database pool is not initialized")

    async with pool.acquire() as conn:
        async with conn.transaction(isolation='serializable'):
            # Step 1: Check current member count
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM room_members WHERE room_id = $1",
                room_id,
            )

            # Step 2: Enforce capacity
            if count >= MAX_ROOM_MEMBERS:
                raise RoomFullError(room_id, count)

            # Step 3: Insert member row
            row = await conn.fetchrow(
                """
                INSERT INTO room_members (user_id, room_id)
                VALUES ($1, $2)
                RETURNING user_id, room_id, joined_at
                """,
                _uuid.UUID(user_id),
                room_id,
            )

            # Step 4: Touch room last_activity
            await conn.execute(
                "UPDATE rooms SET last_activity = now() WHERE room_id = $1",
                room_id,
            )

    return row


async def remove_room_member(
    user_id: str,
    room_id: str,
) -> bool:
    """
    Remove a user from a room.

    Idempotent — returns ``False`` if the membership row did not exist.
    Also updates ``rooms.last_activity`` to ``now()``.

    The schema's ``ON DELETE CASCADE`` on ``room_members`` handles
    automatic cleanup when a user or room is deleted from the parent
    table. This function handles the *explicit* leave/disconnect case.

    Args:
        user_id: UUID v4 string of the leaving user.
        room_id: 6-character room code.

    Returns:
        ``True`` if a row was deleted, ``False`` if the user was not
        a member of the room.

    Raises:
        RuntimeError: If the connection pool is not initialized.
    """
    if pool is None:
        raise RuntimeError("Database pool is not initialized")

    async with pool.acquire() as conn:
        async with conn.transaction():
            result = await conn.execute(
                "DELETE FROM room_members WHERE user_id = $1 AND room_id = $2",
                _uuid.UUID(user_id),
                room_id,
            )

            # result is a status string like 'DELETE 1' or 'DELETE 0'
            deleted = result == "DELETE 1"

            if deleted:
                await conn.execute(
                    "UPDATE rooms SET last_activity = now() WHERE room_id = $1",
                    room_id,
                )

    return deleted


async def count_room_members(room_id: str) -> int:
    """
    Count the current number of members in a room.

    Args:
        room_id: 6-character room code.

    Returns:
        Integer count of members (0 if room has no members or
        does not exist).

    Raises:
        RuntimeError: If the connection pool is not initialized.
    """
    if pool is None:
        raise RuntimeError("Database pool is not initialized")

    async with pool.acquire() as conn:
        count = await conn.fetchval(
            "SELECT COUNT(*) FROM room_members WHERE room_id = $1",
            room_id,
        )
    return count


async def get_room_members(room_id: str) -> List[asyncpg.Record]:
    """
    List all members of a room with their usernames.

    Performs a JOIN with the ``users`` table to retrieve display names.
    Used by M1 to populate the ``members`` array in ``join_ack``.

    Args:
        room_id: 6-character room code.

    Returns:
        List of ``asyncpg.Record``, each with columns:
        ``user_id`` (UUID), ``username`` (str), ``joined_at`` (datetime).

    Raises:
        RuntimeError: If the connection pool is not initialized.
    """
    if pool is None:
        raise RuntimeError("Database pool is not initialized")

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT rm.user_id, u.username, rm.joined_at
            FROM room_members rm
            JOIN users u ON u.user_id = rm.user_id
            WHERE rm.room_id = $1
            ORDER BY rm.joined_at
            """,
            room_id,
        )
    return rows
