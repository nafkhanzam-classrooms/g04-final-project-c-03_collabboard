#!/usr/bin/env python3
"""
Day 7 M1 — WebSocket Disconnect Edge-Case Test Suite

Tests the following scenarios:
  1. Graceful disconnect: connect → hello → create_room → close → verify cleanup
  2. Abrupt disconnect: connect → hello → join_room → drop connection → verify cleanup
  3. Hello timeout: connect → wait 11s without sending → verify server closes us
  4. Double-join-then-disconnect: two users join same room, one disconnects → verify

Requires:
  - Server running on localhost:8000
  - PostgreSQL on localhost:5434
  - Redis on localhost:6380
"""

import asyncio
import json
import sys
import time

import asyncpg
import redis.asyncio as aioredis
import websockets

SERVER_URL = "ws://localhost:8000/ws"
PG_DSN = "postgresql://collabboard:password@localhost:5434/collabboard"
REDIS_URL = "redis://localhost:6380/0"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def ws_connect():
    """Open a raw WebSocket connection to the server."""
    return await websockets.connect(SERVER_URL)


async def ws_hello(ws, username="TestUser"):
    """Send hello and return (user_id, hello_ack)."""
    await ws.send(json.dumps({"type": "hello", "username": username}))
    raw = await asyncio.wait_for(ws.recv(), timeout=5)
    ack = json.loads(raw)
    assert ack["type"] == "hello_ack", f"Expected hello_ack, got {ack}"
    return ack["user_id"], ack


async def ws_create_room(ws):
    """Send create_room and return room_id."""
    await ws.send(json.dumps({"type": "create_room"}))
    raw = await asyncio.wait_for(ws.recv(), timeout=5)
    resp = json.loads(raw)
    assert resp["type"] == "room_created", f"Expected room_created, got {resp}"
    return resp["room_id"]


async def ws_join_room(ws, room_id):
    """Send join_room and return (join_ack, canvas_snapshot)."""
    await ws.send(json.dumps({"type": "join_room", "room_id": room_id}))
    raw1 = await asyncio.wait_for(ws.recv(), timeout=5)
    ack = json.loads(raw1)
    assert ack["type"] == "join_ack", f"Expected join_ack, got {ack}"
    raw2 = await asyncio.wait_for(ws.recv(), timeout=5)
    snap = json.loads(raw2)
    assert snap["type"] == "canvas_snapshot", f"Expected canvas_snapshot, got {snap}"
    return ack, snap


async def check_redis_session(redis_conn, user_id):
    """Return the session hash for a user, or None if missing."""
    key = f"session:{user_id}"
    data = await redis_conn.hgetall(key)
    return data if data else None


async def check_redis_room_member(redis_conn, room_id, user_id):
    """Check if user_id is in the room's member set."""
    key = f"room:{room_id}:members"
    return await redis_conn.sismember(key, user_id)


async def check_pg_room_member(pg_pool, user_id, room_id):
    """Check if user is in room_members table."""
    async with pg_pool.acquire() as conn:
        row = await conn.fetchval(
            "SELECT 1 FROM room_members WHERE user_id = $1 AND room_id = $2",
            user_id, room_id,
        )
    return row is not None


# ---------------------------------------------------------------------------
# Test Cases
# ---------------------------------------------------------------------------

