"""
CollabBoard Day 2 — WebSocket Handshake Test Suite
===================================================
Run with:  python tests/test_day2_ws.py

Prerequisites:
    1. The backend server must be running on localhost:8000
    2. Start it with:
       DATABASE_URL="" REDIS_URL="" uvicorn backend.main:app --port 8000

This script tests all hello/hello_ack scenarios automatically.
"""

import asyncio
import json
import sys

import websockets

WS_URL = "ws://127.0.0.1:8000/ws"
HEALTH_URL = "http://127.0.0.1:8000/health"

passed = 0
failed = 0


def report(name: str, ok: bool, detail: str = ""):
    global passed, failed
    if ok:
        passed += 1
        print(f"  ✅ {name}")
    else:
        failed += 1
        print(f"  ❌ {name} — {detail}")


async def run_tests():
    global passed, failed

    # ==================================================================
    # TEST 1: Valid hello → hello_ack
    # ==================================================================
    print("\n🔹 Test 1: Valid hello handshake")
    try:
        async with websockets.connect(WS_URL) as ws:
            await ws.send(json.dumps({"type": "hello", "username": "Jokowi"}))
            resp = json.loads(await ws.recv())
            report("Response type is hello_ack", resp["type"] == "hello_ack", f"got {resp.get('type')}")
            report("user_id is present", "user_id" in resp and len(resp["user_id"]) > 0)
            report("server_version is 2.0", resp.get("server_version") == "2.0", f"got {resp.get('server_version')}")
    except Exception as e:
        report("Connection", False, str(e))

    # ==================================================================
    # TEST 2: ping → pong (after hello)
    # ==================================================================
    print("\n🔹 Test 2: Ping / Pong heartbeat")
    try:
        async with websockets.connect(WS_URL) as ws:
            await ws.send(json.dumps({"type": "hello", "username": "Prabowo"}))
            await ws.recv()  # consume hello_ack

            await ws.send(json.dumps({"type": "ping"}))
            resp = json.loads(await ws.recv())
            report("ping → pong", resp["type"] == "pong", f"got {resp.get('type')}")
    except Exception as e:
        report("Connection", False, str(e))

    # ==================================================================
    # TEST 3: Empty username → INVALID_USERNAME
    # ==================================================================
    print("\n🔹 Test 3: Empty username rejected")
    try:
        async with websockets.connect(WS_URL) as ws:
            await ws.send(json.dumps({"type": "hello", "username": ""}))
            resp = json.loads(await ws.recv())
            report("Error type received", resp["type"] == "error", f"got {resp.get('type')}")
            report("Code is INVALID_USERNAME", resp.get("code") == "INVALID_USERNAME", f"got {resp.get('code')}")
    except Exception as e:
        report("Connection", False, str(e))

    # ==================================================================
    # TEST 4: Whitespace-only username → INVALID_USERNAME
    # ==================================================================
    print("\n🔹 Test 4: Whitespace-only username rejected")
    try:
        async with websockets.connect(WS_URL) as ws:
            await ws.send(json.dumps({"type": "hello", "username": "   "}))
            resp = json.loads(await ws.recv())
            report("Code is INVALID_USERNAME", resp.get("code") == "INVALID_USERNAME", f"got {resp.get('code')}")
    except Exception as e:
        report("Connection", False, str(e))

    # ==================================================================
    # TEST 5: Username too long (33 chars) → INVALID_USERNAME
    # ==================================================================
    print("\n🔹 Test 5: Too-long username (33 chars) rejected")
    try:
        async with websockets.connect(WS_URL) as ws:
            await ws.send(json.dumps({"type": "hello", "username": "A" * 33}))
            resp = json.loads(await ws.recv())
            report("Code is INVALID_USERNAME", resp.get("code") == "INVALID_USERNAME", f"got {resp.get('code')}")
    except Exception as e:
        report("Connection", False, str(e))

    # ==================================================================
    # TEST 6: Invalid JSON → error + close
    # ==================================================================
    print("\n🔹 Test 6: Invalid JSON rejected")
    try:
        async with websockets.connect(WS_URL) as ws:
            await ws.send("this is not json!!!")
            resp = json.loads(await ws.recv())
            report("Error received for bad JSON", resp["type"] == "error", f"got {resp.get('type')}")
    except Exception as e:
        report("Connection", False, str(e))

    # ==================================================================
    # TEST 7: Wrong first message type → error + close
    # ==================================================================
    print("\n🔹 Test 7: Non-hello first message rejected")
    try:
        async with websockets.connect(WS_URL) as ws:
            await ws.send(json.dumps({"type": "ping"}))  # ping before hello
            resp = json.loads(await ws.recv())
            report("Error received for non-hello", resp["type"] == "error", f"got {resp.get('type')}")
    except Exception as e:
        report("Connection", False, str(e))

    # ==================================================================
    # TEST 8: Two clients get different UUIDs
    # ==================================================================
    print("\n🔹 Test 8: Multiple clients get unique UUIDs")
    try:
        ws1 = await websockets.connect(WS_URL)
        ws2 = await websockets.connect(WS_URL)
        await ws1.send(json.dumps({"type": "hello", "username": "User1"}))
        await ws2.send(json.dumps({"type": "hello", "username": "User2"}))
        r1 = json.loads(await ws1.recv())
        r2 = json.loads(await ws2.recv())
        report("Both get hello_ack", r1["type"] == "hello_ack" and r2["type"] == "hello_ack")
        report("UUIDs are different", r1["user_id"] != r2["user_id"],
               f"both got {r1.get('user_id')}")
        await ws1.close()
        await ws2.close()
    except Exception as e:
        report("Connection", False, str(e))

    # ==================================================================
    # TEST 9: NOT_IN_ROOM for ops before joining a room
    # ==================================================================
    print("\n🔹 Test 9: Op rejected when not in room")
    try:
        async with websockets.connect(WS_URL) as ws:
            await ws.send(json.dumps({"type": "hello", "username": "Tester"}))
            await ws.recv()  # consume hello_ack

            await ws.send(json.dumps({"type": "op", "op": "add"}))
            resp = json.loads(await ws.recv())
            report("Code is NOT_IN_ROOM", resp.get("code") == "NOT_IN_ROOM", f"got {resp.get('code')}")
    except Exception as e:
        report("Connection", False, str(e))

    # ==================================================================
    # TEST 10: Health endpoint
    # ==================================================================
    print("\n🔹 Test 10: HTTP /health endpoint")
    try:
        import urllib.request
        resp = urllib.request.urlopen(HEALTH_URL)
        health = json.loads(resp.read())
        report("status is ok", health.get("status") == "ok", f"got {health.get('status')}")
        report("server_version is 2.0", health.get("server_version") == "2.0")
    except Exception as e:
        report("Health check", False, str(e))

    # ==================================================================
    # SUMMARY
    # ==================================================================
    total = passed + failed
    print("\n" + "=" * 50)
    print(f"  RESULTS: {passed}/{total} passed, {failed} failed")
    if failed == 0:
        print("  🎉 ALL TESTS PASSED!")
    else:
        print("  ⚠️  Some tests failed — check output above")
    print("=" * 50)

    return failed == 0


if __name__ == "__main__":
    print("=" * 50)
    print("  CollabBoard Day 2 — WebSocket Test Suite")
    print("=" * 50)
    print(f"  Target: {WS_URL}")

    ok = asyncio.run(run_tests())
    sys.exit(0 if ok else 1)
