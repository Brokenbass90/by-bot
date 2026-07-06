"""Live position panel API — thin FastAPI wrapper over bot.position_view.

Owner gap (2026-07-08): «нет возможности в вебе следить за открытой позицией,
управлять ей и обсуждать её с ИИшкой». WATCH + DISCUSS ship in v1 (this route +
web/static/position.html + existing /api/ai/chat). MANAGE deliberately waits:
live-money buttons need ai_manual_v1-grade token discipline.
"""
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends

from bot.position_view import build_position_view
from ..deps import require_auth

router = APIRouter(prefix="/api/position", tags=["position"])


@router.get("/live")
async def live_position(_: str = Depends(require_auth)) -> Dict[str, Any]:
    return build_position_view()
