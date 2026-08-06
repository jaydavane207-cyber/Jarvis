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
import hashlib
import json
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import HTMLResponse, FileResponse, RedirectResponse, Response
from fastapi.security import HTTPBasic, HTTPBasicCredentials
import secrets

security = HTTPBasic()
from fastapi.staticfiles import StaticFiles

from .config import settings
from .agents.router import AgentRouter
from .voice.preview import router as voice_router
from .security.crypto import mfa_manager
from .api.finance import router as finance_router
from pydantic import BaseModel

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)
# Show FINANCE CACHE HIT / MISS lines (DEBUG level) in the server log
logging.getLogger("jarvis.api.finance").setLevel(logging.DEBUG)


# ── Application lifespan ───────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start background tasks on startup; clean up on shutdown."""
    asyncio.create_task(reminder_checker())
    asyncio.create_task(crm_checker())
    asyncio.create_task(protocol_scheduler())
    asyncio.create_task(shadow_portfolio_evaluator())
    from .agents.trading_signal_scanner import trading_signal_scanner, eod_digest_scheduler
    asyncio.create_task(trading_signal_scanner(manager))
    asyncio.create_task(eod_digest_scheduler(manager))
    logger.info(
        "✅ JARVIS v2.0 backend started. "
        "Reminder, CRM, Protocol, Shadow Portfolio, and Trading Signal Scanner running."
    )
    yield
    # Pause all watchdogs on shutdown

    from .safety.kill_switch import kill_switch
    kill_switch.pause(reason="Server shutdown")
    logger.info("JARVIS backend shutting down.")


# ── App ────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="JARVIS Backend",
    description="The core routing, memory, and specialized agents powering JARVIS v2.0 (PRD-aligned).",
    version="2.0.0",
    lifespan=lifespan
)

# ── 204 No Content for favicon to prevent 404 errors in browser console ──
@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return Response(status_code=204)

# Detailed health check is defined below


# CORS — allow Railway domain + localhost for dev
_ALLOWED_ORIGINS = [
    "http://localhost:8000",
    "http://localhost:3000",
    "http://localhost:5173",
    os.getenv("RAILWAY_PUBLIC_DOMAIN", ""),  # auto-set by Railway
    os.getenv("CORS_ORIGIN", "*"),           # override via env if needed
]
# ── GZip compression (#10) ────────────────────────────────────────────────────
# Compresses responses ≥ 1 000 B (skips small JSON payloads).  The 168 KB HUD
# compresses to ~25–30 KB, cutting first-load transfer time significantly.
app.add_middleware(GZipMiddleware, minimum_size=1000)

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

# Mount the root directory to serve jarvis_hud.html and jarvis_boot.html
_ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
app.mount(
    "/hud",
    StaticFiles(directory=_ROOT_DIR, html=True),
    name="hud",
)

# ── Global objects ─────────────────────────────────────────────────────────────

router = AgentRouter()
app.include_router(voice_router)
# Finance proxy: GET /api/finance/chart/{ticker}  and  GET /api/finance/batch (#2/#6)
app.include_router(finance_router, prefix="/api/finance", tags=["Finance Proxy"])


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


# ── Protocol Scheduler (Morning & Evening Briefings) ──────────────────────────

async def protocol_scheduler() -> None:
    """Fire morning and evening briefings at configured times."""
    from datetime import time as dt_time
    from .safety.kill_switch import kill_switch

    try:
        morning_parts = settings.morning_protocol_time.split(":")
        evening_parts = settings.evening_protocol_time.split(":")
        morning_t = dt_time(int(morning_parts[0]), int(morning_parts[1]))
        evening_t = dt_time(int(evening_parts[0]), int(evening_parts[1]))
    except Exception:
        morning_t = dt_time(7, 30)
        evening_t = dt_time(21, 0)

    logger.info(
        f"Protocol Scheduler started | Morning: {morning_t} | Evening: {evening_t}"
    )

    last_morning = None
    last_evening = None

    while True:
        await kill_switch.wait_if_paused()
        await asyncio.sleep(60)

        from datetime import datetime, date
        now = datetime.now()
        today = now.date()
        ct = now.time().replace(second=0, microsecond=0)

        if ct.hour == morning_t.hour and ct.minute == morning_t.minute and last_morning != today:
            last_morning = today
            try:
                text = await router.protocol_agent.morning_briefing(router.llm)
                await manager.broadcast(
                    json.dumps({"type": "system", "text": f"🌅 Morning Protocol:\n{text}"})
                )
                logger.info("Protocol Scheduler: Morning Protocol delivered")
            except Exception as exc:
                logger.error(f"Protocol scheduler morning error: {exc}")

        if ct.hour == evening_t.hour and ct.minute == evening_t.minute and last_evening != today:
            last_evening = today
            try:
                text = await router.protocol_agent.evening_briefing(router.llm)
                await manager.broadcast(
                    json.dumps({"type": "system", "text": f"🌙 Evening Wind-Down:\n{text}"})
                )
                logger.info("Protocol Scheduler: Evening Protocol delivered")
            except Exception as exc:
                logger.error(f"Protocol scheduler evening error: {exc}")


