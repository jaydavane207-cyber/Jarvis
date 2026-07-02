from fastapi import APIRouter

# Import the actual routers from all 15 implemented modules
from app.modules.study.routes import router as study_router
from app.modules.productivity.routes import router as prod_router
from app.modules.communication.routes import router as comm_router
from app.modules.agent.routes import router as agent_router
from app.modules.cognitive.routes import router as cognitive_router
from app.modules.analytics.routes import router as analytics_router
from app.modules.india.routes import router as india_router
from app.modules.twin.routes import router as twin_router
from app.modules.neural.routes import router as neural_router
from app.modules.arvr.routes import router as arvr_router
from app.modules.web3.routes import router as web3_router
from app.modules.iot.routes import router as iot_router

router = APIRouter()

# --- Module 1: Study & Learning ---
router.include_router(study_router, prefix="/study", tags=["Study & Learning"])

# --- Module 2: Work & Productivity ---
router.include_router(prod_router, prefix="/productivity", tags=["Work & Productivity"])

# --- Module 3: Communication ---
router.include_router(comm_router, prefix="/communication", tags=["Communication"])

# --- Module 4: Autonomous Agent ---
router.include_router(agent_router, prefix="/agent", tags=["Autonomous Agent"])

# --- Module 5: Cognitive Enhancement ---
router.include_router(cognitive_router, prefix="/cognitive", tags=["Cognitive Enhancement"])

# --- Module 6: Predictive Analytics ---
router.include_router(analytics_router, prefix="/analytics", tags=["Predictive Analytics"])

# --- Module 7, 8, 9: Security Core ---
# Handled via middleware and utility functions (app/core/security.py, zero_knowledge.py, jailbreak_protection.py)

# --- Module 10: Digital Twin Firewall ---
router.include_router(twin_router, prefix="/twin", tags=["Digital Twin"])

# --- Module 11: Neural Interface ---
router.include_router(neural_router, prefix="/neural", tags=["Neural Interface"])

# --- Module 12: AR/VR Native ---
router.include_router(arvr_router, prefix="/arvr", tags=["AR/VR Native"])

# --- Module 13: Blockchain Agent ---
router.include_router(web3_router, prefix="/web3", tags=["Blockchain"])

# --- Module 14: IoT Ecosystem ---
router.include_router(iot_router, prefix="/iot", tags=["IoT Ecosystem"])

# --- Module 15: India Optimization ---
router.include_router(india_router, prefix="/india", tags=["India Optimization"])
