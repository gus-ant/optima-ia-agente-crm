"""
agent/extraction.py
-------------------
Extração estruturada de dados do lead usando LangChain with_structured_output.
Usado como fallback quando o bloco <extraction> não está presente na resposta do LLM.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from agent.prompts import EXTRACTION_INSTRUCTION

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pydantic schemas para structured output
# ---------------------------------------------------------------------------

class LeadExtraction(BaseModel):
    nome: Optional[str] = Field(None, description="Nome completo do cliente")
    whatsapp: str = Field(..., description="Número WhatsApp normalizado")
    instagram: Optional[str] = Field(None, description="@ do Instagram se mencionado")
    cidade: Optional[str] = Field(None, description="Cidade do cliente")
    canal_origem: Optional[str] = Field(
        None,
        description="Canal: instagram|indicacao|google|trafego|evento|outro",
    )


class EventoExtraction(BaseModel):
    tipo: Optional[str] = Field(
        None, description="casamento|aniversario|cha|corporativo|outro"
    )
    data: Optional[str] = Field(None, description="Data no formato YYYY-MM-DD")
    local_nome: Optional[str] = Field(None, description="Nome do espaço do evento")
    local_cidade: Optional[str] = Field(None, description="Cidade do evento")
    num_convidados: Optional[int] = Field(None, description="Número aproximado de convidados")
    espaco_status: Optional[str] = Field(None, description="fechado|aberto")
    tem_mobilia: Optional[bool] = Field(None, description="O espaço tem mobília própria?")
    estilo: Optional[str] = Field(None, description="Estilo de decoração desejado")
    paleta_cores: Optional[str] = Field(None, description="Paleta de cores preferida")
    tipo_flores: Optional[str] = Field(None, description="vivas|permanentes|mistas")
    referencias: List[str] = Field(
        default_factory=list, description="URLs de referências visuais"
    )


class ComercialExtraction(BaseModel):
    faixa_investimento: Optional[str] = Field(
        None, description="Faixa de valor estimada pelo cliente"
    )
    urgencia: Optional[str] = Field(None, description="alta|media|baixa")
    avaliou_concorrencia: Optional[bool] = Field(
        None, description="Cliente já consultou outros fornecedores?"
    )


class FullLeadExtraction(BaseModel):
    lead: LeadExtraction
    evento: EventoExtraction
    comercial: ComercialExtraction
    pipeline_stage: str = Field(
        default="em_qualificacao",
        description=(
            "novo_lead|em_qualificacao|dados_coletados|"
            "aguardando_fotos|pronto_orcamento"
        ),
    )
    pronto_transbordo: bool = Field(
        default=False,
        description="True quando todos os dados obrigatórios foram coletados",
    )


# ---------------------------------------------------------------------------
# Extractor
# ---------------------------------------------------------------------------

def extract_lead_data(conversation_history: list, whatsapp: str) -> FullLeadExtraction:
    """
    Executa extração estruturada via LLM com structured output (Pydantic).

    Args:
        conversation_history: Lista de mensagens LangChain (Human/AI).
        whatsapp: Número do cliente para garantir campo obrigatório.

    Returns:
        FullLeadExtraction com todos os campos preenchidos ou None.
    """
    import os

    model = os.getenv("LLM_MODEL", "gpt-4o")
    llm = ChatOpenAI(model=model, temperature=0).with_structured_output(FullLeadExtraction)

    messages = [
        SystemMessage(content=EXTRACTION_INSTRUCTION),
        *conversation_history,
        HumanMessage(
            content=f"O número WhatsApp do cliente é {whatsapp}. "
            "Extraia todos os dados coletados até agora."
        ),
    ]

    try:
        result: FullLeadExtraction = llm.invoke(messages)
        # Garante que o whatsapp não seja perdido
        result.lead.whatsapp = whatsapp
        return result
    except Exception as exc:
        logger.error("Extraction failed: %s", exc)
        # Retorna extração mínima com whatsapp
        return FullLeadExtraction(
            lead=LeadExtraction(whatsapp=whatsapp),
            evento=EventoExtraction(),
            comercial=ComercialExtraction(),
        )
