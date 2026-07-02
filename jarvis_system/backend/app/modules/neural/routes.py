from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import json

router = APIRouter()

@router.websocket("/ws/telemetry")
async def neural_telemetry_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for real-time BCI (Brain-Computer Interface) telemetry.
    Expects JSON payloads matching NeuralTelemetryPayload schema.
    """
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_text()
            payload = json.loads(data)
            
            # Mock intent inference: If 'AF3' spikes, assume "execute"
            inferred = "idle"
            if payload.get("channels", {}).get("AF3", 0) > 80.0:
                inferred = "execute_primary_task"
                
            response = {"status": "received", "inferred_intent": inferred}
            await websocket.send_text(json.dumps(response))
    except WebSocketDisconnect:
        print("Neural Interface disconnected.")