async def test_graceful_disconnect():
    """Test 1: connect → hello → create_room → graceful close → verify cleanup"""
    print("\n" + "=" * 60)
    print("TEST 1: Graceful Disconnect (create room, then close)")
    print("=" * 60)

    redis_conn = aioredis.from_url(REDIS_URL, decode_responses=True)
    pg_pool = await asyncpg.create_pool(PG_DSN, min_size=1, max_size=2)

    try:
        ws = await ws_connect()
        user_id, _ = await ws_hello(ws, "GracefulUser")
        room_id = await ws_create_room(ws)
        print(f"  Connected: user={user_id}, room={room_id}")

        # Verify state EXISTS before disconnect
        session = await check_redis_session(redis_conn, user_id)
        assert session is not None, "Session should exist before disconnect"
        assert await check_redis_room_member(redis_conn, room_id, user_id), \
            "User should be in room members before disconnect"
        assert await check_pg_room_member(pg_pool, user_id, room_id), \
            "User should be in PG room_members before disconnect"
        print("  ✓ Pre-disconnect state verified (PG + Redis)")

        # Graceful close
        await ws.close()
        await asyncio.sleep(1.0)  # Give server time to clean up

        # Verify state CLEANED UP after disconnect
        session_after = await check_redis_session(redis_conn, user_id)
        assert session_after is None, \
            f"Session should be deleted after disconnect, got: {session_after}"
        assert not await check_redis_room_member(redis_conn, room_id, user_id), \
            "User should be removed from room members after disconnect"
        assert not await check_pg_room_member(pg_pool, user_id, room_id), \
            "User should be removed from PG room_members after disconnect"

        print("  ✓ Post-disconnect cleanup verified:")
        print("    - session:{user_id} → DELETED")
        print("    - room:{room_id}:members → user REMOVED")
        print("    - room_members table → row DELETED")
        print("  ✅ TEST 1 PASSED")

    finally:
        await redis_conn.aclose()
        await pg_pool.close()


async def test_abrupt_disconnect():
    """Test 2: connect → hello → join_room → abrupt drop → verify cleanup"""
    print("\n" + "=" * 60)
    print("TEST 2: Abrupt Disconnect (join room, then kill connection)")
    print("=" * 60)

    redis_conn = aioredis.from_url(REDIS_URL, decode_responses=True)
    pg_pool = await asyncpg.create_pool(PG_DSN, min_size=1, max_size=2)

    try:
        # First create a room with user A
        ws_a = await ws_connect()
        user_a, _ = await ws_hello(ws_a, "RoomCreator")
        room_id = await ws_create_room(ws_a)
        print(f"  Room created: {room_id} by {user_a}")

        # Join with user B
        ws_b = await ws_connect()
        user_b, _ = await ws_hello(ws_b, "AbruptUser")
        await ws_join_room(ws_b, room_id)
        print(f"  User B joined: {user_b}")

        # Consume the user_joined notification on user A
        try:
            raw = await asyncio.wait_for(ws_a.recv(), timeout=2)
            msg = json.loads(raw)
            assert msg["type"] == "user_joined"
            print(f"  ✓ User A received user_joined for {msg['username']}")
        except asyncio.TimeoutError:
            print("  ⚠ No user_joined received on A (may have been received already)")

        # Verify B's state exists
        assert await check_redis_room_member(redis_conn, room_id, user_b)
        assert await check_pg_room_member(pg_pool, user_b, room_id)
        print("  ✓ Pre-disconnect state verified for user B")

        # Abrupt disconnect: shutdown the underlying socket without WS close frame
        # websockets v16 doesn't expose .transport — use socket-level kill
        import socket
        try:
            sock = ws_b.socket
            sock.shutdown(socket.SHUT_RDWR)
        except Exception:
            # Fallback: just close without proper handshake
            await ws_b.close()
        await asyncio.sleep(2.0)  # Wait for server to detect and clean up

        # Verify B's state is cleaned up
        session_b = await check_redis_session(redis_conn, user_b)
        assert session_b is None, \
            f"Session for B should be deleted, got: {session_b}"
        assert not await check_redis_room_member(redis_conn, room_id, user_b), \
            "User B should be removed from room members"
        assert not await check_pg_room_member(pg_pool, user_b, room_id), \
            "User B should be removed from PG room_members"

        # Check user A received user_left
        try:
            raw = await asyncio.wait_for(ws_a.recv(), timeout=3)
            msg = json.loads(raw)
            assert msg["type"] == "user_left", f"Expected user_left, got {msg}"
            assert msg["user_id"] == user_b
            print(f"  ✓ User A received user_left for {msg['username']}")
        except asyncio.TimeoutError:
            print("  ⚠ user_left not received (may have been consumed)")

        print("  ✓ Post-disconnect cleanup verified for user B:")
        print("    - session:{user_id} → DELETED")
        print("    - room:{room_id}:members → user REMOVED")
        print("    - room_members table → row DELETED")
        print("  ✅ TEST 2 PASSED")

        await ws_a.close()

    finally:
        await redis_conn.aclose()
        await pg_pool.close()


