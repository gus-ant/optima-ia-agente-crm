"""
whatsapp/uazapi_client.py
-------------------------
Cliente para UazAPI - Solução simplificada, confiável e com melhor suporte para WhatsApp.

Docs: https://docs.uazapi.com
"""

from __future__ import annotations

import json
import logging
import os
from typing import Optional

import httpx

from whatsapp.client import BaseWhatsAppClient

logger = logging.getLogger(__name__)


class UazAPIClient(BaseWhatsAppClient):
    """
    Cliente para UazAPI WhatsApp Cloud.
    
    Vantagens sobre Meta Cloud API:
    - Interface mais simples
    - Melhor documentação
    - Menos requisitos de verificação
    - Suporte mais responsivo
    
    Variáveis de ambiente:
        UAZAPI_API_KEY: Chave de API (obtida em https://app.uazapi.com)
        UAZAPI_INSTANCE_ID: ID da instância (criado no painel)
    """

    def __init__(self):
        self.api_key = os.getenv("UAZAPI_API_KEY", "")
        self.instance_id = os.getenv("UAZAPI_INSTANCE_ID", "")

        if not self.api_key:
            raise ValueError("UAZAPI_API_KEY não configurada")
        if not self.instance_id:
            raise ValueError("UAZAPI_INSTANCE_ID não configurada")

        # Permite configurar uma URL base customizada (ex: a instância dedicada do cliente)
        self.base_url = os.getenv("UAZAPI_BASE_URL", "https://api.uazapi.com/v1")
        self.headers = {
            "token": self.api_key, # Usado pelo uazapiGO/instâncias dedicadas
            "Authorization": f"Bearer {self.api_key}", # Fallback padrão
            "Content-Type": "application/json",
        }

        logger.info(
            "UazAPI client initialized (base_url: %s, instance: %s)",
            self.base_url,
            self.instance_id[:8] + "...",
        )

    def send_message(self, to: str, text: str) -> dict:
        """
        Envia mensagem de texto simples.

        Args:
            to: Número WhatsApp (ex: '5511999998888')
            text: Texto da mensagem

        Returns:
            dict com 'message_id' e 'status'
        """
        return self._send_text_message(to, text)

    def send_template(self, to: str, template_name: str, params: list) -> dict:
        """
        Envia template estruturado.

        Args:
            to: Número WhatsApp
            template_name: Nome do template aprovado na UazAPI
            params: Lista de parâmetros para substituir no template

        Returns:
            dict com 'message_id' e 'status'
        """
        payload = {
            "to": to,
            "templateName": template_name,
            "templateParams": params,
        }

        return self._post("/send/template", payload)

    def send_interactive_buttons(
        self,
        to: str,
        body: str,
        buttons: list[dict],
        footer: Optional[str] = None,
    ) -> dict:
        """
        Envia mensagem com botões interativos.
        Útil para confirmação de agendamentos.

        Args:
            to: Número WhatsApp
            body: Texto principal da mensagem
            buttons: Lista de dicts {'id': '1', 'title': 'Sim'}
            footer: Rodapé opcional

        Returns:
            dict com status
        """
        payload = {
            "to": to,
            "body": body,
            "buttons": buttons,
        }
        if footer:
            payload["footer"] = footer

        return self._post("/send/interactive/buttons", payload)

    def send_location(
        self, to: str, latitude: float, longitude: float, address: Optional[str] = None
    ) -> dict:
        """
        Envia localização/mapa.

        Args:
            to: Número WhatsApp
            latitude: Latitude
            longitude: Longitude
            address: Endereço opcional

        Returns:
            dict com 'message_id'
        """
        payload = {
            "to": to,
            "latitude": latitude,
            "longitude": longitude,
        }
        if address:
            payload["name"] = address

        return self._post("/send/location", payload)

    def send_media(
        self, to: str, media_url: str, media_type: str, caption: Optional[str] = None
    ) -> dict:
        """
        Envia mídia (imagem, vídeo, áudio, documento).

        Args:
            to: Número WhatsApp
            media_url: URL da mídia
            media_type: 'image' | 'video' | 'audio' | 'document'
            caption: Legenda opcional

        Returns:
            dict com 'message_id'
        """
        payload = {
            "to": to,
            "mediaUrl": media_url,
            "mediaType": media_type,
        }
        if caption:
            payload["caption"] = caption

        return self._post("/send/media", payload)

    # -----------------------------------------------------------------------
    # Métodos privados
    # -----------------------------------------------------------------------

    def _send_text_message(self, to: str, text: str) -> dict:
        """Envia mensagem de texto (uso interno)."""
        payload = {
            "to": to,
            "message": text,
        }
        return self._post("/send/text", payload)

    def _post(self, endpoint: str, payload: dict) -> dict:
        """Faz POST request para UazAPI."""
        try:
            url = f"{self.base_url}{endpoint}"
            payload["instanceId"] = self.instance_id

            with httpx.Client(timeout=30) as client:
                response = client.post(
                    url,
                    json=payload,
                    headers=self.headers,
                )

            response.raise_for_status()
            result = response.json()

            message_id = result.get("messageId") or result.get("id")
            logger.debug("UazAPI response: %s", result)

            return {
                "message_id": message_id,
                "status": "sent",
                "provider": "uazapi",
                "response": result,
            }

        except httpx.HTTPStatusError as exc:
            logger.error(
                "UazAPI HTTP error: %d %s",
                exc.response.status_code,
                exc.response.text,
            )
            raise

        except Exception as exc:
            logger.error("UazAPI send error: %s", exc, exc_info=True)
            raise

    # -----------------------------------------------------------------------
    # Métodos auxiliares
    # -----------------------------------------------------------------------

    def check_instance_health(self) -> dict:
        """Verifica saúde da instância."""
        # Se for a URL dedicada (sem /v1), usa o endpoint singular /instance/status
        path = "/instance/status" if "api.uazapi.com" not in self.base_url else "/instances/status"
        try:
            with httpx.Client(timeout=10) as client:
                response = client.get(
                    f"{self.base_url}{path}",
                    headers=self.headers,
                )
            response.raise_for_status()
            return response.json()
        except Exception as exc:
            logger.error("Health check failed: %s", exc)
            raise

    def get_instance_info(self) -> dict:
        """Obtém informações da instância."""
        # Se for a URL dedicada (sem /v1), usa o endpoint singular /instance/{id}
        path = f"/instance/{self.instance_id}" if "api.uazapi.com" not in self.base_url else f"/instances/{self.instance_id}"
        try:
            with httpx.Client(timeout=10) as client:
                response = client.get(
                    f"{self.base_url}{path}",
                    headers=self.headers,
                )
            response.raise_for_status()
            return response.json()
        except Exception as exc:
            logger.error("Failed to get instance info: %s", exc)
            raise
