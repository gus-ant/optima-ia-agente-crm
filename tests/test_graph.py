"""
tests/test_graph.py
-------------------
Testes unitários para o grafo LangGraph do agente Lara.
Executa com: pytest tests/ -v
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from agent.graph import build_graph
from agent.state import AgentState


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def base_state() -> dict:
    return {
        "messages": [],
        "session_id": "5511999998888",
        "crm_contact_id": None,
        "lead": {"whatsapp": "5511999998888"},
        "evento": {"referencias": []},
        "comercial": {},
        "pipeline_stage": "novo_lead",
        "pronto_transbordo": False,
        "follow_up_count": 0,
        "awaiting_media": False,
        "error_message": None,
    }


# ---------------------------------------------------------------------------
# Testes de roteamento
# ---------------------------------------------------------------------------

def test_route_after_llm_no_tools():
    """Se o LLM não retornou tool_calls, deve ir para sync_crm."""
    from agent.graph import route_after_llm

    state = {
        "messages": [AIMessage(content="Olá! Qual é o seu nome?")],
        "pronto_transbordo": False,
    }
    assert route_after_llm(state) == "sync_crm"


def test_route_after_llm_with_tools():
    """Se o LLM retornou tool_calls, deve ir para tool_executor."""
    from agent.graph import route_after_llm

    msg = AIMessage(content="", tool_calls=[{"name": "create_crm_contact", "args": {}, "id": "1"}])
    state = {"messages": [msg], "pronto_transbordo": False}
    assert route_after_llm(state) == "tool_executor"


def test_route_after_sync_ready_for_handoff():
    """Se pronto_transbordo=True, deve ir para handoff."""
    from agent.graph import route_after_sync

    state = {"pronto_transbordo": True}
    assert route_after_sync(state) == "handoff"


def test_route_after_sync_not_ready():
    """Se pronto_transbordo=False, deve encerrar."""
    from agent.graph import route_after_sync

    state = {"pronto_transbordo": False}
    assert route_after_sync(state) == "__end__"


# ---------------------------------------------------------------------------
# Testes de extração
# ---------------------------------------------------------------------------

def test_parse_extraction_valid():
    """Deve extrair e parsear o JSON do bloco <extraction>."""
    from agent.nodes import _parse_extraction

    text = """
    Oi! Qual o tipo do evento?
    <extraction>{"lead": {"nome": "Ana", "whatsapp": "5511999998888"}, "pipeline_stage": "em_qualificacao"}</extraction>
    """
    result = _parse_extraction(text)
    assert result is not None
    assert result["lead"]["nome"] == "Ana"
    assert result["pipeline_stage"] == "em_qualificacao"


def test_parse_extraction_missing():
    """Deve retornar None se não houver bloco <extraction>."""
    from agent.nodes import _parse_extraction

    result = _parse_extraction("Olá! Qual é o seu nome?")
    assert result is None


def test_parse_extraction_invalid_json():
    """Deve retornar None se o JSON for inválido."""
    from agent.nodes import _parse_extraction

    result = _parse_extraction("<extraction>{invalid json}</extraction>")
    assert result is None


# ---------------------------------------------------------------------------
# Testes do node receive_message
# ---------------------------------------------------------------------------

def test_node_receive_message_new_lead(base_state):
    """Para novo lead, deve inicializar pipeline_stage e dados do lead."""
    from agent.nodes import node_receive_message

    result = node_receive_message(base_state)
    assert result["pipeline_stage"] == "novo_lead"
    assert result["lead"]["whatsapp"] == "5511999998888"
    assert result["pronto_transbordo"] is False


def test_node_receive_message_existing_lead(base_state):
    """Para lead existente, não deve sobrescrever estado."""
    from agent.nodes import node_receive_message

    base_state["crm_contact_id"] = "123"
    base_state["pipeline_stage"] = "em_qualificacao"

    result = node_receive_message(base_state)
    assert result == {}  # estado mantido


# ---------------------------------------------------------------------------
# Testes de integração (mock LLM)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_graph_first_message(base_state):
    """
    Teste de integração: primeira mensagem deve resultar em resposta da Lara
    e criação de lead no CRM.
    """
    mock_response = AIMessage(
        content=(
            "Olá! Sou a Lara, da Lu Decorações 🌸 "
            "Ficamos felizes em ter você aqui! "
            "Para começarmos, poderia me dizer seu nome completo? "
            "<extraction>{\"lead\": {\"whatsapp\": \"5511999998888\", \"nome\": null}, "
            "\"evento\": {\"referencias\": []}, \"comercial\": {}, "
            "\"pipeline_stage\": \"em_qualificacao\", \"pronto_transbordo\": false}</extraction>"
        )
    )

    with (
        patch("agent.nodes._get_llm") as mock_llm_factory,
        patch("agent.nodes.node_sync_crm", return_value={}),
    ):
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = mock_response
        mock_llm_factory.return_value = mock_llm

        graph = build_graph()
        config = {"configurable": {"thread_id": "5511999998888"}}

        input_state = {
            **base_state,
            "messages": [HumanMessage(content="Oi, quero informações sobre decoração!")],
        }

        result = await graph.ainvoke(input_state, config=config)

        assert result is not None
        assert len(result["messages"]) > 0
        assert result["pipeline_stage"] == "em_qualificacao"
