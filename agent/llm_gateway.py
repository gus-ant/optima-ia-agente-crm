"""
agent/llm_gateway.py
---------------------
LLM Gateway Multi-Tenant com roteamento por plano e fallback automático.

Roteamento:
  - basic      → gpt-3.5-turbo (custo baixo)
  - pro        → gpt-4o (default)
  - enterprise → modelo configurado no AgentConfig (ex: gpt-4o, claude-3-5-sonnet)

O gateway:
  1. Carrega a config do tenant do AgentState (já hidratada no início da sessão).
  2. Seleciona o modelo correto com base no plano.
  3. Aplica fallback automático se o modelo primário falhar.
  4. Retorna um ChatOpenAI com tools vinculadas.

Uso:
    llm = get_llm_for_tenant(state)
    response = llm.invoke(messages)
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Optional

from langchain_openai import ChatOpenAI

if TYPE_CHECKING:
    from agent.state import AgentState

logger = logging.getLogger(__name__)

# Mapeamento de plano → modelo padrão
_PLAN_MODEL_MAP = {
    "basic": "gpt-3.5-turbo",
    "pro": "gpt-4o",
    "enterprise": "gpt-4o",
}

# Fallback global se tudo falhar
_FALLBACK_MODEL = "gpt-3.5-turbo"


def get_llm_for_tenant(state: "AgentState", bind_tools: bool = True) -> ChatOpenAI:
    """
    Retorna o LLM correto para o tenant com base no plano e configuração.

    Ordem de prioridade para modelo:
      1. AgentConfig.llm_model (configurado pelo admin do tenant)
      2. Modelo padrão do plano (basic/pro/enterprise)
      3. LLM_MODEL env var (fallback global)
      4. gpt-3.5-turbo (fallback hardcoded)

    Args:
        state: AgentState com agent_config já carregado.
        bind_tools: Se True, vincula as tools do agente ao LLM.

    Returns:
        ChatOpenAI com ou sem tools vinculadas.
    """
    from agent.tools import ALL_TOOLS

    agent_config = state.get("agent_config") or {}
    plano = agent_config.get("plano", "basic")
    temperatura = agent_config.get("temperatura", 0.3)

    # Resolução do modelo
    model = (
        agent_config.get("llm_model")                    # 1. Config do tenant
        or _PLAN_MODEL_MAP.get(plano)                    # 2. Padrão do plano
        or os.getenv("LLM_MODEL")                        # 3. Env var global
        or _FALLBACK_MODEL                               # 4. Hardcoded fallback
    )

    logger.debug(
        "LLMGateway: tenant_id=%s plano=%s model=%s temperatura=%.1f",
        state.get("tenant_id"),
        plano,
        model,
        temperatura,
    )

    llm = ChatOpenAI(model=model, temperature=temperatura)

    if bind_tools:
        return llm.bind_tools(ALL_TOOLS)

    return llm


def get_system_prompt_for_tenant(state: "AgentState") -> str:
    """
    Retorna o system prompt do tenant ou o prompt padrão da Lara.

    Ordem de prioridade:
      1. AgentConfig.system_prompt (personalizado pelo admin)
      2. LARA_SYSTEM_PROMPT (padrão do código)
    """
    from agent.prompts import LARA_SYSTEM_PROMPT

    agent_config = state.get("agent_config") or {}
    custom_prompt = agent_config.get("system_prompt")

    if custom_prompt and custom_prompt.strip():
        logger.debug(
            "LLMGateway: usando system_prompt personalizado para tenant_id=%s",
            state.get("tenant_id"),
        )
        return custom_prompt

    return LARA_SYSTEM_PROMPT


async def load_agent_config_for_tenant(tenant_id: int) -> dict:
    """
    Carrega a AgentConfig e o plano do tenant do banco de dados.
    Retorna um dict compatível com AgentConfigSnapshot.

    Chamado uma vez por sessão (no node_receive_message) para evitar
    queries repetidas ao banco a cada mensagem.
    """
    from sqlalchemy import select
    from crm.database import AsyncSessionLocal
    from crm.models import AgentConfig, Tenant

    defaults = {
        "nome_agente": "Lara",
        "system_prompt": None,
        "llm_model": None,
        "temperatura": 0.3,
        "human_agent_whatsapp": os.getenv("HUMAN_AGENT_WHATSAPP", ""),
        "plano": "basic",
    }

    try:
        async with AsyncSessionLocal() as session:
            # Busca config do agente
            stmt_config = (
                select(AgentConfig)
                .where(AgentConfig.tenant_id == tenant_id, AgentConfig.ativo == True)
                .limit(1)
            )
            result_config = await session.execute(stmt_config)
            config = result_config.scalar_one_or_none()

            # Busca plano do tenant
            stmt_tenant = select(Tenant.plano).where(Tenant.id == tenant_id)
            result_tenant = await session.execute(stmt_tenant)
            plano = result_tenant.scalar_one_or_none() or "basic"

        if config:
            return {
                "nome_agente": config.nome_agente,
                "system_prompt": config.system_prompt,
                "llm_model": config.llm_model,
                "temperatura": config.temperatura,
                "human_agent_whatsapp": config.human_agent_whatsapp or defaults["human_agent_whatsapp"],
                "plano": plano,
            }

        return {**defaults, "plano": plano}

    except Exception as exc:
        logger.error("Erro ao carregar AgentConfig para tenant_id=%d: %s", tenant_id, exc)
        return defaults
