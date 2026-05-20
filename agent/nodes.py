"""
agent/nodes.py
--------------
Nós (nodes) do grafo LangGraph.
Cada função representa um passo discreto no fluxo de qualificação do lead.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from agent.prompts import (
    EXTRACTION_INSTRUCTION,
    HANDOFF_MESSAGE,
    LARA_SYSTEM_PROMPT,
)
from agent.state import AgentState
from agent.tools import ALL_TOOLS

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# LLM singleton (sobrescrito em testes via monkeypatch)
# ---------------------------------------------------------------------------

def _get_llm() -> ChatOpenAI:
    """Retorna instância do LLM com tools vinculadas."""
    import os
    model = os.getenv("LLM_MODEL", "gpt-4o")
    llm = ChatOpenAI(model=model, temperature=0.3)
    return llm.bind_tools(ALL_TOOLS)


# ---------------------------------------------------------------------------
# Node: receber mensagem (entry point)
# ---------------------------------------------------------------------------

def node_receive_message(state: AgentState) -> dict[str, Any]:
    """
    Ponto de entrada: normaliza a mensagem recebida e garante que o lead
    já existe no CRM. Cria contato se for a primeira mensagem.
    """
    is_new_lead = not state.get("crm_contact_id")

    if is_new_lead:
        logger.info("New lead from %s — creating CRM contact", state["session_id"])
        # O node não cria diretamente; delega ao tool_executor via LLM
        return {
            "pipeline_stage": "novo_lead",
            "pronto_transbordo": False,
            "follow_up_count": 0,
            "awaiting_media": False,
            "lead": {"whatsapp": state["session_id"]},
            "evento": {"referencias": []},
            "comercial": {},
        }

    return {}  # estado existente mantido


# ---------------------------------------------------------------------------
# Node: chamar o LLM (Lara)
# ---------------------------------------------------------------------------

def node_call_llm(state: AgentState) -> dict[str, Any]:
    """
    Invoca o LLM com o system prompt + histórico e retorna a resposta da Lara.
    Também extrai o bloco <extraction> JSON embutido na resposta.
    """
    llm = _get_llm()

    messages = [
        SystemMessage(content=LARA_SYSTEM_PROMPT),
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
    tool_node = ToolNode(ALL_TOOLS)
    result = tool_node.invoke(state)

    # Captura contact_id se a tool create_crm_contact foi executada
    crm_id = _extract_crm_id_from_tool_messages(result.get("messages", []))
    if crm_id:
        return {**result, "crm_contact_id": crm_id}

    return result


# ---------------------------------------------------------------------------
# Node: sincronizar CRM
# ---------------------------------------------------------------------------

def node_sync_crm(state: AgentState) -> dict[str, Any]:
    """
    Atualiza o CRM com os dados extraídos e avança o pipeline se necessário.
    Executado após cada resposta do agente.
    """
    if not state.get("crm_contact_id"):
        logger.warning("sync_crm: no contact_id yet, skipping")
        return {}

    from crm.client import CRMClient
    client = CRMClient()

    fields = {
        "lead": state.get("lead", {}),
        "evento": state.get("evento", {}),
        "comercial": state.get("comercial", {}),
        "pipeline_stage": state.get("pipeline_stage", "em_qualificacao"),
    }

    client.update_contact(contact_id=state["crm_contact_id"], fields=fields)
    client.set_pipeline_stage(
        contact_id=state["crm_contact_id"],
        stage=state.get("pipeline_stage", "em_qualificacao"),
    )

    return {}


# ---------------------------------------------------------------------------
# Node: transbordo humano
# ---------------------------------------------------------------------------

def node_handoff(state: AgentState) -> dict[str, Any]:
    """
    Envia notificação ao atendente humano e mensagem de encerramento ao cliente.
    Executado apenas quando pronto_transbordo == True.
    """
    from whatsapp.client import WhatsAppClient
    import os

    client = WhatsAppClient()
    nome = state.get("lead", {}).get("nome", "cliente")
    farewell = HANDOFF_MESSAGE.format(nome=nome)

    # Mensagem de encerramento para o cliente
    client.send_message(to=state["session_id"], text=farewell)

    # Notificação interna para o atendente
    agent_number = os.getenv("HUMAN_AGENT_WHATSAPP", "")
    if agent_number:
        summary = _build_lead_summary(state)
        client.send_message(
            to=agent_number,
            text=(
                f"🔔 *Novo lead qualificado!*\n\n{summary}\n\n"
                f"📱 Cliente: {state['session_id']}"
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
        current = dict(state.get(key, {}))
        for field, value in (new_data or {}).items():
            if value is not None:
                current[field] = value
        updates[key] = current

    if "pipeline_stage" in extracted and extracted["pipeline_stage"]:
        updates["pipeline_stage"] = extracted["pipeline_stage"]

    if "pronto_transbordo" in extracted:
        updates["pronto_transbordo"] = bool(extracted["pronto_transbordo"])

    return updates


def _extract_crm_id_from_tool_messages(messages: list) -> str | None:
    """Extrai contact_id do resultado de tool create_crm_contact."""
    for msg in messages:
        if hasattr(msg, "name") and msg.name == "create_crm_contact":
            try:
                data = json.loads(msg.content)
                return data.get("contact_id")
            except Exception:
                pass
    return None


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
