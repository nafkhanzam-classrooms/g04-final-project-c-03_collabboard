# =============================================================================
# CollabBoard — Database Layer (Stub)
# =============================================================================
# Owner : M3 (Data/Sync)
# Sprint: Day 1–3
#
# This module will set up the asyncpg connection pool and expose CRUD
# operations for users, rooms, room_members, canvas_objects, images,
# action_history, and saved_canvases.
#
# Reference:
#   - IMPLEMENTATION_PLAN.md §B1
#   - DATABASE_SCHEMA.md (source of truth for DDL)
#   - POSTGRESQL_MIGRATION.md
# =============================================================================
"""
Database: asyncpg pool setup, CRUD operations.

TODO (Day 1–2, M3):
    - asyncpg.create_pool() on startup
    - upsert_user, insert_room, insert_room_member, remove_room_member
    - Atomic seq update: UPDATE rooms SET seq_counter = seq_counter + 1 RETURNING
    - insert_canvas_object, update_object (JSONB merge), soft_delete_object
    - load_canvas snapshot query
"""
