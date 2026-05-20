"""
agent/tools.py
--------------
LangChain Tools disponíveis para o agente Lara via tool calling.
Cada tool representa uma ação concreta sobre o CRM ou canal de mensagens.
"""

from __future__ import annotations

import logging
from typing import Optional

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# CRM Tools
# ---------------------------------------------------------------------------

@tool
def create_crm_contact(
    whatsapp: str,
    nome: Optional[str] = None,
    canal_origem: Optional[str] = "whatsapp",
) -> dict:
    """
    Cria um novo contato/lead no CRM (Bitrix24 ou HubSpot) com os dados iniciais.
    Deve ser chamado na PRIMEIRA mensagem recebida de um novo número.

    Args:
        whatsapp: Número WhatsApp normalizado (ex: '5511999998888').
        nome: Nome do lead se já disponível.
        canal_origem: Canal de aquisição do lead.

    Returns:
        dict com 'contact_id' e 'crm_url' do contato criado.
    """
    # Implementação real importada do módulo crm
    from crm.client import CRMClient
    client = CRMClient()
    result = client.create_contact(
        whatsapp=whatsapp,
        nome=nome,
        canal_origem=canal_origem,
    )
    logger.info("CRM contact created: %s", result.get("contact_id"))
    return result


@tool
def update_crm_lead(contact_id: str, fields: dict) -> dict:
    """
    Atualiza campos do lead/negócio no CRM com os dados extraídos pelo agente.

    Args:
        contact_id: ID do contato no CRM.
        fields: Dicionário com campos a atualizar (lead, evento, comercial).

    Returns:
        dict com status da operação.
    """
    from crm.client import CRMClient
    client = CRMClient()
    result = client.update_contact(contact_id=contact_id, fields=fields)
    logger.info("CRM lead updated: %s → stage %s", contact_id, fields.get("pipeline_stage"))
    return result


@tool
def advance_pipeline_stage(contact_id: str, stage: str) -> dict:
    """
    Avança o estágio do pipeline do lead no CRM.

    Args:
        contact_id: ID do contato no CRM.
        stage: Novo estágio (novo_lead|em_qualificacao|dados_coletados|
               aguardando_fotos|pronto_orcamento).

    Returns:
        dict com status.
    """
    from crm.client import CRMClient
    client = CRMClient()
    return client.set_pipeline_stage(contact_id=contact_id, stage=stage)


@tool
def notify_human_agent(contact_id: str, summary: str, whatsapp: str) -> dict:
    """
    Envia notificação ao atendente humano quando o dossiê está completo.
    Dispara via WhatsApp e/ou e-mail configurado no .env.

    Args:
        contact_id: ID do contato no CRM.
        summary: Resumo textual dos dados coletados para o atendente.
        whatsapp: Número do cliente para o atendente iniciar o contato.

    Returns:
        dict com status do envio.
    """
    from whatsapp.client import WhatsAppClient
    import os

    client = WhatsAppClient()
    agent_number = os.getenv("HUMAN_AGENT_WHATSAPP")
    message = (
        f"🔔 *Novo lead qualificado!*\n\n"
        f"📋 {summary}\n\n"
        f"📱 WhatsApp do cliente: {whatsapp}\n"
        f"🔗 CRM: {os.getenv('CRM_BASE_URL', '')}/contacts/{contact_id}"
    )
    result = client.send_message(to=agent_number, text=message)
    logger.info("Human agent notified for contact %s", contact_id)
    return result


@tool
def log_conversation_message(
    contact_id: str,
    direction: str,
    content: str,
    timestamp: str,
) -> dict:
    """
    Registra uma mensagem no histórico do CRM para auditoria (RF-08).

    Args:
        contact_id: ID do contato no CRM.
        direction: 'inbound' (cliente → agente) ou 'outbound' (agente → cliente).
        content: Texto da mensagem.
        timestamp: ISO-8601 timestamp da mensagem.

    Returns:
        dict com status do log.
    """
    from crm.client import CRMClient
    client = CRMClient()
    return client.log_activity(
        contact_id=contact_id,
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
ALL_TOOLS = [
    create_crm_contact,
    update_crm_lead,
    advance_pipeline_stage,
    notify_human_agent,
    log_conversation_message,
    send_whatsapp_message,
]
