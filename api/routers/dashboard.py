"""
api/routers/dashboard.py
------------------------
Router para fornecer dados do CRM SQLite para o painel de controle (Dashboard).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select

from crm.database import get_tenant_db_session
from crm.tenant import get_current_tenant_id
from crm.models import Atividade, Contato, Negocio, Agendamento

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


class StageUpdateSchema(BaseModel):
    stage: str


@router.get("/stats")
async def get_dashboard_stats() -> Dict[str, Any]:
    """Retorna estatísticas gerais consolidando leads, estágios do funil e agendamentos."""
    try:
        tenant_id = get_current_tenant_id()
        async with get_tenant_db_session() as session:
            # Contagem total de contatos
            c_stmt = select(func.count(Contato.id))
            if tenant_id is not None:
                c_stmt = c_stmt.where(Contato.tenant_id == tenant_id)
            c_res = await session.execute(c_stmt)
            total_contacts = c_res.scalar() or 0

            # Contagem total de negócios
            n_stmt = select(func.count(Negocio.id)).join(Contato, Negocio.contato_id == Contato.id)
            if tenant_id is not None:
                n_stmt = n_stmt.where(Contato.tenant_id == tenant_id)
            n_res = await session.execute(n_stmt)
            total_deals = n_res.scalar() or 0

            # Contagem de agendamentos
            a_stmt = select(func.count(Agendamento.id)).join(Contato, Agendamento.contato_id == Contato.id)
            if tenant_id is not None:
                a_stmt = a_stmt.where(Contato.tenant_id == tenant_id)
            a_res = await session.execute(a_stmt)
            total_appointments = a_res.scalar() or 0

            # Contagem por estágio de negócios
            stage_stmt = select(Negocio.etapa_funil, func.count(Negocio.id)).join(Contato, Negocio.contato_id == Contato.id).group_by(Negocio.etapa_funil)
            if tenant_id is not None:
                stage_stmt = stage_stmt.where(Contato.tenant_id == tenant_id)
            stage_res = await session.execute(stage_stmt)
            
            stages = {
                "NOVO": 0,
                "EM_QUALIFICACAO": 0,
                "ALINHAMENTO": 0,
                "PRONTO_PARA_HUMANO": 0
            }
            
            for row in stage_res.all():
                stage_name = row[0]
                stage_count = row[1]
                if stage_name in stages:
                    stages[stage_name] = stage_count

            return {
                "total_contacts": total_contacts,
                "total_deals": total_deals,
                "total_appointments": total_appointments,
                "stages": stages
            }
    except Exception as exc:
        logger.error("Erro ao carregar estatísticas do dashboard: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/leads")
async def get_dashboard_leads() -> List[Dict[str, Any]]:
    """Retorna lista de leads contendo dados do Contato e Negócio vinculados."""
    try:
        tenant_id = get_current_tenant_id()
        async with get_tenant_db_session() as session:
            stmt = select(Contato, Negocio).outerjoin(Negocio, Contato.id == Negocio.contato_id)
            if tenant_id is not None:
                stmt = stmt.where(Contato.tenant_id == tenant_id)
            stmt = stmt.order_by(Contato.data_criacao.desc())
            result = await session.execute(stmt)
            
            leads = []
            for row in result.all():
                contato = row[0]
                negocio = row[1]
                leads.append({
                    "contact": contato.to_dict(),
                    "deal": negocio.to_dict() if negocio else None
                })
            return leads
    except Exception as exc:
        logger.error("Erro ao carregar lista de leads do dashboard: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/leads/{contact_id}/chat")
async def get_lead_chat_history(contact_id: int) -> List[Dict[str, Any]]:
    """Retorna o histórico de atividades e mensagens trocadas com o lead específico."""
    try:
        tenant_id = get_current_tenant_id()
        async with get_tenant_db_session() as session:
            # Verifica se o contato existe
            c_stmt = select(Contato).where(Contato.id == contact_id)
            if tenant_id is not None:
                c_stmt = c_stmt.where(Contato.tenant_id == tenant_id)
            c_res = await session.execute(c_stmt)
            if not c_res.scalar_one_or_none():
                raise HTTPException(status_code=404, detail="Contato não encontrado")

            stmt = select(Atividade).join(Contato, Atividade.contato_id == Contato.id).where(Atividade.contato_id == contact_id)
            if tenant_id is not None:
                stmt = stmt.where(Contato.tenant_id == tenant_id)
            stmt = stmt.order_by(Atividade.timestamp.asc())
            result = await session.execute(stmt)
            activities = [act.to_dict() for act in result.scalars().all()]
            return activities
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Erro ao obter histórico do chat para o contato %d: %s", contact_id, exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/appointments")
async def get_dashboard_appointments() -> List[Dict[str, Any]]:
    """Retorna lista de todos os agendamentos realizados."""
    try:
        tenant_id = get_current_tenant_id()
        async with get_tenant_db_session() as session:
            stmt = select(Agendamento, Contato).join(Contato, Agendamento.contato_id == Contato.id)
            if tenant_id is not None:
                stmt = stmt.where(Contato.tenant_id == tenant_id)
            stmt = stmt.order_by(Agendamento.data_agendamento.asc())
            result = await session.execute(stmt)
            
            appointments = []
            for row in result.all():
                agendamento = row[0]
                contato = row[1]
                appointments.append({
                    "appointment": agendamento.to_dict(),
                    "contact": contato.to_dict()
                })
            return appointments
    except Exception as exc:
        logger.error("Erro ao buscar agendamentos do dashboard: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@router.patch("/leads/{contact_id}/stage")
async def update_lead_stage(contact_id: int, schema: StageUpdateSchema) -> Dict[str, Any]:
    """Permite alterar manualmente o estágio do negócio de um lead."""
    try:
        tenant_id = get_current_tenant_id()
        async with get_tenant_db_session() as session:
            stmt = select(Negocio).join(Contato, Negocio.contato_id == Contato.id).where(Negocio.contato_id == contact_id)
            if tenant_id is not None:
                stmt = stmt.where(Contato.tenant_id == tenant_id)
            result = await session.execute(stmt)
            negocio = result.scalar_one_or_none()
            if not negocio:
                raise HTTPException(status_code=404, detail="Negócio associado não encontrado")

            etapa = schema.stage.upper()
            if etapa not in ("NOVO", "EM_QUALIFICACAO", "ALINHAMENTO", "PRONTO_PARA_HUMANO"):
                raise HTTPException(status_code=400, detail="Etapa de funil inválida")

            negocio.etapa_funil = etapa
            negocio.atualizado_em = datetime.now(timezone.utc)
            await session.commit()
            
            return {
                "status": "success",
                "contact_id": contact_id,
                "new_stage": etapa
            }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Erro ao atualizar estágio do lead %d: %s", contact_id, exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))
