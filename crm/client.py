"""
crm/client.py
-------------
Cliente CRM Próprio Local integrado ao banco de dados relacional.
Multi-Tenant: usa get_tenant_db_session() que injeta SET LOCAL para ativar o RLS.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from crm.database import get_tenant_db_session
from crm.models import Atividade, Contato, Negocio

logger = logging.getLogger(__name__)

# Mapeamento de estágios do LangGraph para as etapas locais do banco de dados
STAGE_MAP = {
    "novo_lead": "NOVO",
    "em_qualificacao": "EM_QUALIFICACAO",
    "dados_coletados": "ALINHAMENTO",
    "aguardando_fotos": "ALINHAMENTO",
    "pronto_orcamento": "PRONTO_PARA_HUMANO",
}


class LocalCRMClient:
    """
    Cliente para operações no CRM local usando sessões assíncronas do SQLAlchemy.
    Multi-Tenant: injeta tenant_id em todas as operações via get_tenant_db_session().
    """

    def __init__(self, tenant_id: Optional[int] = None):
        """
        Args:
            tenant_id: ID do tenant para isolar as operações via RLS.
                       Se None, tenta usar o ContextVar current_tenant_id.
        """
        self._tenant_id = tenant_id

    async def get_or_create_contato(
        self, whatsapp_id: str, nome: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Busca ou cria um contato com o número de WhatsApp fornecido.
        O tenant_id é obrigatório para criar um novo contato multi-tenant.
        """
        try:
            async with get_tenant_db_session(self._tenant_id) as session:
                stmt = select(Contato).where(
                    Contato.whatsapp_id == whatsapp_id,
                    Contato.tenant_id == self._tenant_id,
                )
                result = await session.execute(stmt)
                contato = result.scalar_one_or_none()

                if contato is None:
                    logger.info("Contato não encontrado para whatsapp_id=%s. Criando...", whatsapp_id)
                    if not self._tenant_id:
                        raise ValueError("tenant_id é obrigatório para criar contato")
                    contato = Contato(
                        whatsapp_id=whatsapp_id,
                        nome=nome,
                        tenant_id=self._tenant_id,
                    )
                    session.add(contato)
                    await session.flush()  # Garante geração do ID do contato
                    
                    # Cria automaticamente um negócio vinculado para este novo contato
                    negocio = Negocio(
                        contato_id=contato.id,
                        etapa_funil="NOVO"
                    )
                    session.add(negocio)
                    await session.flush()

                    logger.info("Contato criado com ID %d e Negócio com ID %d", contato.id, negocio.id)
                    
                    # Retorna os IDs gerados
                    return {
                        "contact_id": str(contato.id),
                        "deal_id": str(negocio.id),
                        "crm_url": f"http://localhost:8000/crm/contacts/{contato.id}",
                        "is_new": True,
                    }
                else:
                    # Busca negócio vinculado se já existir
                    stmt_negocio = select(Negocio).where(Negocio.contato_id == contato.id)
                    res_neg = await session.execute(stmt_negocio)
                    negocio = res_neg.scalar_one_or_none()
                    deal_id = negocio.id if negocio else None

                    logger.info("Contato recuperado do DB: ID %d", contato.id)
                    return {
                        "contact_id": str(contato.id),
                        "deal_id": str(deal_id) if deal_id else None,
                        "crm_url": f"http://localhost:8000/crm/contacts/{contato.id}",
                        "is_new": False,
                    }

        except Exception as exc:
            logger.error("Erro ao obter/criar contato no banco local: %s", exc, exc_info=True)
            # Fallback temporário usando o número de whatsapp como ID fake
            # para evitar a interrupção do bot no WhatsApp
            return {
                "contact_id": f"fallback_{whatsapp_id}",
                "deal_id": f"fallback_deal_{whatsapp_id}",
                "crm_url": "#fallback-database-offline",
                "is_new": True,
            }

    async def create_negocio(self, contato_id: int) -> Dict[str, Any]:
        """
        Cria um novo negócio (Deal) para o contato informado.
        """
        try:
            async with get_tenant_db_session(self._tenant_id) as session:
                negocio = Negocio(
                    contato_id=contato_id,
                    etapa_funil="NOVO"
                )
                session.add(negocio)
                await session.flush()
                logger.info("Negócio criado para contato_id=%d com ID %d", contato_id, negocio.id)
                return {"deal_id": str(negocio.id)}
        except Exception as exc:
            logger.error("Erro ao criar negócio local: %s", exc, exc_info=True)
            return {"deal_id": f"fallback_deal_{contato_id}"}

    async def update_dados_negocio(
        self, negocio_id: int, **kwargs
    ) -> Dict[str, Any]:
        """
        Atualiza dinamicamente os dados de qualificação do negócio (Deal).
        Pode atualizar: tipo_evento, data_evento, orcamento_estimado, notas_agente.
        """
        try:
            async with get_tenant_db_session(self._tenant_id) as session:
                stmt = select(Negocio).where(Negocio.id == negocio_id)
                result = await session.execute(stmt)
                negocio = result.scalar_one_or_none()

                if not negocio:
                    logger.warning("Negócio com ID %d não foi encontrado para atualização", negocio_id)
                    return {"status": "not_found"}

                # Atualização dinâmica dos campos
                for field in ("tipo_evento", "data_evento", "orcamento_estimado", "notas_agente"):
                    if field in kwargs and kwargs[field] is not None:
                        setattr(negocio, field, kwargs[field])

                negocio.atualizado_em = datetime.now(timezone.utc)
                logger.info("Dados do negócio %d atualizados com sucesso", negocio_id)
                return {"status": "success", "negocio": negocio.to_dict()}
        except Exception as exc:
            logger.error("Erro ao atualizar negócio %d: %s", negocio_id, exc, exc_info=True)
            return {"status": "error", "message": str(exc)}

    async def update_contact_data(self, contact_id: str, fields: dict) -> dict:
        """
        Mapeia a extração do agente em colunas locais e atualiza o contato e negócio associado.
        """
        if contact_id.startswith("fallback_"):
            return {"status": "fallback_success"}

        lead = fields.get("lead", {})
        evento = fields.get("evento", {})
        comercial = fields.get("comercial", {})
        
        nome_lead = lead.get("nome")
        
        # Mapeamento do orçamento estimado
        faixa_invest = comercial.get("faixa_investimento")
        orcamento = None
        if faixa_invest:
            try:
                # Limpa a string de moeda para Real/Dólar
                cleaned = (
                    faixa_invest.replace("R$", "")
                    .replace("$", "")
                    .replace(" ", "")
                    .replace(".", "")
                )
                if "," in cleaned:
                    cleaned = cleaned.replace(",", ".")
                import re
                nums = re.findall(r"\d+\.?\d*", cleaned)
                if nums:
                    orcamento = float(nums[0])
            except Exception:
                pass


        # Compila as notas do agente agregando dados detalhados não estruturados
        notas_lista = []
        if lead.get("instagram"):
            notas_lista.append(f"Instagram: {lead['instagram']}")
        if lead.get("cidade"):
            notas_lista.append(f"Cidade do Cliente: {lead['cidade']}")
        if lead.get("canal_origem"):
            notas_lista.append(f"Origem: {lead['canal_origem']}")
            
        if evento:
            if evento.get("local_nome"):
                notas_lista.append(f"Local do Evento: {evento['local_nome']}")
            if evento.get("local_cidade"):
                notas_lista.append(f"Cidade do Evento: {evento['local_cidade']}")
            if evento.get("num_convidados"):
                notas_lista.append(f"Convidados: {evento['num_convidados']}")
            if evento.get("espaco_status"):
                notas_lista.append(f"Espaço: {evento['espaco_status']}")
            if evento.get("tem_mobilia") is not None:
                notas_lista.append(f"Tem mobília: {'Sim' if evento['tem_mobilia'] else 'Não'}")
            if evento.get("estilo"):
                notas_lista.append(f"Estilo: {evento['estilo']}")
            if evento.get("paleta_cores"):
                notas_lista.append(f"Cores: {evento['paleta_cores']}")
            if evento.get("tipo_flores"):
                notas_lista.append(f"Flores: {evento['tipo_flores']}")
            if evento.get("referencias"):
                notas_lista.append(f"Referências: {', '.join(evento['referencias'])}")
                
        if comercial:
            if comercial.get("urgencia"):
                notas_lista.append(f"Urgência: {comercial['urgencia']}")
            if comercial.get("avaliou_concorrencia") is not None:
                notas_lista.append(f"Avaliou concorrência: {'Sim' if comercial['avaliou_concorrencia'] else 'Não'}")

        notas_agente = "\n".join(notas_lista)

        try:
            # Atualiza nome do Contato e localiza o negócio vinculado
            async with get_tenant_db_session(self._tenant_id) as session:
                c_id = int(contact_id)
                # Atualiza nome no Contato
                if nome_lead:
                    stmt_c = select(Contato).where(Contato.id == c_id)
                    res_c = await session.execute(stmt_c)
                    contato = res_c.scalar_one_or_none()
                    if contato:
                        contato.nome = nome_lead

                # Busca Negócio do contato
                stmt_n = select(Negocio).where(Negocio.contato_id == c_id)
                res_n = await session.execute(stmt_n)
                negocio = res_n.scalar_one_or_none()
                
                if negocio:
                    negocio_id = negocio.id
                else:
                    novo_neg = Negocio(contato_id=c_id, etapa_funil="EM_QUALIFICACAO")
                    session.add(novo_neg)
                    await session.flush()
                    negocio_id = novo_neg.id
            
            # Chama a atualização do negócio
            return await self.update_dados_negocio(
                negocio_id=negocio_id,
                tipo_evento=evento.get("tipo"),
                data_evento=evento.get("data"),
                orcamento_estimado=orcamento,
                notas_agente=notas_agente,
            )
        except Exception as exc:
            logger.error("Falha ao atualizar dados do lead no banco: %s", exc, exc_info=True)
            return {"status": "error", "message": str(exc)}

    async def update_etapa_funil(self, negocio_id: int, nova_etapa: str) -> Dict[str, Any]:
        """
        Atualiza o estágio do negócio no funil de vendas.
        """
        # Normaliza a etapa para os valores aceitos no banco local
        etapa_db = STAGE_MAP.get(nova_etapa, nova_etapa)
        if etapa_db not in ("NOVO", "EM_QUALIFICACAO", "ALINHAMENTO", "PRONTO_PARA_HUMANO"):
            etapa_db = "EM_QUALIFICACAO"

        try:
            async with get_tenant_db_session(self._tenant_id) as session:
                stmt = select(Negocio).where(Negocio.id == negocio_id)
                result = await session.execute(stmt)
                negocio = result.scalar_one_or_none()

                if not negocio:
                    logger.warning("Negócio com ID %d não encontrado para mudar etapa", negocio_id)
                    return {"status": "not_found"}

                negocio.etapa_funil = etapa_db
                negocio.atualizado_em = datetime.now(timezone.utc)
                logger.info("Negócio %d avançou para etapa %s", negocio_id, etapa_db)
                return {"status": "success", "etapa_funil": etapa_db}
        except Exception as exc:
            logger.error("Erro ao mudar etapa do negócio %d: %s", negocio_id, exc, exc_info=True)
            return {"status": "error", "message": str(exc)}

    async def log_activity(
        self, contact_id: int, direction: str, content: str, timestamp: str
    ) -> Dict[str, Any]:
        """
        Registra histórico da conversa diretamente no banco de dados local.
        """
        try:
            async with get_tenant_db_session(self._tenant_id) as session:
                atividade = Atividade(
                    contato_id=contact_id,
                    direcao=direction,
                    conteudo=content,
                    timestamp=timestamp,
                )
                session.add(atividade)
                logger.info("Atividade (%s) registrada para contato %d", direction, contact_id)
                return {"status": "success"}
        except Exception as exc:
            logger.error("Erro ao registrar atividade do contato %d: %s", contact_id, exc, exc_info=True)
            return {"status": "error", "message": str(exc)}


# ---------------------------------------------------------------------------
# Factory do cliente (Multi-Tenant)
# ---------------------------------------------------------------------------

def CRMClient(tenant_id: Optional[int] = None) -> LocalCRMClient:
    """
    Retorna a instância do cliente CRM local próprio.
    
    Args:
        tenant_id: ID do tenant para isolar as operações via RLS.
                   Se omitido, usa o ContextVar current_tenant_id do middleware.
    """
    return LocalCRMClient(tenant_id=tenant_id)