# ── Shadow Portfolio Evaluator ─────────────────────────────────────────────────

async def shadow_portfolio_evaluator() -> None:
    """Run shadow portfolio outcome evaluation daily."""
    from .safety.kill_switch import kill_switch
    while True:
        await kill_switch.wait_if_paused()
        await asyncio.sleep(86400)  # run once per day
        try:
            updated = router.shadow_portfolio.evaluate_outcomes()
            if updated:
                logger.info(f"Shadow Portfolio: {len(updated)} outcomes evaluated")
                await manager.broadcast(
                    json.dumps({
                        "type": "system",
                        "text": f"📊 Shadow Portfolio: {len(updated)} trade(s) evaluated today."
                    })
                )
        except Exception as exc:
            logger.error(f"Shadow portfolio evaluator error: {exc}")


# ── REST Endpoints ─────────────────────────────────────────────────────────────


@app.get("/", include_in_schema=False)
async def root(username: str = Depends(verify_credentials)):
    return RedirectResponse(url="/chat")

@app.get("/chat", response_class=HTMLResponse)
async def chat_ui(request: Request, username: str = Depends(verify_credentials)):
    """Serve the redesigned JARVIS HUD HTML with ETag + Cache-Control headers (#10).

    ETag is derived from the file's mtime + size so the browser receives a
    304 Not Modified on repeated loads when the file has not changed, avoiding
    a 168 KB re-download on every page visit.
    """
    _hud_path = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "jarvis_hud.html")
    )
    if not os.path.isfile(_hud_path):
        return HTMLResponse(
            "<h2>jarvis_hud.html not found.</h2><p>Please make sure it exists in the project root.</p>",
            status_code=404,
        )

    stat = os.stat(_hud_path)
    # ETag = sha256(mtime_ns + size) — cheap, stable, reflects any file change
    raw_etag = f"{stat.st_mtime_ns}-{stat.st_size}"
    etag = '"' + hashlib.sha256(raw_etag.encode()).hexdigest()[:32] + '"'

    # Honour If-None-Match — return 304 if the client already has this version
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers={"ETag": etag})

    with open(_hud_path, encoding="utf-8") as f:
        html = f.read()

    return HTMLResponse(
        html,
        headers={
            # no-cache: always revalidate, but use 304 when ETag matches
            "Cache-Control": "no-cache, must-revalidate",
            "ETag": etag,
        },
    )


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


@app.get("/health", tags=["Health"])
async def health_check():
    """Health check — returns server status, model info, and degradation mode."""
    from .infra.degradation_manager import degradation_manager
    from .safety.kill_switch import kill_switch
    return {
        "status":           "online",
        "version":          "2.0.0",
        "model":            settings.local_model,
        "cloud_model":      settings.cloud_model,
        "connections":      manager.connection_count(),
        "kill_switch":      kill_switch.status(),
        "degradation_mode": degradation_manager.mode.value,
    }


@app.get("/stats")
async def stats():
    """Live dashboard metrics — polled by the dashboard UI."""
    data = router.get_stats()
    data["connections"] = manager.connection_count()
    return data


# ── Kill Switch Endpoints ──────────────────────────────────────────────────────

@app.post("/kill-switch/pause", tags=["Safety"])
async def kill_switch_pause(reason: str = "Manual REST command"):
    """Pause all JARVIS background agents immediately."""
    from .safety.kill_switch import kill_switch
    kill_switch.pause(reason=reason)
    return {"status": "paused", "reason": reason}


@app.post("/kill-switch/resume", tags=["Safety"])
async def kill_switch_resume():
    """Resume all JARVIS background agents."""
    from .safety.kill_switch import kill_switch
    kill_switch.resume()
    return {"status": "resumed"}


@app.get("/kill-switch/status", tags=["Safety"])
async def kill_switch_status():
    """Get current kill switch state."""
    from .safety.kill_switch import kill_switch
    return kill_switch.status()


# ── System Status Endpoint ─────────────────────────────────────────────────────

@app.get("/system-status", tags=["Reliability"])
async def system_status():
    """Full system status: degradation mode, latency, kill switch, shadow portfolio."""
    from .infra.degradation_manager import degradation_manager
    from .infra.latency_tracker import latency_tracker
    from .safety.kill_switch import kill_switch
    return {
        "degradation": degradation_manager.status(),
        "kill_switch":  kill_switch.status(),
        "latency_24h":  latency_tracker.get_summary(hours=24),
        "connections":  manager.connection_count(),
    }


# ── Audit Log Endpoint ─────────────────────────────────────────────────────────

@app.get("/audit-log", tags=["Safety"])
async def get_audit_log(limit: int = 50, username: str = Depends(verify_credentials)):
    """Return recent audit log entries (auth required)."""
    from .safety.audit_log import audit_log
    return {"entries": audit_log.get_recent(limit=limit)}


# ── Latency Dashboard ──────────────────────────────────────────────────────────

@app.get("/api/latency", tags=["Reliability"])
async def get_latency(hours: int = 24):
    """Return per-agent latency summary."""
    from .infra.latency_tracker import latency_tracker
    return latency_tracker.get_summary(hours=hours)


