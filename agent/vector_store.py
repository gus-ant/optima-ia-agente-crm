"""
agent/vector_store.py
---------------------
Configuração do banco de dados vetorial (PGVector) via LangChain.
Isolamento multi-tenant garantido via filtro no metadata (tenant_id).
"""

from __future__ import annotations

import logging
import os
from typing import List

from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings
from langchain_postgres.vectorstores import PGVector

logger = logging.getLogger(__name__)

def get_embeddings_model() -> OpenAIEmbeddings:
    return OpenAIEmbeddings(
        model=os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
    )

def get_vector_store() -> PGVector:
    """
    Retorna a instância do PGVector configurada.
    Utiliza a mesma DATABASE_URL da aplicação.
    """
    db_url = os.getenv("DATABASE_URL", "postgresql+psycopg://postgres:postgrespassword@localhost:5432/optimacrm")
    # Langchain PGVector supports sync operations by default with psycopg or async with asyncpg.
    # For simplicity, we use the connection string. If it's asyncpg, we might need to adjust or use psycopg for sync fallback.
    if "asyncpg" in db_url:
        # Troca asyncpg por psycopg para o langchain PGVector se usarmos métodos síncronos
        db_url = db_url.replace("asyncpg", "psycopg")

    return PGVector(
        embeddings=get_embeddings_model(),
        collection_name="tenant_knowledge",
        connection=db_url,
        use_jsonb=True,
    )

async def search_knowledge(query: str, tenant_id: int, k: int = 4) -> List[Document]:
    """
    Busca assíncrona vetorial aplicando filtro de tenant.
    """
    vector_store = get_vector_store()
    # Usa o filtro JSONB para garantir isolamento do tenant
    docs = await vector_store.asimilarity_search(
        query=query,
        k=k,
        filter={"tenant_id": tenant_id}
    )
    return docs

async def add_knowledge(documents: List[Document], tenant_id: int) -> None:
    """
    Adiciona documentos à base injetando tenant_id no metadata.
    """
    vector_store = get_vector_store()
    for doc in documents:
        doc.metadata["tenant_id"] = tenant_id

    await vector_store.aadd_documents(documents)
    logger.info("Adicionados %d chunks ao RAG para tenant %d", len(documents), tenant_id)
