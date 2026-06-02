"""
crm/models.py
-------------
Modelos relacionais do CRM Próprio Local usando SQLAlchemy 2.0.
Arquitetura Multi-Tenant com chave tenant_id + Row Level Security (RLS) no PostgreSQL.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum as PyEnum
from typing import List, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    JSON,
    Enum,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from crm.database import Base


# ---------------------------------------------------------------------------
# Tabela Global: Tenants (visível sem RLS — gerenciada pelo Master)
# ---------------------------------------------------------------------------

class TenantStatus(str, PyEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    TRIAL = "trial"
    CANCELLED = "cancelled"


class TenantPlan(str, PyEnum):
    BASIC = "basic"        # GPT-3.5, sem RAG
    PRO = "pro"            # GPT-4o, RAG habilitado
    ENTERPRISE = "enterprise"  # GPT-4o + modelos customizados


class Tenant(Base):
    """
    Representa uma empresa/cliente que usa a plataforma Óptima IA.
    Tabela global — NOT protegida por RLS (apenas o Master a acessa).
    """
    __tablename__ = "tenants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(String(63), unique=True, nullable=False, index=True)
    nome: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(
        Enum(TenantStatus, name="tenant_status_enum"),
        default=TenantStatus.TRIAL,
        nullable=False,
    )
    plano: Mapped[str] = mapped_column(
        Enum(TenantPlan, name="tenant_plan_enum"),
        default=TenantPlan.BASIC,
        nullable=False,
    )
    # Configurações individuais por tenant (prompt, temperatura, etc.)
    config: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relacionamentos
    contatos: Mapped[List[Contato]] = relationship(
        "Contato", back_populates="tenant", cascade="all, delete-orphan"
    )
    agent_configs: Mapped[List[AgentConfig]] = relationship(
        "AgentConfig", back_populates="tenant", cascade="all, delete-orphan"
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "slug": self.slug,
            "nome": self.nome,
            "status": self.status,
            "plano": self.plano,
            "config": self.config,
            "criado_em": self.criado_em.isoformat() if self.criado_em else None,
        }


# ---------------------------------------------------------------------------
# Tabela: AgentConfig (configuração do agente por tenant)
# Protegida por RLS
# ---------------------------------------------------------------------------

class AgentConfig(Base):
    """
    Configuração do agente IA para cada tenant.
    Permite personalização do system prompt, LLM e comportamento.
    """
    __tablename__ = "agent_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    nome_agente: Mapped[str] = mapped_column(String(100), default="Lara", nullable=False)
    system_prompt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # LLM override: se None, usa o default do plano
    llm_model: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    temperatura: Mapped[float] = mapped_column(Float, default=0.3, nullable=False)
    # Número WhatsApp do atendente humano para transbordo
    human_agent_whatsapp: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    criado_em: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )

    # Relacionamento
    tenant: Mapped[Tenant] = relationship("Tenant", back_populates="agent_configs")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "nome_agente": self.nome_agente,
            "llm_model": self.llm_model,
            "temperatura": self.temperatura,
            "human_agent_whatsapp": self.human_agent_whatsapp,
            "ativo": self.ativo,
        }


# ---------------------------------------------------------------------------
# Tabela: MCPServer (servidores MCP associados ao tenant)
# ---------------------------------------------------------------------------

class MCPServer(Base):
    """
    Servidores MCP (Model Context Protocol) configurados para o tenant.
    """
    __tablename__ = "mcp_servers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    command: Mapped[str] = mapped_column(String(200), nullable=False)
    args: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    env: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    
    criado_em: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )

    # Relacionamento
    tenant: Mapped[Tenant] = relationship("Tenant")

# ---------------------------------------------------------------------------
# Tabela: KnowledgeDocument (RAG Self-Service)
# Protegida por RLS indiretamente ou na tabela e vectorstore
# ---------------------------------------------------------------------------

class KnowledgeDocument(Base):
    """
    Rastreia os documentos enviados pelo tenant para compor a base de conhecimento RAG.
    """
    __tablename__ = "knowledge_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_type: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="processing", nullable=False)
    criado_em: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    tenant: Mapped[Tenant] = relationship("Tenant")


# ---------------------------------------------------------------------------
# Tabela: TenantMCPServer (Integração Dinâmica de Ferramentas)
# Protegida por RLS
# ---------------------------------------------------------------------------

class TenantMCPServer(Base):
    """
    Configurações de servidores MCP conectados por tenant.
    Permite descobrir dinamicamente tools externas (ERPs, agendas, CRMs).
    """
    __tablename__ = "tenant_mcp_servers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    transport_type: Mapped[str] = mapped_column(String(50), default="stdio", nullable=False) # stdio ou sse
    url_or_command: Mapped[str] = mapped_column(String(255), nullable=False)
    env_config: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    criado_em: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    tenant: Mapped[Tenant] = relationship("Tenant")


# ---------------------------------------------------------------------------
# Tabela: Contatos (protegida por RLS — filtra por tenant_id)
# ---------------------------------------------------------------------------

class Contato(Base):
    """
    Representa o contato do lead/cliente qualificado via WhatsApp.
    Multi-tenant: cada registro pertence a um tenant via tenant_id.
    """
    __tablename__ = "contatos"
    __table_args__ = (
        # Garante que whatsapp_id é único dentro do tenant
        UniqueConstraint("tenant_id", "whatsapp_id", name="uq_contatos_tenant_whatsapp"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    whatsapp_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    nome: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    data_criacao: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )

    # Relacionamentos
    tenant: Mapped[Tenant] = relationship("Tenant", back_populates="contatos")
    negocios: Mapped[List[Negocio]] = relationship(
        "Negocio", back_populates="contato", cascade="all, delete-orphan"
    )
    atividades: Mapped[List[Atividade]] = relationship(
        "Atividade", back_populates="contato", cascade="all, delete-orphan"
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "whatsapp_id": self.whatsapp_id,
            "nome": self.nome,
            "data_criacao": self.data_criacao.isoformat() if self.data_criacao else None,
        }


# ---------------------------------------------------------------------------
# Tabela: Negocios (protegida por RLS indiretamente via contato.tenant_id)
# ---------------------------------------------------------------------------

class Negocio(Base):
    """
    Representa um negócio (Deal/Oportunidade) vinculado a um contato.
    Herda isolamento multi-tenant via JOIN com contatos.tenant_id.
    """
    __tablename__ = "negocios"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    contato_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("contatos.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Detalhes extraídos pelo Agente
    tipo_evento: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    data_evento: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # YYYY-MM-DD ou textual
    orcamento_estimado: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Controle de funil: 'NOVO', 'EM_QUALIFICACAO', 'ALINHAMENTO', 'PRONTO_PARA_HUMANO'
    etapa_funil: Mapped[str] = mapped_column(
        String(50), default="NOVO", nullable=False
    )

    # Notas geradas pelo agente (campos não estruturados)
    notas_agente: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relacionamentos
    contato: Mapped[Contato] = relationship("Contato", back_populates="negocios")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "contato_id": self.contato_id,
            "tipo_evento": self.tipo_evento,
            "data_evento": self.data_evento,
            "orcamento_estimado": self.orcamento_estimado,
            "etapa_funil": self.etapa_funil,
            "notas_agente": self.notas_agente,
            "atualizado_em": self.atualizado_em.isoformat() if self.atualizado_em else None,
        }


# ---------------------------------------------------------------------------
# Tabela: Atividades (protegida por RLS indiretamente)
# ---------------------------------------------------------------------------

class Atividade(Base):
    """
    Registra o histórico de interações (mensagens enviadas e recebidas) para auditoria.
    Herda isolamento multi-tenant via JOIN com contatos.tenant_id.
    """
    __tablename__ = "atividades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    contato_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("contatos.id", ondelete="CASCADE"),
        nullable=False,
    )
    direcao: Mapped[str] = mapped_column(String(20), nullable=False)  # 'inbound' ou 'outbound'
    conteudo: Mapped[str] = mapped_column(Text, nullable=False)
    timestamp: Mapped[str] = mapped_column(String(50), nullable=False)  # ISO-8601 string

    # Relacionamento
    contato: Mapped[Contato] = relationship("Contato", back_populates="atividades")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "contato_id": self.contato_id,
            "direcao": self.direcao,
            "conteudo": self.conteudo,
            "timestamp": self.timestamp,
        }


class Agendamento(Base):
    """
    Representa um agendamento de atendimento/consulta.
    
    Regras:
    - Segunda a sexta: 08:00 - 16:30
    - Sábado: 08:00 - 11:00
    - Consulta: 40 minutos
    - Atendimento: 60 minutos
    - Confirmação obrigatória (24h)
    """
    __tablename__ = "agendamentos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    negocio_id: Mapped[int] = mapped_column(
        Integer, 
        ForeignKey("negocios.id", ondelete="CASCADE"), 
        nullable=False
    )
    contato_id: Mapped[int] = mapped_column(
        Integer, 
        ForeignKey("contatos.id", ondelete="CASCADE"), 
        nullable=False
    )
    
    # --- Informações da Consulta ---
    data_agendamento: Mapped[datetime] = mapped_column(
        DateTime, 
        nullable=False,
        index=True  # Índice para buscas rápidas por horário
    )
    duracao_minutos: Mapped[int] = mapped_column(
        Integer, 
        default=60,
        nullable=False
    )  # 40 (consulta) ou 60 (atendimento)
    
    tipo_agendamento: Mapped[str] = mapped_column(
        String(50),
        default="consulta_inicial",
        nullable=False
    )  # 'consulta_inicial', 'visita_local', 'apresentacao_orcamento'
    
    local_atendimento: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True
    )  # Endereço ou 'Online'
    
    observacoes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # --- Status de Confirmação ---
    confirmado: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    data_confirmacao: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # --- Realização ---
    presente: Mapped[bool] = mapped_column(Boolean, default=False)
    data_presenca: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # --- Cancelamento ---
    cancelado_em: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    motivo_cancelamento: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # --- Auditoria ---
    criado_em: Mapped[datetime] = mapped_column(
        DateTime, 
        default=lambda: datetime.now(timezone.utc),
        index=True
    )
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime, 
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
    )
    
    # --- Sincronização com Calendários Externos ---
    external_calendar_id: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True
    )  # ID do evento em Google Calendar, Outlook, etc
    
    # Relacionamentos
    negocio: Mapped[Negocio] = relationship("Negocio")
    contato: Mapped[Contato] = relationship("Contato")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "negocio_id": self.negocio_id,
            "contato_id": self.contato_id,
            "data_agendamento": self.data_agendamento.isoformat() if self.data_agendamento else None,
            "duracao_minutos": self.duracao_minutos,
            "tipo_agendamento": self.tipo_agendamento,
            "local_atendimento": self.local_atendimento,
            "observacoes": self.observacoes,
            "confirmado": self.confirmado,
            "data_confirmacao": self.data_confirmacao.isoformat() if self.data_confirmacao else None,
            "presente": self.presente,
            "data_presenca": self.data_presenca.isoformat() if self.data_presenca else None,
            "cancelado_em": self.cancelado_em.isoformat() if self.cancelado_em else None,
            "motivo_cancelamento": self.motivo_cancelamento,
            "criado_em": self.criado_em.isoformat() if self.criado_em else None,
            "atualizado_em": self.atualizado_em.isoformat() if self.atualizado_em else None,
            "external_calendar_id": self.external_calendar_id,
        }
