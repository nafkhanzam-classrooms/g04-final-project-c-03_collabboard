# =============================================================================
# CollabBoard — Room Manager (Stub)
# =============================================================================
# Owner : M1 (Server & DevOps)
# Sprint: Day 3–4
#
# This module will manage room lifecycle: create, join, leave, capacity
# enforcement, and Redis session state mapping.
#
# Reference:
#   - IMPLEMENTATION_PLAN.md §B2
#   - DISTRIBUTED_SYSTEM_DESIGN.md
#   - API_CONTRACT.md §4–§6
# =============================================================================
"""
RoomManager: room create/join/leave, Redis session state.

TODO (Day 3):
    - create_room: generate 6-char code, enforce MAX_ROOMS
    - join_room: validate capacity (≤ 8), Redis room:members SET
    - leave_room: cleanup, broadcast user_left, eviction timer
    - Redis session HSET with 300s TTL
"""
