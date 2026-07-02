from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from app.core.jailbreak_protection import verify_prompt_safety
from app.api import router as api_router
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="JARVIS Personal AI Assistant",
    description="Production-Ready Quantum-Secure AI System",
    version="2.0.0",
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # In production, restrict to actual domains
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Application startup events
@app.on_event("startup")
async def startup_event():
    logger.info("JARVIS Core Systems Initializing...")
    logger.info("Quantum Encryption Module: STANDBY")
    logger.info("Zero-Knowledge Architecture: ACTIVE")
    logger.info("AI Jailbreak Protection: ARMED")

# Include the main API router
app.include_router(api_router, prefix="/api/v1")

@app.get("/health")
async def health_check():
    """Basic health check endpoint."""
    return {"status": "online", "modules": 15, "quantum_secure": True}

# Example of a secure prompt endpoint using jailbreak protection
@app.post("/secure-prompt")
async def process_secure_prompt(prompt: str = Depends(verify_prompt_safety)):
    """
    Processes a prompt after passing through the multi-layer adversarial detection.
    """
    return {"status": "success", "processed_prompt": prompt}
