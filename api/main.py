"""
api/main.py
-----------
FastAPI application — ponto de entrada principal.
Recebe webhooks do WhatsApp (Meta Cloud API ou Evolution API)
e os encaminha ao agente LangGraph.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from api.routers import health, webhook

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Inicializa recursos compartilhados na startup."""
    from agent.graph import get_graph
    from memory.store import init_store

    logger.info("Initializing LangGraph agent...")
    get_graph()  # força compilação antecipada

    logger.info("Initializing memory store...")
    await init_store()

    logger.info("Óptima IA Agent ready ✓")
    yield
    logger.info("Shutting down...")


app = FastAPI(
    title="Óptima IA — Agente Lara API",
    description="Agente de qualificação de leads para Lu Decorações via WhatsApp",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — ajustar origins em produção
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("ALLOWED_ORIGINS", "*").split(","),
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# Routers
app.include_router(health.router, prefix="/health", tags=["health"])
app.include_router(webhook.router, prefix="/webhook", tags=["webhook"])


if __name__ == "__main__":
    uvicorn.run(
        "api.main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8000)),
        reload=os.getenv("ENV", "production") == "development",
        log_level=os.getenv("LOG_LEVEL", "info").lower(),
    )
