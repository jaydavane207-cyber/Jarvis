"""
JARVIS FastAPI backend — main entry point.

WebSocket protocol:
  Client → Server:
    { type: "chat",          text: "...", fileContent?: "...", fileName?: "..." }
    { type: "clear_history" }
    { type: "get_reminders" }

  Server → Client (streaming):
    { type: "thinking" }                  ← immediate acknowledgement
    { type: "token",   text: "..." }      ← streamed tokens (one per chunk)
    { type: "done",    text: "<full>" }   ← final assembled reply
    { type: "system",  text: "..." }      ← system messages
    { type: "reminder",text: "..." }      ← background reminder alert
    { type: "reminders_list", reminders: [...] }
    { type: "error",   text: "..." }      ← JSON parse / internal errors
"""
from __future__ import annotations
import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse, RedirectResponse, Response
from fastapi.security import HTTPBasic, HTTPBasicCredentials
import secrets

security = HTTPBasic()
from fastapi.staticfiles import StaticFiles

from .config import settings
from .agents.router import AgentRouter
from .voice.preview import router as voice_router
from .security.crypto import mfa_manager
from pydantic import BaseModel

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


# ── Application lifespan ───────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start background tasks on startup; clean up on shutdown."""
    asyncio.create_task(reminder_checker())
    asyncio.create_task(crm_checker())
    logger.info("✅ JARVIS backend started. Reminder & CRM checkers running.")
    yield
    logger.info("JARVIS backend shutting down.")


# ── App ────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="JARVIS Backend",
    description="The core routing, memory, and specialized agents powering JARVIS.",
    version="1.0.0",
    lifespan=lifespan
)

# ── 204 No Content for favicon to prevent 404 errors in browser console ──
@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return Response(status_code=204)

