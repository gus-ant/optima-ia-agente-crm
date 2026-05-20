"""
crm/client.py
-------------
Cliente abstrato para integração com CRM.
Suporta Bitrix24 (recomendado) e HubSpot via configuração de variável de ambiente.

CRM_PROVIDER=bitrix24  → usa Bitrix24Client
CRM_PROVIDER=hubspot   → usa HubSpotClient
"""

from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

CRM_PROVIDER = os.getenv("CRM_PROVIDER", "bitrix24")


# ---------------------------------------------------------------------------
# Interface abstrata
# ---------------------------------------------------------------------------

class BaseCRMClient(ABC):
    @abstractmethod
    def create_contact(self, whatsapp: str, nome: Optional[str], canal_origem: Optional[str]) -> dict:
        ...

    @abstractmethod
    def update_contact(self, contact_id: str, fields: dict) -> dict:
        ...

    @abstractmethod
    def set_pipeline_stage(self, contact_id: str, stage: str) -> dict:
        ...

    @abstractmethod
    def log_activity(self, contact_id: str, direction: str, content: str, timestamp: str) -> dict:
        ...


# ---------------------------------------------------------------------------
# Bitrix24 Client
# ---------------------------------------------------------------------------

class Bitrix24Client(BaseCRMClient):
    """
    Cliente para Bitrix24 REST API.
    Docs: https://apidocs.bitrix24.com/
    """

    STAGE_MAP = {
        "novo_lead": "NEW",
        "em_qualificacao": "IN_PROCESS",
        "dados_coletados": "PROCESSED",
        "aguardando_fotos": "PROCESSED",
        "pronto_orcamento": "WON",
    }

    def __init__(self):
        self.base_url = os.getenv("BITRIX24_WEBHOOK_URL", "")
        if not self.base_url:
            raise ValueError("BITRIX24_WEBHOOK_URL not configured")

    def _call(self, method: str, params: dict) -> dict:
        url = f"{self.base_url}/{method}"
        try:
            response = httpx.post(url, json=params, timeout=10)
            response.raise_for_status()
            return response.json().get("result", {})
        except Exception as exc:
            logger.error("Bitrix24 API error [%s]: %s", method, exc)
            raise

    def create_contact(self, whatsapp: str, nome: Optional[str] = None, canal_origem: Optional[str] = None) -> dict:
        fields = {
            "PHONE": [{"VALUE": whatsapp, "VALUE_TYPE": "WORK"}],
            "SOURCE_ID": self._map_source(canal_origem),
        }
        if nome:
            parts = nome.split(" ", 1)
            fields["NAME"] = parts[0]
            if len(parts) > 1:
                fields["LAST_NAME"] = parts[1]

        result = self._call("crm.contact.add", {"fields": fields})
        contact_id = str(result)

        # Cria lead/deal vinculado
        deal_result = self._call("crm.deal.add", {
            "fields": {
                "TITLE": f"Lead WhatsApp — {whatsapp}",
                "STAGE_ID": "NEW",
                "CONTACT_ID": contact_id,
                "SOURCE_ID": self._map_source(canal_origem),
            }
        })

        return {
            "contact_id": contact_id,
            "deal_id": str(deal_result),
            "crm_url": f"{os.getenv('BITRIX24_BASE_URL', '')}/crm/contact/details/{contact_id}/",
        }

    def update_contact(self, contact_id: str, fields: dict) -> dict:
        lead_data = fields.get("lead", {})
        evento_data = fields.get("evento", {})

        crm_fields = {}
        if lead_data.get("nome"):
            parts = lead_data["nome"].split(" ", 1)
            crm_fields["NAME"] = parts[0]
            if len(parts) > 1:
                crm_fields["LAST_NAME"] = parts[1]

        if crm_fields:
            self._call("crm.contact.update", {"id": contact_id, "fields": crm_fields})

        # Atualiza campos custom do deal (UF_CRM_*)
        # Adicionar mapeamento de campos UF conforme configuração do Bitrix24
        return {"status": "updated"}

    def set_pipeline_stage(self, contact_id: str, stage: str) -> dict:
        bitrix_stage = self.STAGE_MAP.get(stage, "IN_PROCESS")
        # Aqui precisaria do deal_id — simplificado para demonstração
        return {"status": "stage_set", "stage": bitrix_stage}

    def log_activity(self, contact_id: str, direction: str, content: str, timestamp: str) -> dict:
        self._call("crm.activity.add", {
            "fields": {
                "OWNER_TYPE_ID": 3,  # Contact
                "OWNER_ID": contact_id,
                "TYPE_ID": 4,  # Message
                "SUBJECT": f"WhatsApp [{direction}]",
                "DESCRIPTION": content,
                "START_TIME": timestamp,
                "COMPLETED": "Y",
            }
        })
        return {"status": "logged"}

    def _map_source(self, canal: Optional[str]) -> str:
        mapping = {
            "instagram": "ADVERTISING",
            "google": "ADVERTISING",
            "indicacao": "PARTNER",
            "trafego": "ADVERTISING",
            "evento": "CONFERENCE",
        }
        return mapping.get(canal or "", "OTHER")


# ---------------------------------------------------------------------------
# HubSpot Client (stub — expansível)
# ---------------------------------------------------------------------------

class HubSpotClient(BaseCRMClient):
    """Cliente para HubSpot CRM API v3."""

    def __init__(self):
        self.api_key = os.getenv("HUBSPOT_API_KEY", "")
        self.base_url = "https://api.hubapi.com"
        self.headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    def _call(self, method: str, endpoint: str, data: dict) -> dict:
        url = f"{self.base_url}{endpoint}"
        try:
            response = httpx.request(method, url, json=data, headers=self.headers, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as exc:
            logger.error("HubSpot API error [%s %s]: %s", method, endpoint, exc)
            raise

    def create_contact(self, whatsapp: str, nome: Optional[str] = None, canal_origem: Optional[str] = None) -> dict:
        properties = {"phone": whatsapp}
        if nome:
            parts = nome.split(" ", 1)
            properties["firstname"] = parts[0]
            if len(parts) > 1:
                properties["lastname"] = parts[1]

        result = self._call("POST", "/crm/v3/objects/contacts", {"properties": properties})
        return {"contact_id": result["id"], "crm_url": f"https://app.hubspot.com/contacts/{result['id']}"}

    def update_contact(self, contact_id: str, fields: dict) -> dict:
        properties = {}
        lead = fields.get("lead", {})
        if lead.get("nome"):
            parts = lead["nome"].split(" ", 1)
            properties["firstname"] = parts[0]
            if len(parts) > 1:
                properties["lastname"] = parts[1]

        self._call("PATCH", f"/crm/v3/objects/contacts/{contact_id}", {"properties": properties})
        return {"status": "updated"}

    def set_pipeline_stage(self, contact_id: str, stage: str) -> dict:
        # Cria/atualiza deal vinculado ao contato
        return {"status": "stage_set", "stage": stage}

    def log_activity(self, contact_id: str, direction: str, content: str, timestamp: str) -> dict:
        self._call("POST", "/crm/v3/objects/notes", {
            "properties": {
                "hs_note_body": f"[WhatsApp {direction}] {content}",
                "hs_timestamp": timestamp,
            },
            "associations": [{"to": {"id": contact_id}, "types": [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 202}]}],
        })
        return {"status": "logged"}


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def CRMClient() -> BaseCRMClient:
    """Factory que retorna o cliente CRM configurado via env."""
    if CRM_PROVIDER == "hubspot":
        return HubSpotClient()
    return Bitrix24Client()  # default