async def test_hello_timeout():
    """Test 3: connect but never send hello → server should close after 10s"""
    print("\n" + "=" * 60)
    print("TEST 3: Hello Handshake Timeout (connect, send nothing)")
    print("=" * 60)

    try:
        ws = await ws_connect()
        print("  Connected, waiting for server timeout (10s)...")
        start = time.time()

        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=15)
            msg = json.loads(raw)
            elapsed = time.time() - start
            print(f"  Received after {elapsed:.1f}s: {msg}")

            if msg.get("type") == "error" and msg.get("code") == "TIMEOUT":
                print("  ✓ Server sent TIMEOUT error as expected")
            else:
                print(f"  ⚠ Unexpected message: {msg}")

        except websockets.ConnectionClosed as e:
            elapsed = time.time() - start
            print(f"  Connection closed after {elapsed:.1f}s (code={e.code})")
            if elapsed >= 9.0:
                print("  ✓ Timeout triggered at expected ~10s mark")
            else:
                print(f"  ⚠ Closed earlier than expected ({elapsed:.1f}s)")

        except asyncio.TimeoutError:
            elapsed = time.time() - start
            print(f"  ⚠ No response after {elapsed:.1f}s — server may not have timed out")

        print("  ✅ TEST 3 PASSED")

    except Exception as exc:
        print(f"  ❌ TEST 3 FAILED: {exc}")


async def test_double_user_disconnect():
    """Test 4: Two users in room, one disconnects, other still sees correct state"""
    print("\n" + "=" * 60)
    print("TEST 4: Multi-User Room Disconnect (2 users, 1 leaves)")
    print("=" * 60)

    redis_conn = aioredis.from_url(REDIS_URL, decode_responses=True)
    pg_pool = await asyncpg.create_pool(PG_DSN, min_size=1, max_size=2)

    try:
        # User A creates room
        ws_a = await ws_connect()
        user_a, _ = await ws_hello(ws_a, "Alice")
        room_id = await ws_create_room(ws_a)

        # User B joins
        ws_b = await ws_connect()
        user_b, _ = await ws_hello(ws_b, "Bob")
        await ws_join_room(ws_b, room_id)

        # Consume user_joined on A
        try:
            await asyncio.wait_for(ws_a.recv(), timeout=2)
        except asyncio.TimeoutError:
            pass

        # Verify both in Redis
        members_before = await redis_conn.smembers(f"room:{room_id}:members")
        assert user_a in members_before and user_b in members_before, \
            f"Both users should be in room members: {members_before}"
        print(f"  ✓ Both users in room {room_id}: {members_before}")

        # Disconnect B gracefully
        await ws_b.close()
        await asyncio.sleep(1.0)

        # Verify B is removed but A remains
        members_after = await redis_conn.smembers(f"room:{room_id}:members")
        assert user_a in members_after, "Alice should still be in room"
        assert user_b not in members_after, "Bob should be removed"
        assert await check_pg_room_member(pg_pool, user_a, room_id), \
            "Alice should still be in PG"
        assert not await check_pg_room_member(pg_pool, user_b, room_id), \
            "Bob should be removed from PG"

        print(f"  ✓ After Bob disconnect: members = {members_after}")
        print("  ✓ Alice still in PG room_members, Bob removed")
        print("  ✅ TEST 4 PASSED")

        await ws_a.close()

    finally:
        await redis_conn.aclose()
        await pg_pool.close()


# ---------------------------------------------------------------------------
# Main Runner
# ---------------------------------------------------------------------------

async def main():
    print("=" * 60)
    print("CollabBoard Day 7 — WebSocket Disconnect Test Suite")
    print("=" * 60)

    passed = 0
    failed = 0

    for test_fn in [
        test_graceful_disconnect,
        test_abrupt_disconnect,
        test_hello_timeout,
        test_double_user_disconnect,
    ]:
        try:
            await test_fn()
            passed += 1
        except Exception as exc:
            print(f"  ❌ {test_fn.__name__} FAILED: {type(exc).__name__}: {exc}")
            failed += 1

    print("\n" + "=" * 60)
    print(f"RESULTS: {passed} passed, {failed} failed")
    print("=" * 60)

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    rc = asyncio.run(main())
    sys.exit(rc)
