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


# ---------------------------------------------------------------------------
# Agendamento Tools (v2.0)
# ---------------------------------------------------------------------------

@tool
async def verificar_disponibilidade(
    data: str,
    hora_inicio: str,
    duracao_minutos: int = 60,
) -> dict:
    """
    Verifica disponibilidade de um horário para agendamento.
    Se não disponível, retorna próximas 3 opções.

    Args:
        data: Data em formato YYYY-MM-DD (ex: '2026-06-15')
        hora_inicio: Hora em formato HH:MM (ex: '14:30')
        duracao_minutos: 40 (consulta) ou 60 (atendimento)

    Returns:
        dict com 'disponivel' (bool), 'motivo' se não disponível,
        e 'proximas_opcoes' se não tiver o horário desejado.
    """
    from datetime import datetime
    from crm.database import get_db_session
    from crm.agenda_rules import validar_disponibilidade, get_slots_disponiveis

    try:
        # Parse data/hora
        data_str = f"{data}T{hora_inicio}:00"
        data_hora = datetime.fromisoformat(data_str)

        async with get_db_session() as session:
            valido, erro = await validar_disponibilidade(
                session, data_hora, duracao_minutos
            )

            if valido:
                return {
                    "disponivel": True,
                    "data": data,
                    "hora": hora_inicio,
                    "duracao_minutos": duracao_minutos,
                }

            # Retornar próximas opções
            proximos_slots = await get_slots_disponiveis(
                session, data_hora, num_opcoes=3, duracao_minutos=duracao_minutos
            )

            return {
                "disponivel": False,
                "motivo": erro,
                "proximas_opcoes": proximos_slots[:3],
            }

    except Exception as exc:
        logger.error("Erro ao verificar disponibilidade: %s", exc, exc_info=True)
        return {"disponivel": False, "motivo": f"Erro: {str(exc)}"}


@tool
async def agendar_atendimento(
    contact_id: str,
    negocio_id: str,
    data: str,
    hora: str,
    tipo_agendamento: str = "consulta_inicial",
    local: str = "Presencial",
    observacoes: str = "",
) -> dict:
    """
    Cria um agendamento para o cliente.
    O agendamento é criado mas REQUER confirmação antes de ser ativado.

    Args:
        contact_id: ID do contato no CRM
        negocio_id: ID do negócio/deal vinculado
        data: Data em formato YYYY-MM-DD
        hora: Hora em formato HH:MM
        tipo_agendamento: 'consulta_inicial' | 'visita_local' | 'apresentacao_orcamento'
        local: Endereço ou 'Online'
        observacoes: Notas adicionais

    Returns:
        dict com agendamento criado e link de confirmação.
    """
    from datetime import datetime
    from crm.database import get_db_session
    from crm.models import Agendamento
    from crm.agenda_rules import validar_disponibilidade, formatar_agendamento_para_mensagem

    try:
        # Parse data/hora
        data_str = f"{data}T{hora}:00"
        data_hora = datetime.fromisoformat(data_str)

        async with get_db_session() as session:
            # Validar slot
            valido, erro = await validar_disponibilidade(session, data_hora, duracao=60)
            if not valido:
                return {"sucesso": False, "erro": erro}

            # Criar agendamento (não confirmado)
            agendamento = Agendamento(
                negocio_id=int(negocio_id),
                contato_id=int(contact_id),
                data_agendamento=data_hora,
                duracao_minutos=60,
                tipo_agendamento=tipo_agendamento,
                local_atendimento=local,
                observacoes=observacoes or None,
                confirmado=False,  # Aguardando confirmação
            )

            session.add(agendamento)
            await session.commit()
            await session.refresh(agendamento)

            # Formatar mensagem
            msg_confirmacao = formatar_agendamento_para_mensagem(
                data_hora, tipo_agendamento, local
            )

            logger.info(
                "Agendamento criado para contato %s: %s",
                contact_id,
                agendamento.id,
            )

            return {
                "sucesso": True,
                "agendamento_id": agendamento.id,
                "status": "pendente_confirmacao",
                "mensagem_cliente": msg_confirmacao,
                "link_confirmacao": f"https://seu-dominio.com/agendamento/{agendamento.id}/confirmar",
            }

    except Exception as exc:
        logger.error("Erro ao agendar: %s", exc, exc_info=True)
        return {"sucesso": False, "erro": str(exc)}


