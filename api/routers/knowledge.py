"""
api/routers/knowledge.py
------------------------
Endpoints de administração para Ingestão de Conhecimento RAG.
"""

from __future__ import annotations

import os
import tempfile
import logging
from typing import Dict, Any

from fastapi import APIRouter, UploadFile, File, Request, HTTPException

from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter

from crm.database import get_db_session
from crm.models import KnowledgeDocument
from agent.vector_store import add_knowledge

logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("/upload")
async def upload_knowledge_document(request: Request, file: UploadFile = File(...)) -> Dict[str, Any]:
    """
    Recebe um arquivo (PDF, TXT), extrai texto, divide em chunks,
    gera embeddings via OpenAI e armazena no PostgreSQL vetorial.
    Os dados são isolados pelo tenant_id (RLS na camada LangChain).
    """
    tenant_id = getattr(request.state, "tenant_id", None)
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Tenant não identificado pelo middleware.")

    # Registra no BD
    async with get_db_session() as session:
        doc_record = KnowledgeDocument(
            tenant_id=tenant_id,
            filename=file.filename,
            file_type=file.content_type,
            status="processing"
        )
        session.add(doc_record)
        await session.commit()
        await session.refresh(doc_record)

    # Cria arquivo temporário
    ext = os.path.splitext(file.filename)[1].lower()
    temp_fd, temp_path = tempfile.mkstemp(suffix=ext)
    
    try:
        content = await file.read()
        with os.fdopen(temp_fd, "wb") as f:
            f.write(content)

        # Processamento LangChain
        if ext == ".pdf":
            loader = PyPDFLoader(temp_path)
        else:
            # Fallback text
            loader = TextLoader(temp_path, encoding="utf-8")
        
        docs = loader.load()

        # Chunking
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=150)
        chunks = text_splitter.split_documents(docs)

        # Insere no RAG
        if chunks:
            await add_knowledge(chunks, tenant_id)

        # Atualiza status no banco
        async with get_db_session() as session:
            doc_record.status = "processed"
            session.add(doc_record)
            await session.commit()

        return {
            "status": "success",
            "document_id": doc_record.id,
            "filename": doc_record.filename,
            "chunks_added": len(chunks)
        }

    except Exception as exc:
        logger.error("Erro no processamento do documento %s: %s", file.filename, exc)
        async with get_db_session() as session:
            doc_record.status = "failed"
            session.add(doc_record)
            await session.commit()
        raise HTTPException(status_code=500, detail=f"Erro no processamento RAG: {str(exc)}")
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

