"""
tests/test_graph.py
-------------------
Testes unitários e de integração para o grafo LangGraph e CRM Próprio Local.
Executa com: pytest tests/ -v
"""

from __future__ import annotations

import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage

# Configura o ambiente para usar SQLite em memória antes de qualquer import do DB
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"

from agent.graph import build_graph
from agent.state import AgentState
from crm.database import Base, engine, get_db_session
from crm.client import LocalCRMClient
from crm.models import Contato, Negocio, Atividade


# ---------------------------------------------------------------------------
# Fixtures do Banco de Dados
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
async def setup_db():
    """Inicializa as tabelas no SQLite em memória antes de cada teste."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
def base_state() -> dict:
    return {
        "messages": [],
        "session_id": "5511999998888",
        "crm_contact_id": None,
        "contato_id": None,
        "negocio_id": None,
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
# Testes do CRM Próprio Local
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_local_crm_flow():
    """Valida a criação e atualização de contatos e negócios no banco local."""
    client = LocalCRMClient()

    # 1. Criação do Contato + Negócio automático
    res_create = await client.get_or_create_contato(
        whatsapp_id="5511999998888",
        nome="Gustavo Teste",
    )
    assert res_create["is_new"] is True
    contact_id = res_create["contact_id"]
    deal_id = res_create["deal_id"]
    assert contact_id is not None
    assert deal_id is not None

    # 2. Re-busca do mesmo contato (deve retornar is_new=False e manter IDs)
    res_get = await client.get_or_create_contato(
        whatsapp_id="5511999998888",
    )
    assert res_get["is_new"] is False
    assert res_get["contact_id"] == contact_id
    assert res_get["deal_id"] == deal_id

    # 3. Atualização dos campos do negócio
    res_update = await client.update_contact_data(
        contact_id=contact_id,
        fields={
            "lead": {"nome": "Gustavo Editado", "instagram": "@gustavo"},
            "evento": {
                "tipo": "casamento",
                "data": "2026-12-25",
                "local_nome": "Espaço Jardim",
                "num_convidados": 150,
            },
            "comercial": {"faixa_investimento": "R$ 15.000,00"},
        }
    )
    assert res_update["status"] == "success"
    assert res_update["negocio"]["tipo_evento"] == "casamento"
    assert res_update["negocio"]["data_evento"] == "2026-12-25"
    assert res_update["negocio"]["orcamento_estimado"] == 15000.0
    assert "Jardim" in res_update["negocio"]["notas_agente"]

    # 4. Avanço do pipeline / etapa de funil
    res_stage = await client.update_etapa_funil(negocio_id=int(deal_id), nova_etapa="em_qualificacao")
    assert res_stage["status"] == "success"
    assert res_stage["etapa_funil"] == "EM_QUALIFICACAO"

    # 5. Registro de Atividade (Mensagem)
    res_act = await client.log_activity(
        contact_id=1,
        direction="inbound",
        content="Olá Lara!",
        timestamp="2026-05-27T20:30:00Z"
    )
    assert res_act["status"] == "success"


# ---------------------------------------------------------------------------
# Testes de roteamento do LangGraph
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
# Testes do node receive_message
# ---------------------------------------------------------------------------

def test_node_receive_message_new_lead(base_state):
    """Para novo lead, deve inicializar pipeline_stage, dados do lead e IDs locais como None."""
    from agent.nodes import node_receive_message

    result = node_receive_message(base_state)
    assert result["pipeline_stage"] == "novo_lead"
    assert result["lead"]["whatsapp"] == "5511999998888"
    assert result["pronto_transbordo"] is False
    assert result["contato_id"] is None
    assert result["negocio_id"] is None


def test_node_receive_message_existing_lead(base_state):
    """Para lead existente (contato_id preenchido), não deve sobrescrever estado."""
    from agent.nodes import node_receive_message

    base_state["contato_id"] = 123
    base_state["pipeline_stage"] = "em_qualificacao"

    result = node_receive_message(base_state)
    assert result == {}  # estado mantido


# ---------------------------------------------------------------------------
# Testes de integração (mock LLM)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_graph_first_message(base_state):
    """
    Teste de integração: primeira mensagem deve resultar em resposta da Lara.
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
        patch("agent.llm_gateway.get_llm_for_tenant", new_callable=AsyncMock) as mock_llm_factory,
        patch("agent.nodes.node_sync_crm", return_value={}),
    ):
        mock_llm = AsyncMock()
        mock_llm.ainvoke.return_value = mock_response
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