@tool
async def confirmar_agendamento(
    agendamento_id: str,
    confirmado: bool = True,
) -> dict:
    """
    Cliente confirma ou cancela um agendamento.

    Args:
        agendamento_id: ID do agendamento
        confirmado: True para confirmar, False para cancelar

    Returns:
        dict com status da confirmação.
    """
    from datetime import datetime
    from crm.database import get_db_session
    from crm.models import Agendamento
    from sqlalchemy import select

    try:
        async with get_db_session() as session:
            stmt = select(Agendamento).where(Agendamento.id == int(agendamento_id))
            result = await session.execute(stmt)
            agendamento = result.scalar_one_or_none()

            if not agendamento:
                return {"sucesso": False, "erro": "Agendamento não encontrado"}

            if confirmado:
                agendamento.confirmado = True
                agendamento.data_confirmacao = datetime.now()
                status = "confirmado"
                msg = "✅ Agendamento confirmado! Até breve!"
            else:
                agendamento.cancelado_em = datetime.now()
                agendamento.motivo_cancelamento = "Cancelado pelo cliente"
                status = "cancelado"
                msg = "❌ Agendamento cancelado. Caso queira remarcar, é só falar!"

            await session.commit()

            logger.info(f"Agendamento {agendamento_id} {status}")

            return {
                "sucesso": True,
                "agendamento_id": agendamento_id,
                "status": status,
                "mensagem": msg,
            }

    except Exception as exc:
        logger.error("Erro ao confirmar agendamento: %s", exc, exc_info=True)
        return {"sucesso": False, "erro": str(exc)}


@tool
async def listar_agendamentos_disponiveis(
    data_inicio: str = None,
    dias_afrente: int = 7,
    num_opcoes: int = 5,
) -> dict:
    """
    Lista os próximos horários disponíveis para agendamento.

    Args:
        data_inicio: Data inicial em YYYY-MM-DD (default: hoje)
        dias_afrente: Quantos dias afrente buscar (default: 7)
        num_opcoes: Quantas opções retornar (default: 5)

    Returns:
        dict com lista de slots disponíveis em formato amigável.
    """
    from datetime import datetime, timedelta
    from crm.database import get_db_session
    from crm.agenda_rules import get_slots_disponiveis

    try:
        if data_inicio:
            data = datetime.fromisoformat(data_inicio)
        else:
            data = datetime.now() + timedelta(days=1)

        async with get_db_session() as session:
            slots = await get_slots_disponiveis(
                session, data, num_opcoes=num_opcoes
            )

            # Formatar para mensagem WhatsApp
            opcoes_formatadas = []
            for i, slot in enumerate(slots, 1):
                opcoes_formatadas.append(
                    f"{i}️⃣ {slot['data']} às {slot['hora']} ({slot['dia_semana']})"
                )

            msg = "📅 *Próximas datas disponíveis:*\n\n" + "\n".join(
                opcoes_formatadas
            )

            return {
                "sucesso": True,
                "total_opcoes": len(slots),
                "slots": slots,
                "mensagem_cliente": msg,
            }

    except Exception as exc:
        logger.error("Erro ao listar agendamentos: %s", exc, exc_info=True)
        return {"sucesso": False, "erro": str(exc)}


@tool
async def search_knowledge_base(query: str, tenant_id: int) -> dict:
    """
    Busca informações na base de conhecimento (RAG) do tenant.
    Use esta ferramenta para responder perguntas sobre manuais, catálogos ou regras do negócio.

    Args:
        query: A pergunta ou termo a ser buscado.
        tenant_id: ID do tenant (injetado automaticamente pelo sistema, repasse o que está no estado).

    Returns:
        dict com os textos mais relevantes encontrados.
    """
    from agent.vector_store import search_knowledge
    try:
        docs = await search_knowledge(query=query, tenant_id=tenant_id, k=3)
        if not docs:
            return {"resultado": "Nenhuma informação relevante encontrada na base de conhecimento."}
        
        # Junta o conteúdo dos documentos
        context = "\n\n---\n\n".join(doc.page_content for doc in docs)
        return {"resultado": context}
    except Exception as exc:
        logger.error("Erro na busca RAG: %s", exc)
        return {"erro": str(exc)}

# Registro de todas as tools disponíveis para bind ao LLM
# Note: LangChain detecta se a tool é síncrona ou assíncrona automaticamente.
ALL_TOOLS = [
    create_crm_contact,
    update_crm_lead,
    advance_pipeline_stage,
    notify_human_agent,
    log_conversation_message,
    send_whatsapp_message,
    # Agendamento (v2.0)
    verificar_disponibilidade,
    agendar_atendimento,
    confirmar_agendamento,
    listar_agendamentos_disponiveis,
    # RAG
    search_knowledge_base,
]