@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint used by Railway and uptime monitors."""
    return {"status": "healthy", "service": "JARVIS", "version": "1.0.0"}

# CORS — allow Railway domain + localhost for dev
_ALLOWED_ORIGINS = [
    "http://localhost:8000",
    "http://localhost:3000",
    "http://localhost:5173",
    os.getenv("RAILWAY_PUBLIC_DOMAIN", ""),  # auto-set by Railway
    os.getenv("CORS_ORIGIN", "*"),           # override via env if needed
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o for o in _ALLOWED_ORIGINS if o] or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def verify_credentials(credentials: HTTPBasicCredentials = Depends(security)):
    correct_username = secrets.compare_digest(credentials.username, settings.dashboard_username)
    correct_password = secrets.compare_digest(credentials.password, settings.dashboard_password)
    if not (correct_username and correct_password):
        from fastapi import HTTPException, status
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_ui(username: str = Depends(verify_credentials)):
    _DASHBOARD_INDEX = os.path.join(os.path.dirname(__file__), "dashboard", "index.html")
    if os.path.isfile(_DASHBOARD_INDEX):
        with open(_DASHBOARD_INDEX, encoding="utf-8") as f:
            return HTMLResponse(f.read())
    return HTMLResponse("Dashboard not found.", status_code=404)

# Mount the React chat webview build (extension/dist/webview)
_WEBVIEW_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "extension", "dist", "webview")
)
if os.path.isdir(_WEBVIEW_DIR):
    app.mount(
        "/assets",
        StaticFiles(directory=_WEBVIEW_DIR),
        name="webview_assets",
    )

# ── Global objects ─────────────────────────────────────────────────────────────

router = AgentRouter()
app.include_router(voice_router)


# ── Connection manager ────────────────────────────────────────────────────────

class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"New connection. Total: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info(f"Connection closed. Total: {len(self.active_connections)}")

    async def broadcast(self, message: str) -> None:
        dead: list[WebSocket] = []
        for ws in self.active_connections:
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

    def connection_count(self) -> int:
        return len(self.active_connections)


manager = ConnectionManager()


# ── Background reminder checker ───────────────────────────────────────────────

async def reminder_checker() -> None:
    """Poll every 30 s; broadcast any due reminders to all WebSocket clients."""
    while True:
        await asyncio.sleep(30)
        try:
            pending = router.reminder_store.get_pending_reminders()
            for reminder in pending:
                router.reminder_store.mark_fired(reminder["id"])
                text = f"Reminder alert, Jay: {reminder['text']}"
                logger.info(f"Firing reminder #{reminder['id']}: {reminder['text']}")
                await manager.broadcast(json.dumps({"type": "reminder", "text": text}))
        except Exception as exc:
            logger.error(f"Reminder checker error: {exc}")


# ── CRM Stay-in-Touch Checker ──────────────────────────────────────────────────

async def crm_checker() -> None:
    """Poll every 24 hours; check for dormant contacts and set reminders."""
    while True:
        try:
            from datetime import datetime, timedelta
            dormant = router.contact_store.get_dormant_contacts(days=30)
            for contact in dormant:
                # Add a reminder to reach out to this contact.
                # To prevent spamming, we only add if there isn't already a pending reminder for them.
                pending = router.reminder_store.get_pending_reminders()
                name = contact['name']
                if not any(f"Reach out to {name}" in r["text"] for r in pending):
                    # Set reminder for noon tomorrow
                    fire_at = (datetime.now() + timedelta(days=1)).replace(hour=12, minute=0, second=0)
                    router.reminder_store.add_reminder(f"Reach out to {name} (Stay in Touch)", fire_at)
                    logger.info(f"CRM Checker: Scheduled stay-in-touch reminder for {name}.")
        except Exception as exc:
            logger.error(f"CRM checker error: {exc}")
        # Wait 24 hours before checking again
        await asyncio.sleep(86400)


# ── REST Endpoints ─────────────────────────────────────────────────────────────

@app.get("/", include_in_schema=False)
async def root(username: str = Depends(verify_credentials)):
    return RedirectResponse(url="/chat")

@app.get("/chat", response_class=HTMLResponse)
async def chat_ui(username: str = Depends(verify_credentials)):
    """Serve the JARVIS React chat UI."""
    _webview_index = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "extension", "dist", "webview", "index.html")
    )
    if not os.path.isfile(_webview_index):
        return HTMLResponse(
            "<h2>Chat UI not built yet.</h2><p>Run <code>npm run compile</code> inside the <code>extension/</code> folder.</p>",
            status_code=503,
        )
    # Patch asset paths: the built HTML uses /App.js and /index.css at root,
    # so we rewrite them to /assets/* served by the mount above.
    import time
    version = int(time.time())
    with open(_webview_index, encoding="utf-8") as f:
        html = f.read()
    html = html.replace('src="/App.js"', f'src="/assets/App.js?v={version}"')
    html = html.replace('href="/index.css"', f'href="/assets/index.css?v={version}"')
    return HTMLResponse(html)


@app.get("/api", response_class=HTMLResponse)
async def api_explorer(username: str = Depends(verify_credentials)):
    """Serve the custom ANTIGRAVITY Backend API Explorer UI."""
    _api_index = os.path.join(os.path.dirname(__file__), "dashboard", "backend.html")
    if os.path.isfile(_api_index):
        with open(_api_index, encoding="utf-8") as f:
            return HTMLResponse(f.read())
    return HTMLResponse("API Explorer not found.", status_code=404)

@app.get("/privacy", response_class=HTMLResponse)
async def privacy_ui(username: str = Depends(verify_credentials)):
    """Serve the Privacy & Security UI."""
    _privacy_index = os.path.join(os.path.dirname(__file__), "dashboard", "privacy.html")
    if os.path.isfile(_privacy_index):
        with open(_privacy_index, encoding="utf-8") as f:
            return HTMLResponse(f.read())
    return HTMLResponse("Privacy UI not found.", status_code=404)


@app.get("/health")
async def health_check():
    """Health check — returns server status and model info."""
    return {
        "status":       "online",
        "model":        settings.local_model,
        "cloud_model":  settings.cloud_model,
        "connections":  manager.connection_count(),
    }


@app.get("/stats")
async def stats():
    """Live dashboard metrics — polled by the dashboard UI (no auth required;
    the /dashboard page itself is auth-guarded, so these metrics are safe)."""
    data = router.get_stats()
    data["connections"] = manager.connection_count()
    return data


@app.post("/clear_logs")
async def clear_logs():
    """Clear dashboard routing and latency logs."""
    router.clear_logs()
    return {"status": "ok", "message": "Logs cleared"}


@app.get("/api/autostart")
async def autostart_status():
    startup_folder = os.path.join(os.getenv('APPDATA'), 'Microsoft', 'Windows', 'Start Menu', 'Programs', 'Startup')
    script_path = os.path.join(startup_folder, 'jarvis_autostart.vbs')
    return {"enabled": os.path.exists(script_path)}


@app.post("/api/autostart")
async def toggle_autostart():
    startup_folder = os.path.join(os.getenv('APPDATA'), 'Microsoft', 'Windows', 'Start Menu', 'Programs', 'Startup')
    script_path = os.path.join(startup_folder, 'jarvis_autostart.vbs')
    if os.path.exists(script_path):
        os.remove(script_path)
        return {"enabled": False}
    else:
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        vbs_content = 'Set WshShell = CreateObject("WScript.Shell")\n'
        vbs_content += f'WshShell.CurrentDirectory = "{base_dir}"\n'
        vbs_content += 'WshShell.Run "cmd /c .venv\\Scripts\\activate.bat && uvicorn jarvis.main:app", 0, False\n'
        with open(script_path, "w") as f:
            f.write(vbs_content)
        return {"enabled": True}


@app.get("/api/personal/stats")
async def personal_stats():
    """Returns data for the Personal Dashboard UI."""
    store = router.personal_agent.store
    return {
        "goals": store.get_goals(),
        "health": store.get_health_logs(50),
        "finance": store.get_financial_logs(50),
        "memory": store.get_all_memory()
    }

class PrivacyClearRequest(BaseModel):
    target: str
    mfa_code: str

@app.get("/api/mfa/setup")
async def mfa_setup(username: str = Depends(verify_credentials)):
    """Returns MFA setup info (QR code)."""
    if not settings.mfa_secret:
        return {"configured": False, "message": "MFA secret not set in config."}
    return {
        "configured": True,
        "qr_base64": mfa_manager.get_qr_code_base64()
    }

@app.post("/api/privacy/clear")
async def privacy_clear(req: PrivacyClearRequest, username: str = Depends(verify_credentials)):
    """Clear personal data, protected by MFA."""
    if settings.mfa_secret and not mfa_manager.verify(req.mfa_code):
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Invalid MFA Code")
        
    if req.target == "history":
        router.memory.clear_history()
    elif req.target == "contacts":
        import sqlite3
        with sqlite3.connect(".jarvis/contacts.db") as conn:
            conn.execute("DELETE FROM contacts")
            conn.execute("DELETE FROM interactions")
    elif req.target == "personal":
        import sqlite3
        with sqlite3.connect("personal.db") as conn:
            conn.execute("DELETE FROM goals")
            conn.execute("DELETE FROM health_logs")
            conn.execute("DELETE FROM financial_logs")
            conn.execute("DELETE FROM memory_profile")
    elif req.target == "all":
        router.memory.clear_history()
        import sqlite3
        with sqlite3.connect(".jarvis/contacts.db") as conn:
            conn.execute("DELETE FROM contacts")
            conn.execute("DELETE FROM interactions")
        with sqlite3.connect("personal.db") as conn:
            conn.execute("DELETE FROM goals")
            conn.execute("DELETE FROM health_logs")
            conn.execute("DELETE FROM financial_logs")
            conn.execute("DELETE FROM memory_profile")
    else:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="Invalid target")
        
    return {"status": "ok", "message": f"Cleared {req.target} data."}

# ── WebSocket ─────────────────────────────────────────────────────────────────

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            logger.info(f"← {data[:120]}{'…' if len(data) > 120 else ''}")

            try:
                payload  = json.loads(data)
                msg_type = payload.get("type", "chat")

                # ── Clear conversation history ─────────────────────────────
                if msg_type == "clear_history":
                    router.memory.clear_history()
                    await websocket.send_text(
                        json.dumps({"type": "system", "text": "Conversation history cleared."})
                    )
                    continue

                # ── Reminders list ─────────────────────────────────────────
                if msg_type == "get_reminders":
                    reminders = router.reminder_store.get_all_upcoming()
                    await websocket.send_text(
                        json.dumps({"type": "reminders_list", "reminders": reminders})
                    )
                    continue

                # ── Get history ────────────────────────────────────────────
                if msg_type == "get_history":
                    messages = router.memory.get_recent_messages(limit=50)
                    formatted_msgs = []
                    for m in messages:
                        ts = m["timestamp"]
                        if ts and " " in ts:
                            ts = ts.replace(" ", "T") + "Z"
                        formatted_msgs.append({
                            "role": m["role"],
                            "content": m["content"],
                            "timestamp": ts,
                        })
                    await websocket.send_text(
                        json.dumps({"type": "history_list", "messages": formatted_msgs})
                    )
                    continue

                # ── Chat (streaming) ───────────────────────────────────────
                if msg_type == "chat":
                    text         = payload.get("text", "").strip()
                    file_content = payload.get("fileContent", "")
                    file_name    = payload.get("fileName",    "")
                    voice_mode   = payload.get("voice_mode") or payload.get("selectedVoiceMode") or "calm_male"
                    agent_mode   = payload.get("agent_mode", "Default Assistant")

                    if not text:
                        continue

                    # Immediate "thinking" acknowledgement
                    await websocket.send_text(json.dumps({"type": "thinking"}))

                    full_reply = ""
                    try:
                        async for token in router.route_stream(text, file_content, file_name, voice_mode, agent_mode):
                            full_reply += token
                            await websocket.send_text(
                                json.dumps({"type": "token", "text": token})
                            )
                    except Exception as exc:
                        logger.error(f"Streaming error: {exc}")
                        err_msg = (
                            f"I encountered an error processing your request, Jay. "
                            f"Details: {exc}"
                        )
                        if not full_reply:
                            full_reply = err_msg
                        await websocket.send_text(
                            json.dumps({"type": "token", "text": err_msg})
                        )
                        full_reply = err_msg

                    # Final "done" frame with the complete assembled text
                    await websocket.send_text(
                        json.dumps({"type": "done", "text": full_reply})
                    )
                    logger.info(f"→ Reply sent ({len(full_reply)} chars)")

            except json.JSONDecodeError:
                await websocket.send_text(
                    json.dumps({"type": "error", "text": "Invalid JSON"})
                )

    except WebSocketDisconnect:
        manager.disconnect(websocket)


# ── Dev entry point ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("jarvis.main:app", host="127.0.0.1", port=8000, reload=True)
