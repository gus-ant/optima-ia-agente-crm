"""
api/routers/webhook.py
----------------------
Router para receber webhooks do WhatsApp (Meta Cloud API e Evolution API).

Meta Cloud API:
  GET  /webhook/meta  — verificação de token (challenge)
  POST /webhook/meta  — recebimento de mensagens

Evolution API (self-hosted):
  POST /webhook/evolution  — evento de mensagem recebida
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request, Response
from langchain_core.messages import HumanMessage
from pydantic import BaseModel

from agent.graph import get_graph
from memory.store import get_session_state, save_session_state

logger = logging.getLogger(__name__)
router = APIRouter()

META_VERIFY_TOKEN = os.getenv("META_WEBHOOK_VERIFY_TOKEN", "optima_ia_verify")
META_APP_SECRET = os.getenv("META_APP_SECRET", "")


# ---------------------------------------------------------------------------
# Meta Cloud API — GET (verificação de webhook)
# ---------------------------------------------------------------------------

@router.get("/meta")
async def meta_verify(
    hub_mode: str = Query(alias="hub.mode", default=""),
    hub_verify_token: str = Query(alias="hub.verify_token", default=""),
    hub_challenge: str = Query(alias="hub.challenge", default=""),
):
    """Endpoint de verificação de webhook exigido pela Meta."""
    if hub_mode == "subscribe" and hub_verify_token == META_VERIFY_TOKEN:
        logger.info("Meta webhook verified ✓")
        return Response(content=hub_challenge, media_type="text/plain")
    raise HTTPException(status_code=403, detail="Webhook verification failed")


# ---------------------------------------------------------------------------
# Meta Cloud API — POST (mensagens recebidas)
# ---------------------------------------------------------------------------

@router.post("/meta")
async def meta_receive(request: Request, background_tasks: BackgroundTasks):
    """Recebe eventos de mensagem da Meta Cloud API."""
    body = await request.body()

    # Valida assinatura HMAC-SHA256
    if META_APP_SECRET:
        sig_header = request.headers.get("X-Hub-Signature-256", "")
        _verify_meta_signature(body, sig_header)

    payload = json.loads(body)
    messages = _extract_meta_messages(payload)

    for msg in messages:
        background_tasks.add_task(process_incoming_message, msg)

    return {"status": "ok", "processed": len(messages)}


# ---------------------------------------------------------------------------
# Evolution API — POST
# ---------------------------------------------------------------------------

@router.post("/evolution")
async def evolution_receive(request: Request, background_tasks: BackgroundTasks):
    """Recebe eventos de mensagem da Evolution API (self-hosted)."""
    payload = await request.json()

    msg = _extract_evolution_message(payload)
    if msg:
        background_tasks.add_task(process_incoming_message, msg)

    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Core: processar mensagem recebida
# ---------------------------------------------------------------------------

async def process_incoming_message(msg: dict):
    """
    Encaminha a mensagem ao grafo LangGraph e persiste o estado atualizado.

    Args:
        msg: dict com keys: from_number, text, media_url, timestamp
    """
    phone = msg["from_number"]
    text = msg.get("text", "")
    timestamp = msg.get("timestamp", datetime.now(timezone.utc).isoformat())

    logger.info("Processing message from %s: %s chars", phone, len(text))

    # Recupera estado existente da sessão (ou inicializa novo)
    state = await get_session_state(phone)

    # Adiciona mensagem do cliente ao histórico
    new_message = HumanMessage(content=text, additional_kwargs={"timestamp": timestamp})

    graph = get_graph()
    config = {"configurable": {"thread_id": phone}}

    try:
        result = await graph.ainvoke(
            {
                **state,
                "messages": [new_message],
                "session_id": phone,
            },
            config=config,
        )
        await save_session_state(phone, result)
        logger.info("Message processed for %s — stage: %s", phone, result.get("pipeline_stage"))

    except Exception as exc:
        logger.error("Error processing message from %s: %s", phone, exc, exc_info=True)


# ---------------------------------------------------------------------------
# Helpers privados
# ---------------------------------------------------------------------------

def _verify_meta_signature(body: bytes, sig_header: str):
    """Valida assinatura HMAC-SHA256 enviada pela Meta."""
    expected = "sha256=" + hmac.new(
        META_APP_SECRET.encode(), body, hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(expected, sig_header):
        raise HTTPException(status_code=401, detail="Invalid Meta signature")


def _extract_meta_messages(payload: dict) -> list[dict]:
    """Extrai lista de mensagens do payload Meta Cloud API."""
    messages = []
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            for msg in value.get("messages", []):
                if msg.get("type") == "text":
                    messages.append(
                        {
                            "from_number": msg["from"],
                            "text": msg["text"]["body"],
                            "timestamp": datetime.fromtimestamp(
                                int(msg["timestamp"]), tz=timezone.utc
                            ).isoformat(),
                        }
                    )
                elif msg.get("type") in ("image", "document", "audio"):
                    messages.append(
                        {
                            "from_number": msg["from"],
                            "text": f"[mídia recebida: {msg['type']}]",
                            "media_url": msg.get(msg["type"], {}).get("url"),
                            "timestamp": datetime.fromtimestamp(
                                int(msg["timestamp"]), tz=timezone.utc
                            ).isoformat(),
                        }
                    )
    return messages


def _extract_evolution_message(payload: dict) -> dict | None:
    """Extrai mensagem do payload Evolution API."""
    if payload.get("event") != "messages.upsert":
        return None

    data = payload.get("data", {})
    key = data.get("key", {})

    if key.get("fromMe"):
        return None  # ignora mensagens enviadas pelo próprio bot

    return {
        "from_number": key.get("remoteJid", "").replace("@s.whatsapp.net", ""),
        "text": data.get("message", {}).get("conversation", ""),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
