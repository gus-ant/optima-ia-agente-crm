"""
api/routers/health.py
---------------------
Endpoints de healthcheck e status do sistema.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

from fastapi import APIRouter

router = APIRouter()

START_TIME = datetime.now(timezone.utc)


@router.get("/")
async def health_check():
    """Healthcheck básico para monitoramento (UptimeRobot, etc.)."""
    uptime = (datetime.now(timezone.utc) - START_TIME).total_seconds()
    return {
        "status": "ok",
        "service": "optima-ia-agente-crm",
        "version": "1.0.0",
        "uptime_seconds": round(uptime),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/detailed")
async def health_detailed():
    """Healthcheck detalhado com verificação de dependências."""
    checks = {}

    # Verifica conexão com Redis
    try:
        from memory.store import get_redis
        r = await get_redis()
        await r.ping()
        checks["redis"] = "ok"
    except Exception as e:
        checks["redis"] = f"error: {e}"

    # Verifica variáveis de ambiente críticas
    required_env = ["OPENAI_API_KEY", "META_WEBHOOK_VERIFY_TOKEN"]
    for var in required_env:
        checks[f"env_{var.lower()}"] = "ok" if os.getenv(var) else "missing"

    overall = "ok" if all(v == "ok" for v in checks.values()) else "degraded"

    return {"status": overall, "checks": checks}
