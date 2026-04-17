"""Trading Journal Web Interface — FastAPI app.

Startup:
    uvicorn web.main:app --host 127.0.0.1 --port 8765 --reload

Or via the run script:
    bash scripts/run_web.sh
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .routes.auth_routes import router as auth_router
from .routes.data_routes import router as data_router
from .routes.ai_routes import router as ai_router
from .routes.admin_routes import router as admin_router

# ── app setup ─────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Trading Journal",
    description="Read-only trading journal and strategy performance dashboard.",
    version="1.0.0",
    docs_url="/docs" if os.getenv("WEB_ENABLE_DOCS", "0") == "1" else None,
    redoc_url=None,
)

# CORS: restrict to the server's own origin in production.
# In dev, allow localhost:3000 (Vite/React dev server).
_allowed_origins = [
    "http://localhost:8765",
    "http://127.0.0.1:8765",
]
if os.getenv("WEB_DEV_MODE", "0") == "1":
    _allowed_origins += ["http://localhost:3000", "http://localhost:5173"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type"],
)

# ── routers ───────────────────────────────────────────────────────────────────

app.include_router(auth_router)
app.include_router(data_router)
app.include_router(ai_router)
app.include_router(admin_router)

# ── static frontend ───────────────────────────────────────────────────────────

_STATIC_DIR = Path(__file__).parent / "static"

if _STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str):
        """Serve React SPA for all non-API routes."""
        index = _STATIC_DIR / "index.html"
        if index.exists():
            return FileResponse(str(index))
        return {"detail": "Frontend not built yet. Run: cd web/frontend && npm run build"}

else:
    @app.get("/", include_in_schema=False)
    async def root():
        return {
            "status": "ok",
            "message": "Trading Journal API. Frontend not yet built.",
            "docs": "Set WEB_ENABLE_DOCS=1 to access /docs",
        }


# ── health check (no auth required) ──────────────────────────────────────────

@app.get("/ping", include_in_schema=False)
async def ping():
    return {"pong": True}
