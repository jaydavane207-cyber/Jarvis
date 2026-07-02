from fastapi import FastAPI, Depends, HTTPException, Security
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from src.core.config import settings
from src.middleware.jailbreak_protection import jailbreak_protector
from src.api import auth, study, work, communication, agents, cognitive, predictive, india_local, enterprise, cutting_edge, creative

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="JARVIS Core Production API with Quantum & ZKP Security"
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify exact origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add AI Jailbreak Protection Middleware if enabled
if settings.ENABLE_JAILBREAK_PROTECTION:
    # We wrap it in a BaseHTTPMiddleware
    class JailbreakMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            return await jailbreak_protector.middleware(request, call_next)
            
    app.add_middleware(JailbreakMiddleware)

# Include Routers
app.include_router(auth.router, prefix="/api/v1/auth", tags=["Authentication & Security"])
app.include_router(study.router, prefix="/api/v1/study", tags=["Study & Learning"])
app.include_router(work.router, prefix="/api/v1/work", tags=["Work & Productivity"])
app.include_router(communication.router, prefix="/api/v1/communication", tags=["Communication"])
app.include_router(agents.router, prefix="/api/v1/agents", tags=["Autonomous Agents & Swarm"])
app.include_router(cognitive.router, prefix="/api/v1/cognitive", tags=["Cognitive Enhancement"])
app.include_router(predictive.router, prefix="/api/v1/predictive", tags=["Predictive Analytics"])
app.include_router(india_local.router, prefix="/api/v1/india", tags=["India-Specific & Local"])
app.include_router(enterprise.router, prefix="/api/v1/enterprise", tags=["Enterprise Management"])
app.include_router(cutting_edge.router, prefix="/api/v1/cutting-edge", tags=["Edge Tech & Web3"])
app.include_router(creative.router, prefix="/api/v1/creative", tags=["Creative Studio"])

@app.get("/health")
async def health_check():
    """Basic health check endpoint."""
    return {"status": "healthy", "version": settings.VERSION}

@app.get("/security/status")
async def security_status():
    """Returns the status of high-priority security modules."""
    return {
        "quantum_crypto": "active" if settings.ENABLE_QUANTUM_CRYPTO else "disabled",
        "jailbreak_protection": "active" if settings.ENABLE_JAILBREAK_PROTECTION else "disabled",
        "digital_twin": "active" if settings.ENABLE_DIGITAL_TWIN else "disabled",
        "encryption_algorithm": "CRYSTALS-Kyber512 (Simulation/Fallback)",
    }
