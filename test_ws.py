import asyncio
import websockets
import json

async def main():
    uri = "ws://localhost:8000/ws"
    async with websockets.connect(uri) as ws:
        await ws.send(json.dumps({"type": "hello", "username": "Alice"}))
        hello_ack = await ws.recv()
        print("ACK:", hello_ack)
        await ws.send(json.dumps({"type": "create_room"}))
        room_created = await ws.recv()
        print("CREATE:", room_created)

asyncio.run(main())
