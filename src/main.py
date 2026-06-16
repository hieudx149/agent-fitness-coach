import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from src.api.routes_chat import router as chat_router
from src.config import get_settings

settings = get_settings()

logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="AI Workout Coach",
    description="RAG + Coach Agent + Workout Analysis (Everfit take-home)",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/v1/health")
async def health() -> dict:
    return {
        "status": "ok",
        "service": "agent-fitness-coach",
        "version": "0.1.0",
    }


app.include_router(chat_router)


UI_DIR = Path(__file__).parent.parent / "ui"
if UI_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(UI_DIR), html=True), name="ui")
else:
    logger.warning("UI directory not found at %s — static UI disabled", UI_DIR)
