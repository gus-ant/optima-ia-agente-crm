"""
whatsapp/provider_config.py
---------------------------
Factory pattern para abstração de providers WhatsApp.
Permite alternância entre UazAPI, Meta Cloud API, Evolution API via configuração.

Uso:
    client = get_whatsapp_client()  # Usa WHATSAPP_PROVIDER do .env
    await client.send_message(to="5511999998888", text="Olá!")
"""

from __future__ import annotations

import logging
import os
from typing import Literal

logger = logging.getLogger(__name__)

PROVIDER_TYPE = Literal["uazapi", "meta", "evolution"]


def get_whatsapp_client() -> "BaseWhatsAppClient":
    """
    Retorna instância do client WhatsApp baseado em WHATSAPP_PROVIDER.

    Variáveis de ambiente esperadas:
        WHATSAPP_PROVIDER: 'uazapi' | 'meta' | 'evolution'

    Returns:
        BaseWhatsAppClient: Instância do provider configurado

    Raises:
        ValueError: Se provider não é suportado
    """
    provider = os.getenv("WHATSAPP_PROVIDER", "uazapi").lower()

    logger.info("Loading WhatsApp provider: %s", provider)

    if provider == "uazapi":
        from whatsapp.uazapi_client import UazAPIClient
        return UazAPIClient()

    elif provider == "meta":
        from whatsapp.client import MetaWhatsAppClient
        return MetaWhatsAppClient()

    elif provider == "evolution":
        from whatsapp.client import EvolutionWhatsAppClient
        return EvolutionWhatsAppClient()

    else:
        raise ValueError(
            f"Unsupported WhatsApp provider: {provider}. "
            f"Use 'uazapi', 'meta', or 'evolution'."
        )


def get_provider_type() -> PROVIDER_TYPE:
    """Retorna o tipo de provider configurado."""
    return os.getenv("WHATSAPP_PROVIDER", "uazapi").lower()  # type: ignore


def is_provider(expected: PROVIDER_TYPE) -> bool:
    """Verifica se um provider específico está ativo."""
    return get_provider_type() == expected
