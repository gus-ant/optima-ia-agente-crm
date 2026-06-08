"""
crm/database.py
---------------
Configuração do banco de dados relacional (SQLAlchemy assíncrono).
Suporta PostgreSQL via asyncpg e SQLite via aiosqlite (fallback para dev/testes).

Multi-Tenant: expõe `get_tenant_db_session()` que injeta automaticamente
o tenant_id via SET LOCAL antes de ceder a sessão, ativando o RLS.
"""

from __future__ import annotations

import os
import logging
from asyncio import current_task
from typing import AsyncGenerator, Optional
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_scoped_session,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import declarative_base

logger = logging.getLogger(__name__)

# Resgata a URL do banco, com fallback amigável para SQLite local
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite+aiosqlite:///./optimacrm.db"
)


def _is_postgres() -> bool:
    """Retorna True se o DATABASE_URL aponta para PostgreSQL (inclui Supabase)."""
    return DATABASE_URL.startswith("postgresql") or DATABASE_URL.startswith("postgres")


def _is_supabase() -> bool:
    """Detecta se o banco é Supabase pela presença do domínio característico."""
    return "supabase.co" in DATABASE_URL or "supabase.com" in DATABASE_URL


# Argumentos extras de conexão para asyncpg no Supabase:
# - ssl="require": SSL obrigatório em todos os projetos Supabase
# - statement_cache_size=0: desabilita prepared statements, necessário para
#   funcionar com o Transaction Pooler do Supabase (porta 6543).
#   Na conexão direta (porta 5432) é opcional, mas não causa problemas.
_connect_args: dict = {}
if _is_postgres():
    _connect_args["statement_cache_size"] = 0
if _is_supabase():
    _connect_args["ssl"] = "require"

# Configuração da Engine assíncrona
# pool_pre_ping previne erros de conexões inativas
engine = create_async_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    echo=False,
    connect_args=_connect_args,
)

# Factory de sessões assíncronas
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# Base declarativa para modelos SQLAlchemy
Base = declarative_base()


async def init_db() -> None:
    """
    Cria as tabelas no banco de dados caso elas não existam.
    Chamado no startup da aplicação.
    """
    async with engine.begin() as conn:
        # conn.run_sync executa funções síncronas (como metadata.create_all)
        # dentro do fluxo assíncrono do SQLAlchemy
        await conn.run_sync(Base.metadata.create_all)


@asynccontextmanager
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Gerenciador de contexto assíncrono para sessões do banco de dados.
    Uso: async with get_db_session() as session: ...

    Para operações multi-tenant, prefira get_tenant_db_session() que injeta
    o tenant_id automaticamente via SET LOCAL (ativa o filtro RLS).
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@asynccontextmanager
async def get_tenant_db_session(
    tenant_id: Optional[int] = None,
) -> AsyncGenerator[AsyncSession, None]:
    """
    Gerenciador de contexto assíncrono com suporte a Multi-Tenant via RLS.

    Injeta o tenant_id no parâmetro de runtime do PostgreSQL (SET LOCAL)
    antes de ceder a sessão, garantindo que o RLS filtre os dados corretamente.

    Se `tenant_id` não for passado explicitamente, tenta usar o valor do
    ContextVar `current_tenant_id` (setado pelo TenantMiddleware).

    Uso:
        async with get_tenant_db_session(tenant_id=42) as session:
            result = await session.execute(select(Contato))

    Para não passar tenant_id manualmente (middleware já setou):
        async with get_tenant_db_session() as session:
            ...
    """
    from crm.tenant import current_tenant_id, tenant_context

    # Resolve tenant_id: parâmetro explícito > ContextVar > None
    resolved_id = tenant_id or current_tenant_id.get()

    async with AsyncSessionLocal() as session:
        async with session.begin():
            try:
                if resolved_id is not None:
                    async with tenant_context(session, resolved_id):
                        yield session
                else:
                    logger.warning(
                        "get_tenant_db_session: nenhum tenant_id disponível — "
                        "executando SEM isolamento RLS"
                    )
                    yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
