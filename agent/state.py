"""
agent/state.py
--------------
Define o estado compartilhado do grafo LangGraph para o agente Lara.
Cada campo representa um slot de qualificação do lead ou metadado de controle.
"""

from __future__ import annotations

from typing import Annotated, List, Optional
from typing_extensions import TypedDict

from langgraph.graph.message import add_messages


# ---------------------------------------------------------------------------
# Sub-schemas (espelham o JSON de extração do plano de implementação)
# ---------------------------------------------------------------------------

class LeadData(TypedDict, total=False):
    nome: Optional[str]
    whatsapp: str
    instagram: Optional[str]
    cidade: Optional[str]
    canal_origem: Optional[str]  # instagram|indicacao|google|trafego|evento|outro


class EventoData(TypedDict, total=False):
    tipo: Optional[str]          # casamento|aniversario|cha|corporativo|outro
    data: Optional[str]          # YYYY-MM-DD
    local_nome: Optional[str]
    local_cidade: Optional[str]
    num_convidados: Optional[int]
    espaco_status: Optional[str]  # fechado|aberto
    tem_mobilia: Optional[bool]
    estilo: Optional[str]
    paleta_cores: Optional[str]
    tipo_flores: Optional[str]    # vivas|permanentes|mistas
    referencias: List[str]


class ComercialData(TypedDict, total=False):
    faixa_investimento: Optional[str]
    urgencia: Optional[str]       # alta|media|baixa
    avaliou_concorrencia: Optional[bool]


# ---------------------------------------------------------------------------
# Estado principal do grafo
# ---------------------------------------------------------------------------

class AgentState(TypedDict):
    # Histórico de mensagens (LangGraph gerencia merge automático via add_messages)
    messages: Annotated[list, add_messages]

    # Identificação da sessão
    session_id: str          # phone number normalizado (ex: "5511999998888")
    crm_contact_id: Optional[str]   # ID do contato no CRM antigo (retrocompatibilidade)
    contato_id: Optional[int]       # ID do contato no CRM próprio local
    negocio_id: Optional[int]       # ID do negócio no CRM próprio local

    # Dados extraídos pelo LLM

    lead: LeadData
    evento: EventoData
    comercial: ComercialData

    # Controle de fluxo
    pipeline_stage: str      # novo_lead|em_qualificacao|dados_coletados|aguardando_fotos|pronto_orcamento
    pronto_transbordo: bool  # True quando todos os dados obrigatórios foram coletados
    follow_up_count: int     # quantas mensagens de follow-up já foram enviadas
    awaiting_media: bool     # True quando o agente pediu fotos/referências
    error_message: Optional[str]  # erro capturado para logging
