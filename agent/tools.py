"""
agent/tools.py
--------------
LangChain Tools disponíveis para o agente Lara via tool calling.
Cada tool agora interage de forma assíncrona com o CRM Próprio Local.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from langchain_core.tools import tool

from crm.client import CRMClient

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# CRM Tools
# ---------------------------------------------------------------------------

@tool
async def create_crm_contact(
    whatsapp: str,
    nome: Optional[str] = None,
    canal_origem: Optional[str] = "whatsapp",
) -> dict:
    """
    Cria um novo contato/lead no CRM local com os dados iniciais.
    Deve ser chamado na PRIMEIRA mensagem recebida de um novo número.

    Args:
        whatsapp: Número WhatsApp normalizado (ex: '5511999998888').
        nome: Nome do lead se já disponível.
        canal_origem: Canal de aquisição do lead.

    Returns:
        dict com 'contact_id', 'deal_id' e 'crm_url' do contato criado.
    """
    client = CRMClient()
    result = await client.get_or_create_contato(
        whatsapp_id=whatsapp,
        nome=nome,
    )
    logger.info("Local CRM contact created/retrieved: %s (Deal: %s)", 
                result.get("contact_id"), result.get("deal_id"))
    return result


@tool
async def update_crm_lead(contact_id: str, fields: dict) -> dict:
    """
    Atualiza campos do lead/negócio no CRM local com os dados extraídos pelo agente.

    Args:
        contact_id: ID do contato no CRM (ou ID fake de fallback).
        fields: Dicionário com campos a atualizar (lead, evento, comercial).

    Returns:
        dict com status da operação.
    """
    client = CRMClient()
    return await client.update_contact_data(contact_id=contact_id, fields=fields)



@tool
async def advance_pipeline_stage(contact_id: str, stage: str) -> dict:
    """
    Avança o estágio do pipeline do lead no CRM local.

    Args:
        contact_id: ID do contato no CRM.
        stage: Novo estágio (novo_lead|em_qualificacao|dados_coletados|
               aguardando_fotos|pronto_orcamento).

    Returns:
        dict com status.
    """
    if contact_id.startswith("fallback_"):
        return {"status": "fallback_success"}

    client = CRMClient()
    try:
        from sqlalchemy import select
        from crm.database import get_db_session
        from crm.models import Negocio

        async with get_db_session() as session:
            stmt = select(Negocio).where(Negocio.contato_id == int(contact_id))
            result = await session.execute(stmt)
            negocio = result.scalar_one_or_none()
            if not negocio:
                return {"status": "not_found"}
            negocio_id = negocio.id

        return await client.update_etapa_funil(negocio_id=negocio_id, nova_etapa=stage)
    except Exception as exc:
        logger.error("Erro ao avançar etapa do lead no banco: %s", exc, exc_info=True)
        return {"status": "error", "message": str(exc)}


@tool
async def notify_human_agent(contact_id: str, summary: str, whatsapp: str) -> dict:
    """
    Envia notificação ao atendente humano quando o dossiê está completo.
    Dispara via WhatsApp configurado no .env.

    Args:
        contact_id: ID do contato no CRM.
        summary: Resumo textual dos dados coletados para o atendente.
        whatsapp: Número do cliente para o atendente iniciar o contato.

    Returns:
        dict com status do envio.
    """
    from whatsapp.client import WhatsAppClient

    client = WhatsAppClient()
    agent_number = os.getenv("HUMAN_AGENT_WHATSAPP")
    
    crm_url = f"http://localhost:8000/crm/contacts/{contact_id}"
    if contact_id.startswith("fallback_"):
        crm_url = "#fallback-database-offline"

    message = (
        f"🔔 *Novo lead qualificado!*\n\n"
        f"📋 {summary}\n\n"
        f"📱 WhatsApp do cliente: {whatsapp}\n"
        f"🔗 CRM Local: {crm_url}"
    )
    result = client.send_message(to=agent_number, text=message)
    logger.info("Human agent notified for contact %s", contact_id)
    return result


@tool
async def log_conversation_message(
    contact_id: str,
    direction: str,
    content: str,
    timestamp: str,
) -> dict:
    """
    Registra uma mensagem no histórico do CRM local para auditoria (RF-08).

    Args:
        contact_id: ID do contato no CRM.
        direction: 'inbound' (cliente → agente) ou 'outbound' (agente → cliente).
        content: Texto da mensagem.
        timestamp: ISO-8601 timestamp da mensagem.

    Returns:
        dict com status do log.
    """
    if contact_id.startswith("fallback_"):
        return {"status": "fallback_success"}

    client = CRMClient()
    return await client.log_activity(
        contact_id=int(contact_id),
        direction=direction,
        content=content,
        timestamp=timestamp,
    )


# ---------------------------------------------------------------------------
# WhatsApp Tools
# ---------------------------------------------------------------------------

@tool
def send_whatsapp_message(to: str, text: str) -> dict:
    """
    Envia uma mensagem de texto ao cliente via WhatsApp Cloud API ou Evolution API.

    Args:
        to: Número de destino normalizado.
        text: Texto da mensagem.

    Returns:
        dict com 'message_id' e status.
    """
    from whatsapp.client import WhatsAppClient
    client = WhatsAppClient()
    result = client.send_message(to=to, text=text)
    logger.info("WhatsApp message sent to %s: %s chars", to, len(text))
    return result


# Registro de todas as tools disponíveis para bind ao LLM
# Note: LangChain detecta se a tool é síncrona ou assíncrona automaticamente.
ALL_TOOLS = [
    create_crm_contact,
    update_crm_lead,
    advance_pipeline_stage,
    notify_human_agent,
    log_conversation_message,
    send_whatsapp_message,
]
