import asyncio, websockets, json
async def test():
    async with websockets.connect('ws://127.0.0.1:8000/ws') as ws:
        await ws.send(json.dumps({'type': 'chat', 'text': 'hello'}))
        while True:
            msg = await ws.recv()
            print(msg)
            if 'done' in msg: break
asyncio.run(test())
