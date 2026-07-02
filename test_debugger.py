import asyncio
import websockets
import json

async def test():
    uri = "ws://127.0.0.1:8000/ws"
    try:
        async with websockets.connect(uri) as websocket:
            payload = {
                "type": "chat",
                "text": "Can you debug this python code? \\n```python\\ndef add(a, b):\\n  return a - b\\n```",
                "voice_mode": "calm_male",
                "agent_mode": "Code Debugger"
            }
            await websocket.send(json.dumps(payload))
            
            while True:
                response = await websocket.recv()
                data = json.loads(response)
                print(f"Received: {data}")
                if data.get("type") == "done":
                    break
    except Exception as e:
        print(f"Error connecting: {e}")

if __name__ == "__main__":
    asyncio.run(test())
