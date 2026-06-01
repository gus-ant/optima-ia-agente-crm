"""
agent/nodes.py
--------------
Nós (nodes) do grafo LangGraph.
Cada função representa um passo discreto no fluxo de qualificação do lead.

Multi-Tenant: usa o LLM Gateway para selecionar modelo/prompt por tenant
e thread_id composto ({tenant_id}:{phone}) para isolamento do checkpointer.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from agent.state import AgentState

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Node: receber mensagem (entry point)
# ---------------------------------------------------------------------------

def node_receive_message(state: AgentState) -> dict[str, Any]:
    """
    Ponto de entrada: normaliza a mensagem recebida e garante que o lead
    já existe no CRM. Cria contato se for a primeira mensagem.

    Multi-Tenant: carrega a AgentConfig do tenant se ainda não estiver no estado.
    """
    is_new_lead = not state.get("crm_contact_id") and not state.get("contato_id")

    updates: dict[str, Any] = {}

    if is_new_lead:
        logger.info("New lead from %s — creating CRM contact", state["session_id"])
        updates = {
            "pipeline_stage": "novo_lead",
            "pronto_transbordo": False,
            "follow_up_count": 0,
            "awaiting_media": False,
            "lead": {"whatsapp": state["session_id"]},
            "evento": {"referencias": []},
            "comercial": {},
            "contato_id": None,
            "negocio_id": None,
        }

    return updates


async def node_load_tenant_config(state: AgentState) -> dict[str, Any]:
    """
    Carrega a configuração do agente do tenant (AgentConfig + plano).
    Executado apenas uma vez por sessão (quando agent_config ainda não está no estado).
    """
    # Se já carregou nesta sessão, pula
    if state.get("agent_config"):
        return {}

    tenant_id = state.get("tenant_id")
    if not tenant_id:
        logger.warning("node_load_tenant_config: sem tenant_id no estado, usando defaults")
        return {}

    from agent.llm_gateway import load_agent_config_for_tenant
    config = await load_agent_config_for_tenant(tenant_id)
    logger.info(
        "AgentConfig carregado para tenant_id=%d: plano=%s model=%s",
        tenant_id, config.get("plano"), config.get("llm_model") or "default",
    )
    return {"agent_config": config}


# ---------------------------------------------------------------------------
# Node: chamar o LLM (Lara)
# ---------------------------------------------------------------------------

def node_call_llm(state: AgentState) -> dict[str, Any]:
    """
    Invoca o LLM com o system prompt + histórico e retorna a resposta da Lara.
    Também extrai o bloco <extraction> JSON embutido na resposta.

    Multi-Tenant: usa o LLM Gateway para obter o modelo e prompt corretos.
    """
    from agent.llm_gateway import get_llm_for_tenant, get_system_prompt_for_tenant
    from agent.prompts import EXTRACTION_INSTRUCTION

    llm = get_llm_for_tenant(state)
    system_prompt = get_system_prompt_for_tenant(state)

    messages = [
        SystemMessage(content=system_prompt),
        *state["messages"],
    ]

    response: AIMessage = llm.invoke(messages)
    logger.debug("LLM response: %s", response.content[:120])

    # Extrai JSON de extração embutido na resposta
    extracted = _parse_extraction(response.content)

    # Remove o bloco <extraction>...</extraction> do texto que vai para o cliente
    clean_content = re.sub(
        r"<extraction>.*?</extraction>", "", response.content, flags=re.DOTALL
    ).strip()

    clean_response = AIMessage(content=clean_content, tool_calls=response.tool_calls)

    updates: dict[str, Any] = {"messages": [clean_response]}

    if extracted:
        updates.update(_merge_extraction(state, extracted))

    return updates


# ---------------------------------------------------------------------------
# Node: executar tools
# ---------------------------------------------------------------------------

def node_tool_executor(state: AgentState) -> dict[str, Any]:
    """
    Executa as tool calls retornadas pelo LLM (ToolNode pattern).
    LangGraph cuida da serialização; este node é um wrapper explícito
    para logging e tratamento de erros.
    """
    from langgraph.prebuilt import ToolNode
    from agent.tools import ALL_TOOLS

    tool_node = ToolNode(ALL_TOOLS)
    result = tool_node.invoke(state)

    # Captura os IDs locais se a tool create_crm_contact foi executada
    updates = _extract_crm_ids(result.get("messages", []))
    if updates:
        return {**result, **updates}

    return result


# ---------------------------------------------------------------------------
# Node: sincronizar CRM
# ---------------------------------------------------------------------------

async def node_sync_crm(state: AgentState) -> dict[str, Any]:
    """
    Atualiza o CRM local com os dados extraídos e avança a etapa do pipeline.
    Multi-Tenant: passa tenant_id ao CRMClient para uso no get_tenant_db_session.
    """
    contact_id = state.get("crm_contact_id")
    if not contact_id:
        logger.warning("sync_crm: no contact_id yet, skipping")
        return {}

    from crm.client import CRMClient
    tenant_id = state.get("tenant_id")
    client = CRMClient(tenant_id=tenant_id)

    fields = {
        "lead": state.get("lead", {}),
        "evento": state.get("evento", {}),
        "comercial": state.get("comercial", {}),
        "pipeline_stage": state.get("pipeline_stage", "em_qualificacao"),
    }

    await client.update_contact_data(contact_id=contact_id, fields=fields)

    negocio_id = state.get("negocio_id")
    if negocio_id:
        await client.update_etapa_funil(
            negocio_id=negocio_id,
            nova_etapa=state.get("pipeline_stage", "em_qualificacao"),
        )

    return {}


# ---------------------------------------------------------------------------
# Node: transbordo humano
# ---------------------------------------------------------------------------

def node_handoff(state: AgentState) -> dict[str, Any]:
    """
    Envia notificação ao atendente humano e mensagem de encerramento ao cliente.
    Multi-Tenant: usa o número do atendente da AgentConfig do tenant.
    """
    from whatsapp.client import WhatsAppClient
    from agent.prompts import HANDOFF_MESSAGE

    client = WhatsAppClient()
    nome = state.get("lead", {}).get("nome", "cliente")
    farewell = HANDOFF_MESSAGE.format(nome=nome)

    # Mensagem de encerramento para o cliente
    client.send_message(to=state["session_id"], text=farewell)

    # Número do atendente: tenta agent_config primeiro, depois env var
    agent_config = state.get("agent_config") or {}
    agent_number = (
        agent_config.get("human_agent_whatsapp")
        or ""
    )

    if agent_number:
        summary = _build_lead_summary(state)
        tenant_info = f"🏢 Tenant: {state.get('tenant_slug', 'N/D')}"
        client.send_message(
            to=agent_number,
            text=(
                f"🔔 *Novo lead qualificado!*\n\n{summary}\n\n"
                f"📱 Cliente: {state['session_id']}\n{tenant_info}"
            ),
        )

    return {"pipeline_stage": "pronto_orcamento"}


# ---------------------------------------------------------------------------
# Node: follow-up automático
# ---------------------------------------------------------------------------

def node_follow_up(state: AgentState) -> dict[str, Any]:
    """
    Envia mensagem de follow-up após inatividade (RF-10).
    Agendado externamente via N8N trigger (cron 24h).
    """
    from agent.prompts import FOLLOW_UP_TEMPLATES
    from whatsapp.client import WhatsAppClient

    client = WhatsAppClient()
    nome = state.get("lead", {}).get("nome", "")
    count = state.get("follow_up_count", 0)

    template_key = "24h" if count == 0 else "48h"
    text = FOLLOW_UP_TEMPLATES[template_key].format(nome=nome or "")

    client.send_message(to=state["session_id"], text=text)

    return {"follow_up_count": count + 1}


# ---------------------------------------------------------------------------
# Helpers privados
# ---------------------------------------------------------------------------

def _parse_extraction(text: str) -> dict | None:
    """Extrai e parseia o bloco JSON <extraction>...</extraction> da resposta do LLM."""
    match = re.search(r"<extraction>(.*?)</extraction>", text, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(1).strip())
    except json.JSONDecodeError as exc:
        logger.warning("Failed to parse extraction JSON: %s", exc)
        return None


def _merge_extraction(state: AgentState, extracted: dict) -> dict:
    """Mescla os dados extraídos com o estado atual (campos não-nulos têm prioridade)."""
    updates: dict = {}

    for key in ("lead", "evento", "comercial"):
        new_data = extracted.get(key, {})
        current = dict(state.get(key, {}) or {})
        for field, value in (new_data or {}).items():
            if value is not None:
                current[field] = value
        updates[key] = current

    if "pipeline_stage" in extracted and extracted["pipeline_stage"]:
        updates["pipeline_stage"] = extracted["pipeline_stage"]

    if "pronto_transbordo" in extracted:
        updates["pronto_transbordo"] = bool(extracted["pronto_transbordo"])

    return updates


def _extract_crm_ids(messages: list) -> dict:
    """
    Extrai os IDs do contato e do negócio gerados pela tool create_crm_contact.
    """
    for msg in messages:
        if hasattr(msg, "name") and msg.name == "create_crm_contact":
            try:
                data = json.loads(msg.content)
                contact_id = data.get("contact_id")
                deal_id = data.get("deal_id")

                updates = {}
                if contact_id:
                    updates["crm_contact_id"] = str(contact_id)
                    try:
                        updates["contato_id"] = int(contact_id)
                    except ValueError:
                        pass
                if deal_id:
                    try:
                        updates["negocio_id"] = int(deal_id)
                    except ValueError:
                        pass
                return updates
            except Exception as exc:
                logger.warning("Falha ao ler IDs do retorno da tool create_crm_contact: %s", exc)
    return {}


def _build_lead_summary(state: AgentState) -> str:
    lead = state.get("lead", {})
    evento = state.get("evento", {})
    comercial = state.get("comercial", {})

    lines = [
        f"👤 Nome: {lead.get('nome', 'N/D')}",
        f"🎉 Evento: {evento.get('tipo', 'N/D')} em {evento.get('data', 'N/D')}",
        f"📍 Local: {evento.get('local_nome', '')} — {evento.get('local_cidade', 'N/D')}",
        f"👥 Convidados: {evento.get('num_convidados', 'N/D')}",
        f"💰 Investimento: {comercial.get('faixa_investimento', 'N/D')}",
    ]
    return "\n".join(lines)
