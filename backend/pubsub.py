# =============================================================================
# CollabBoard — Redis Pub/Sub Subscriber (Stub)
# =============================================================================
# Owner : M1 (Server & DevOps)
# Sprint: Day 5–6
#
# This module will run a dedicated asyncio task that subscribes to Redis
# room channels and relays cross-server messages to local WebSocket clients.
#
# Reference:
#   - IMPLEMENTATION_PLAN.md §B3
#   - DISTRIBUTED_SYSTEM_DESIGN.md §Cross-Server Communication
#   - DEVOPS_ARCHITECTURE.md §11
# =============================================================================
"""
Redis Subscriber: listens to room channels, relays to local WebSockets.

TODO (Day 5):
    - Dedicated asyncio task for redis.subscribe(room:{room_id})
    - Filter _server_id != MY_SERVER_ID to prevent echo
    - Relay op_broadcast, cursor_update, cursor_chat to local WS clients
"""
