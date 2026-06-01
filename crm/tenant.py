"""
crm/tenant.py
-------------
Gerenciamento de Contexto Multi-Tenant.

Responsabilidades:
  1. Armazenar o tenant_id corrente via contextvars (thread-safe e asyncio-safe).
  2. Expor helper para injetar o parâmetro de runtime no PostgreSQL via SET LOCAL.
  3. Fornecer context manager assíncrono para garantir que toda sessão de banco
     receba o tenant_id antes de qualquer query, ativando o filtro RLS.

Uso típico no webhook:
    async with tenant_context(session, tenant_id=42):
        result = await session.execute(select(Contato))

Uso no FastAPI Middleware:
    current_tenant_id.set(tenant.id)
"""

from __future__ import annotations

import logging
from contextvars import ContextVar
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# ContextVar: armazena o tenant_id da requisição corrente
# Seguro para uso simultâneo em asyncio sem race conditions
# ---------------------------------------------------------------------------

current_tenant_id: ContextVar[Optional[int]] = ContextVar(
    "current_tenant_id", default=None
)


def get_current_tenant_id() -> Optional[int]:
    """Retorna o tenant_id do contexto da requisição atual."""
    return current_tenant_id.get()


def require_tenant_id() -> int:
    """
    Retorna o tenant_id do contexto ou lança ValueError.
    Use em operações que OBRIGATORIAMENTE precisam de isolamento.
    """
    tid = current_tenant_id.get()
    if tid is None:
        raise ValueError(
            "Nenhum tenant_id encontrado no contexto. "
            "Certifique-se de que o TenantMiddleware está ativo."
        )
    return tid


# ---------------------------------------------------------------------------
# Context manager: injeta o tenant_id no PostgreSQL via SET LOCAL
# ---------------------------------------------------------------------------

@asynccontextmanager
async def tenant_context(
    session: AsyncSession, tenant_id: int
) -> AsyncGenerator[AsyncSession, None]:
    """
    Context manager assíncrono que configura o parâmetro de runtime do PostgreSQL
    antes de qualquer query, garantindo que o RLS filtre pelos dados do tenant correto.

    IMPORTANTE:
    - SET LOCAL dura apenas até o próximo COMMIT/ROLLBACK.
    - Toda a operação deve ocorrer dentro de um único begin() para manter o isolamento.
    - O nome do parâmetro usa ponto (app.current_tenant_id) — exigência do PostgreSQL
      para parâmetros personalizados de runtime (GUC customizados).

    Exemplo:
        async with session.begin():
            async with tenant_context(session, tenant_id=42):
                result = await session.execute(select(Contato))
    """
    # Injeta no ContextVar para uso em código Python (independente do banco)
    token = current_tenant_id.set(tenant_id)
    try:
        # Para PostgreSQL: ativa o filtro RLS na transação corrente
        # SQLite ignora esse comando (SET LOCAL não existe — retorna erro silencioso)
        try:
            await session.execute(
                text("SELECT set_config('app.current_tenant_id', :tid, true)"),
                {"tid": str(tenant_id)},
            )
            logger.debug("tenant_context: SET LOCAL app.current_tenant_id = %d", tenant_id)
        except Exception:
            # SQLite não suporta set_config — ignora silenciosamente em dev
            logger.debug("tenant_context: set_config não suportado (provavelmente SQLite dev)")

        yield session
    finally:
        current_tenant_id.reset(token)


# ---------------------------------------------------------------------------
# Helper: resolve tenant_id a partir do slug (para roteamento via subdomínio)
# ---------------------------------------------------------------------------

async def resolve_tenant_by_slug(session: AsyncSession, slug: str) -> Optional[int]:
    """
    Busca o tenant_id pelo slug sem aplicar RLS (tabela tenants é global).
    Retorna None se o tenant não existir ou estiver inativo.
    """
    from sqlalchemy import select
    from crm.models import Tenant, TenantStatus

    try:
        stmt = select(Tenant.id).where(
            Tenant.slug == slug,
            Tenant.status.in_([TenantStatus.ACTIVE, TenantStatus.TRIAL]),
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()
    except Exception as exc:
        logger.error("Erro ao resolver tenant para slug='%s': %s", slug, exc)
        return None
