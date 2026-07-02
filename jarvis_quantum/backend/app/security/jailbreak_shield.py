import time
import logging
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

class IntentAnalyzer:
    """Simulates real-time deep intent analysis (e.g., using a local LLM or transformer)."""
    @staticmethod
    def analyze(text: str) -> bool:
        # In a real system, this would call a local, sandboxed ML model
        # to detect adversarial intent, prompt injection, or malicious structure.
        banned_patterns = ["ignore previous instructions", "system prompt", "jailbreak", "bypass security"]
        text_lower = text.lower()
        return any(pattern in text_lower for pattern in banned_patterns)

class JailbreakShieldMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):
        start_time = time.time()

        if request.method == "POST" and request.headers.get("content-type") == "application/json":
            try:
                # Read body and keep it in memory
                body_bytes = await request.body()
                body_str = body_bytes.decode('utf-8')
                
                # Real-Time Intent Analysis (Sub-10ms target)
                is_malicious = IntentAnalyzer.analyze(body_str)
                if is_malicious:
                    logging.warning(f"Quantum Firewall: Jailbreak or Adversarial intent intercepted.")
                    return JSONResponse(
                        status_code=403, 
                        content={"error": "Quantum Firewall: Adversarial intent detected and blocked."}
                    )
                
                # Re-inject body for the downstream route handlers
                async def receive():
                    return {"type": "http.request", "body": body_bytes}
                request._receive = receive
                
            except Exception as e:
                logging.error(f"Error in Intent Analysis Middleware: {e}")

        response = await call_next(request)
        process_time = time.time() - start_time
        response.headers["X-Process-Time"] = str(process_time)
        return response
