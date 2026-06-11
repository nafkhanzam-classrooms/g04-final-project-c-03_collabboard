# =============================================================================
# CollabBoard — Background Tasks (Stub)
# =============================================================================
# Owner : M3 (Data/Sync)
# Sprint: Day 8–9
#
# This module will implement periodic background tasks using asyncio:
#   - Autosave loop (every 60s) with Redis distributed lock
#   - Cleanup loop (every 6h) with Redis distributed lock
#
# Reference:
#   - IMPLEMENTATION_PLAN.md §B4
#   - DISTRIBUTED_SYSTEM_DESIGN.md §Distributed Locks
#   - DOCKER_DEPLOYMENT.md §8 (autosave/cleanup responsibilities)
# =============================================================================
"""
Background Tasks: autosave, 30-day cleanup via Redis locks.

TODO (Day 8–9, M3):
    - autosave_loop: every 60s, SET lock:autosave NX EX 55, save dirty rooms
    - cleanup_loop: every 6h, SET lock:cleanup NX EX 21600, delete 30-day stale rooms
"""
