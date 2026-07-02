from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from app.security.jailbreak_shield import JailbreakShieldMiddleware

app = FastAPI(title="Jarvis Quantum Core", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add our custom Jailbreak Shield
app.add_middleware(JailbreakShieldMiddleware)

from app.api.study import router as study_router
from app.api.work import router as work_router
from app.api.comm import router as comm_router
from app.api.predictive import router as predictive_router
from app.integrations.india_stack import router as india_router

app.include_router(study_router)
app.include_router(work_router)
app.include_router(comm_router)
app.include_router(predictive_router)
app.include_router(india_router)

@app.get("/")
async def root():
    return {"status": "Jarvis Online", "security_level": "Quantum-Simulated"}
