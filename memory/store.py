"""
memory/store.py
---------------
Persistência de estado das sessões de conversa.
Usa Redis para estado rápido (sessões ativas) e PostgreSQL para histórico longo prazo.

Em desenvolvimento, usa um dict in-memory como fallback se Redis não estiver disponível.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Redis client (singleton)
# ---------------------------------------------------------------------------

_redis_client = None


async def get_redis():
    """Retorna cliente Redis assíncrono (aioredis/redis-py async)."""
    global _redis_client
    if _redis_client is None:
        import redis.asyncio as aioredis

        url = os.getenv("REDIS_URL", "redis://localhost:6379")
        _redis_client = aioredis.from_url(url, decode_responses=True)
    return _redis_client


# Fallback in-memory para desenvolvimento sem Redis
_memory_store: dict[str, dict] = {}


async def init_store():
    """Inicializa conexão com Redis na startup."""
    redis_url = os.getenv("REDIS_URL")
    if not redis_url:
        logger.warning("REDIS_URL not set — using in-memory store (dev only)")
        return

    try:
        r = await get_redis()
        await r.ping()
        logger.info("Redis connected: %s", redis_url)
    except Exception as exc:
        logger.error("Redis connection failed: %s — falling back to memory", exc)


# ---------------------------------------------------------------------------
# Session state CRUD
# ---------------------------------------------------------------------------

SESSION_TTL_SECONDS = 60 * 60 * 24 * 7  # 7 dias


async def get_session_state(phone: str) -> dict:
    """
    Recupera o estado completo da sessão do lead pelo número de telefone.

    Args:
        phone: Número normalizado (ex: '5511999998888').

    Returns:
        dict com AgentState ou dict vazio para novos leads.
    """
    key = f"session:{phone}"

    try:
        r = await get_redis()
        data = await r.get(key)
        if data:
            return json.loads(data)
    except Exception:
        pass  # fallback para memória

    return _memory_store.get(phone, {})


async def save_session_state(phone: str, state: dict):
    """
    Persiste o estado atualizado da sessão.

    Args:
        phone: Número normalizado.
        state: Estado completo do AgentState após processamento.
    """
    key = f"session:{phone}"

    # Serializa (exclui mensagens completas para economizar espaço — mantém só últimas 20)
    serializable = _prepare_for_storage(state)

    try:
        r = await get_redis()
        await r.setex(key, SESSION_TTL_SECONDS, json.dumps(serializable))
    except Exception:
        pass  # fallback para memória

    _memory_store[phone] = serializable


async def delete_session(phone: str):
    """Remove a sessão (ex: após transbordo completo ou opt-out LGPD)."""
    key = f"session:{phone}"
    try:
        r = await get_redis()
        await r.delete(key)
    except Exception:
        pass
    _memory_store.pop(phone, None)


async def list_active_sessions() -> list[str]:
    """Retorna lista de phones com sessões ativas (usado pelo follow-up N8N trigger)."""
    try:
        r = await get_redis()
        keys = await r.keys("session:*")
        return [k.replace("session:", "") for k in keys]
    except Exception:
        return list(_memory_store.keys())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _prepare_for_storage(state: dict) -> dict:
    """
    Prepara o estado para serialização JSON.
    - Mantém apenas as últimas 20 mensagens para limitar tamanho.
    - Converte objetos LangChain Message para dicts simples.
    """
    stored = dict(state)

    messages = stored.get("messages", [])
    if messages:
        # Converte Message objects → dicts serializáveis
        serialized_msgs = []
        for msg in messages[-20:]:
            if hasattr(msg, "model_dump"):
                serialized_msgs.append(msg.model_dump())
            elif isinstance(msg, dict):
                serialized_msgs.append(msg)
        stored["messages"] = serialized_msgs

    return stored
