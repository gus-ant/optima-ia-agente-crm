"""
crm/database.py
---------------
Configuração do banco de dados relacional (SQLAlchemy assíncrono).
Suporta PostgreSQL via asyncpg e SQLite via aiosqlite (fallback para dev/testes).
"""

from __future__ import annotations

import os
from asyncio import current_task
from typing import AsyncGenerator

from contextlib import asynccontextmanager
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_scoped_session,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import declarative_base

# Resgata a URL do banco, com fallback amigável para SQLite local
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite+aiosqlite:///./optimacrm.db"
)

# Configuração da Engine assíncrona
# Usamos pool_pre_ping para prevenir erros de conexões inativas
engine = create_async_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    echo=False,
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