# ── Shadow Portfolio Endpoints ─────────────────────────────────────────────────

@app.get("/api/shadow-portfolio", tags=["Trading"])
async def get_shadow_portfolio(username: str = Depends(verify_credentials)):
    """Return shadow portfolio trades and win-rate stats."""
    trades = router.shadow_portfolio.get_all_trades(50)
    stats = router.shadow_portfolio.calculate_win_rate()
    return {"trades": trades, "stats": stats, "summary": router.shadow_portfolio.get_portfolio_summary()}


@app.post("/api/shadow-portfolio/add", tags=["Trading"])
async def add_shadow_trade(
    ticker: str,
    action: str,
    price: float,
    qty: int = 1,
    signal_summary: str = "",
    username: str = Depends(verify_credentials),
):
    """Manually add a trade recommendation to the shadow portfolio."""
    result = router.shadow_portfolio.manual_add(ticker, action, price, qty, signal_summary)
    return {"result": result}


# ── Trading Signal Endpoints ──────────────────────────────────────────────────

@app.get("/api/trading/signals", tags=["Trading"])
async def get_trading_signals(limit: int = 20):
    """Return recent trading signals from SQLite store."""
    from .agents.signal_store import signal_store
    return {"signals": signal_store.get_recent_signals(limit=limit)}


@app.post("/api/trading/signals/scan-now", tags=["Trading"])
async def scan_trading_signals_now(username: str = Depends(verify_credentials)):
    """Trigger an instant manual scan pass over the 7-stock watchlist."""
    if not getattr(settings, "trading_signals_enabled", True):
        return {
            "status": "disabled",
            "message": "Trading signal scanner is currently disabled.",
            "result": {"scanned": 0, "status": "disabled"}
        }
    from .agents.trading_signal_scanner import scan_watchlist_once
    result = await scan_watchlist_once(manager)
    return {"status": "ok", "result": result}



@app.post("/api/trading/signals/toggle", tags=["Trading"])
async def toggle_trading_signals(enabled: bool, username: str = Depends(verify_credentials)):
    """Kill-switch toggle for signal scanner without restarting server."""
    settings.trading_signals_enabled = enabled
    return {"trading_signals_enabled": settings.trading_signals_enabled}


@app.get("/api/trading/signals/audit", tags=["Trading"])
async def get_trading_signal_audit(days: int = 30):
    """Signal quality self-audit report comparing real-time vs EOD digest win-rates."""
    from .agents.trading_signal_scanner import get_signal_quality_audit
    return get_signal_quality_audit(days=days)



# ── Budget Endpoints ───────────────────────────────────────────────────────────

@app.post("/api/budget/add", tags=["Budget"])
async def add_budget_transaction(
    amount: float,
    tx_type: str,
    category: str = "Miscellaneous",
    description: str = "",
    username: str = Depends(verify_credentials),
):
    """Manually add a budget transaction."""
    row_id = router.budget_agent.add_transaction(amount, tx_type, category, description)
    return {"id": row_id, "status": "ok" if row_id > 0 else "error"}


@app.get("/api/budget/summary", tags=["Budget"])
async def get_budget_summary(username: str = Depends(verify_credentials)):
    """Return this month's spending summary and anomalies."""
    summary = router.budget_agent.get_monthly_summary()
    anomalies = router.budget_agent.detect_anomalies()
    return {"summary": summary, "anomalies": anomalies}


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
                    stream_error: Exception | None = None
                    try:
                        async for token in router.route_stream(text, file_content, file_name, voice_mode, agent_mode):
                            full_reply += token
                            await websocket.send_text(
                                json.dumps({"type": "token", "text": token})
                            )
                    except Exception as exc:
                        stream_error = exc
                        logger.error(
                            "WebSocket stream error after %d chars: %s",
                            len(full_reply), exc
                        )
                        # Inject a visible notice — don't silently send a
                        # truncated reply as if it were complete
                        err_notice = (
                            f"\n\n⚠️ *Connection was interrupted mid-stream "
                            f"({type(exc).__name__}). The reply above may be incomplete. "
                            f"Retrying automatically via local model...*"
                        )
                        await websocket.send_text(
                            json.dumps({"type": "token", "text": err_notice})
                        )
                        full_reply += err_notice

                    # Final "done" frame with the complete assembled text
                    await websocket.send_text(
                        json.dumps({"type": "done", "text": full_reply})
                    )
                    if stream_error:
                        logger.warning("→ Done frame sent with stream error notice (%d chars)", len(full_reply))
                    else:
                        logger.info(f"→ Reply sent ({len(full_reply)} chars)")

            except json.JSONDecodeError:
                await websocket.send_text(
                    json.dumps({"type": "error", "text": "Invalid JSON"})
                )

    except WebSocketDisconnect:
        manager.disconnect(websocket)

# ── Dev entry point ────────────────────────────────────────────────────────────
# reload=True is single-worker only (uvicorn limitation) — fine for local dev.
# Production multi-worker launch is via Procfile: --workers ${WORKER_COUNT:-2}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("jarvis.main:app", host="127.0.0.1", port=8000, reload=True)
