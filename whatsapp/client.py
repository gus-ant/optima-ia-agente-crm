"""
whatsapp/client.py
------------------
Cliente para envio de mensagens via WhatsApp.
Suporta Meta Cloud API (oficial) e Evolution API (self-hosted open-source).

WHATSAPP_PROVIDER=meta       → Meta Cloud API
WHATSAPP_PROVIDER=evolution  → Evolution API
"""

from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

PROVIDER = os.getenv("WHATSAPP_PROVIDER", "meta")


# ---------------------------------------------------------------------------
# Interface
# ---------------------------------------------------------------------------

class BaseWhatsAppClient(ABC):
    @abstractmethod
    def send_message(self, to: str, text: str) -> dict:
        ...

    @abstractmethod
    def send_template(self, to: str, template_name: str, params: list) -> dict:
        ...


# ---------------------------------------------------------------------------
# Meta Cloud API Client
# ---------------------------------------------------------------------------

class MetaWhatsAppClient(BaseWhatsAppClient):
    """
    Cliente para Meta WhatsApp Cloud API.
    Docs: https://developers.facebook.com/docs/whatsapp/cloud-api
    """

    def __init__(self):
        self.phone_id = os.getenv("META_PHONE_NUMBER_ID", "")
        self.token = os.getenv("META_ACCESS_TOKEN", "")
        self.base_url = f"https://graph.facebook.com/v20.0/{self.phone_id}"
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    def send_message(self, to: str, text: str) -> dict:
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "text",
            "text": {"body": text, "preview_url": False},
        }
        return self._post("/messages", payload)

    def send_template(self, to: str, template_name: str, params: list) -> dict:
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": "pt_BR"},
                "components": [
                    {
                        "type": "body",
                        "parameters": [{"type": "text", "text": p} for p in params],
                    }
                ],
            },
        }
        return self._post("/messages", payload)

    def _post(self, endpoint: str, payload: dict) -> dict:
        try:
            response = httpx.post(
                f"{self.base_url}{endpoint}",
                json=payload,
                headers=self.headers,
                timeout=10,
            )
            response.raise_for_status()
            result = response.json()
            logger.debug("Meta API response: %s", result)
            return {"message_id": result.get("messages", [{}])[0].get("id"), "status": "sent"}
        except Exception as exc:
            logger.error("Meta WhatsApp send error: %s", exc)
            raise


# ---------------------------------------------------------------------------
# Evolution API Client (self-hosted)
# ---------------------------------------------------------------------------

class EvolutionWhatsAppClient(BaseWhatsAppClient):
    """
    Cliente para Evolution API (self-hosted, baseada em Baileys).
    Docs: https://doc.evolution-api.com/
    """

    def __init__(self):
        self.base_url = os.getenv("EVOLUTION_API_URL", "http://localhost:8080")
        self.api_key = os.getenv("EVOLUTION_API_KEY", "")
        self.instance = os.getenv("EVOLUTION_INSTANCE", "lara")
        self.headers = {
            "apikey": self.api_key,
            "Content-Type": "application/json",
        }

    def send_message(self, to: str, text: str) -> dict:
        # Normaliza número para formato JID
        jid = to if "@" in to else f"{to}@s.whatsapp.net"
        payload = {"number": jid, "text": text}
        return self._post(f"/message/sendText/{self.instance}", payload)

    def send_template(self, to: str, template_name: str, params: list) -> dict:
        # Evolution não suporta templates oficialmente — envia como texto
        text = " ".join(str(p) for p in params)
        return self.send_message(to=to, text=text)

    def _post(self, endpoint: str, payload: dict) -> dict:
        try:
            response = httpx.post(
                f"{self.base_url}{endpoint}",
                json=payload,
                headers=self.headers,
                timeout=10,
            )
            response.raise_for_status()
            result = response.json()
            return {"message_id": result.get("key", {}).get("id"), "status": "sent"}
        except Exception as exc:
            logger.error("Evolution API send error: %s", exc)
            raise


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def WhatsAppClient() -> BaseWhatsAppClient:
    """Factory que retorna o cliente WhatsApp configurado via env."""
    if PROVIDER == "evolution":
        return EvolutionWhatsAppClient()
    return MetaWhatsAppClient()  # default
