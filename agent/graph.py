"""
agent/graph.py
--------------
Monta e compila o grafo LangGraph do agente Lara.

Fluxo principal:
  receive_message → call_llm → [tool_executor?] → sync_crm → [handoff?] → END

Nós condicionais:
  - Se o LLM retornou tool_calls → vai para tool_executor
  - Se pronto_transbordo == True → vai para handoff
"""

from __future__ import annotations

import logging
from typing import Literal

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from agent.nodes import (
    node_call_llm,
    node_handoff,
    node_receive_message,
    node_sync_crm,
    node_tool_executor,
)
from agent.state import AgentState

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Funções de roteamento (edges condicionais)
# ---------------------------------------------------------------------------

def route_after_llm(
    state: AgentState,
) -> Literal["tool_executor", "sync_crm"]:
    """Após o LLM: se há tool calls pendentes, executa-as; senão, sincroniza o CRM."""
    last_message = state["messages"][-1]
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "tool_executor"
    return "sync_crm"


def route_after_sync(
    state: AgentState,
) -> Literal["handoff", "__end__"]:
    """Após sync CRM: se dossiê completo, executa transbordo; caso contrário, encerra."""
    if state.get("pronto_transbordo"):
        return "handoff"
    return "__end__"


# ---------------------------------------------------------------------------
# Construção do grafo
# ---------------------------------------------------------------------------

def build_graph(checkpointer=None) -> StateGraph:
    """
    Constrói e compila o grafo LangGraph.

    Args:
        checkpointer: Implementação de persistência de estado.
                      Padrão: MemorySaver (in-memory, apenas para dev).
                      Em produção, usar PostgresSaver ou RedisSaver.

    Returns:
        Grafo compilado pronto para invocar.
    """
    if checkpointer is None:
        checkpointer = MemorySaver()

    builder = StateGraph(AgentState)

    # Adiciona nós
    builder.add_node("receive_message", node_receive_message)
    builder.add_node("call_llm", node_call_llm)
    builder.add_node("tool_executor", node_tool_executor)
    builder.add_node("sync_crm", node_sync_crm)
    builder.add_node("handoff", node_handoff)

    # Edges fixos
    builder.add_edge(START, "receive_message")
    builder.add_edge("receive_message", "call_llm")
    builder.add_edge("tool_executor", "sync_crm")   # após tools, sempre sincroniza
    builder.add_edge("handoff", END)

    # Edges condicionais
    builder.add_conditional_edges(
        "call_llm",
        route_after_llm,
        {"tool_executor": "tool_executor", "sync_crm": "sync_crm"},
    )
    builder.add_conditional_edges(
        "sync_crm",
        route_after_sync,
        {"handoff": "handoff", "__end__": END},
    )

    graph = builder.compile(checkpointer=checkpointer)
    logger.info("LangGraph compiled successfully")
    return graph


# ---------------------------------------------------------------------------
# Singleton de grafo para uso pela API
# ---------------------------------------------------------------------------

_graph = None


def get_graph():
    """Retorna o grafo compilado (singleton). Lazy init."""
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph
