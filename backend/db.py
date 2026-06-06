# =============================================================================
# CollabBoard — Database Layer
# =============================================================================
# Owner : M3 (Data/Sync)
# Sprint: Day 1 — Pool Setup
#
# This module manages the asyncpg connection pool lifecycle and will expose
# CRUD operations for all database tables in future sprints.
#
# Pool configuration values are from POSTGRESQL_MIGRATION.md §7:
#   min_size=5, max_size=20, max_inactive_connection_lifetime=60,
#   command_timeout=10
#
# Reference:
#   - IMPLEMENTATION_PLAN.md §B1
#   - DATABASE_SCHEMA.md (source of truth for DDL)
#   - POSTGRESQL_MIGRATION.md §7 (connection pooling strategy)
# =============================================================================
"""
Database: asyncpg pool setup, CRUD operations.

Exposes:
    pool              — Module-level asyncpg.Pool instance (None until init).
    init_db_pool()    — Create the connection pool (call from lifespan startup).
    close_db_pool()   — Close the connection pool (call from lifespan shutdown).

TODO (Day 2, M3):
    - upsert_user, insert_room, insert_room_member, remove_room_member
    - Atomic seq update: UPDATE rooms SET seq_counter = seq_counter + 1 RETURNING
    - insert_canvas_object, update_object (JSONB merge), soft_delete_object
    - load_canvas snapshot query
"""

from __future__ import annotations

import os
from typing import Optional

import asyncpg

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
