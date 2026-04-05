"""
IntentFlow — FastAPI Application Entry Point.
Mounts all routers, initializes DB, seeds KB, starts SLA monitor.
"""

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from config import get_settings

settings = get_settings()

# ── Logging ───────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s | %(name)-25s | %(levelname)-7s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("intentflow")


# ── Application Lifecycle ─────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    # ── STARTUP ──
    logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION}")

    # 1. Initialize database
    from database import init_db
    init_db()
    logger.info("Database initialized")

    # 2. Seed knowledge base
    try:
        from rag.seed_kb import seed_knowledge_base
        count = seed_knowledge_base()
        logger.info(f"Knowledge base ready: {count} articles")
    except Exception as e:
        logger.warning(f"KB seed skipped (non-fatal): {e}")

    # 3. Start SLA monitor
    from sla.monitor import run_sla_monitor
    sla_task = asyncio.create_task(run_sla_monitor(settings.SLA_CHECK_INTERVAL))
    logger.info("SLA monitor started")

    logger.info(f"{settings.APP_NAME} is ready — http://{settings.HOST}:{settings.PORT}")

    yield  # App is running

    # ── SHUTDOWN ──
    from sla.monitor import stop_sla_monitor
    stop_sla_monitor()
    sla_task.cancel()
    logger.info(f"{settings.APP_NAME} shutting down")


# ── Create App ────────────────────────────────────────────────────────────────

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Autonomous Enterprise Complaint Resolution Engine",
    lifespan=lifespan,
)

# CORS
origins = settings.CORS_ORIGINS.split(",") if settings.CORS_ORIGINS != "*" else ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Mount Routers ─────────────────────────────────────────────────────────────

from routers.auth_router import router as auth_router
from routers.tickets import router as tickets_router
from routers.voice import router as voice_router
from routers.admin import router as admin_router
from routers.metrics import router as metrics_router

app.include_router(auth_router)
app.include_router(tickets_router)
app.include_router(voice_router)
app.include_router(admin_router)
app.include_router(metrics_router)


# ── Health Check ──────────────────────────────────────────────────────────────

@app.get("/health", tags=["Health"])
def health_check():
    return {
        "status": "healthy",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
    }


@app.get("/api/config", tags=["Config"])
def public_config():
    """Non-sensitive config for the frontend."""
    return {
        "app_name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "voice_enabled": True,
        "auto_threshold": settings.AUTO_THRESHOLD,
        "assisted_threshold": settings.ASSISTED_THRESHOLD,
    }


# ── Serve Frontend ────────────────────────────────────────────────────────────

FRONTEND_DIR = Path(__file__).parent / "frontend" / "dist"

if FRONTEND_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIR / "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        """Serve React SPA — all non-API routes fall through to index.html."""
        file_path = FRONTEND_DIR / full_path
        if file_path.is_file():
            return FileResponse(str(file_path))
        return FileResponse(str(FRONTEND_DIR / "index.html"))


# ── Run ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
    )
