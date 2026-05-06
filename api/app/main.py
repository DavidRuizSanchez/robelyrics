"""FastAPI bootstrap."""
from __future__ import annotations

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.config import get_settings
from app.db.session import SessionLocal
from app.routers import admin as admin_router
from app.routers import auth as auth_router
from app.routers import catalog as catalog_router
from app.routers import public as public_router
from app.routers import search as search_router
from app.routers import sources as sources_router

app = FastAPI(title="RobeLyrics API", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3001",
        "http://localhost:3000",
        "http://127.0.0.1:3001",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router.router)
app.include_router(catalog_router.router)
app.include_router(search_router.router)
app.include_router(admin_router.router)
app.include_router(public_router.router)
app.include_router(sources_router.router)


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    settings = get_settings()
    status: dict[str, str] = {"status": "ok"}

    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        status["postgres"] = "ok"
    except Exception as e:  # noqa: BLE001
        status["postgres"] = f"error: {type(e).__name__}"
        status["status"] = "degraded"

    try:
        with httpx.Client(timeout=2.0) as client:
            r = client.get(f"{settings.qdrant_url}/readyz")
            r.raise_for_status()
        status["qdrant"] = "ok"
    except Exception as e:  # noqa: BLE001
        status["qdrant"] = f"error: {type(e).__name__}"
        status["status"] = "degraded"

    return status


@app.get("/", tags=["health"])
def root() -> dict[str, str]:
    return {"service": "RobeLyrics API", "version": "0.2.0"}
