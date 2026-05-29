"""
crm/models.py
-------------
Modelos relacionais do CRM Próprio Local usando SQLAlchemy 2.0.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from crm.database import Base


class Contato(Base):
    """
    Representa o contato do lead/cliente qualificado via WhatsApp.
    """
    __tablename__ = "contatos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    whatsapp_id: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    nome: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    data_criacao: Mapped[datetime] = mapped_column(
        DateTime, 
        default=lambda: datetime.now(timezone.utc)
    )

    # Relacionamentos
    negocios: Mapped[List[Negocio]] = relationship(
        "Negocio", 
        back_populates="contato", 
        cascade="all, delete-orphan"
    )
    atividades: Mapped[List[Atividade]] = relationship(
        "Atividade", 
        back_populates="contato", 
        cascade="all, delete-orphan"
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "whatsapp_id": self.whatsapp_id,
            "nome": self.nome,
            "data_criacao": self.data_criacao.isoformat() if self.data_criacao else None,
        }


class Negocio(Base):
    """
    Representa um negócio (Deal/Oportunidade) vinculado a um contato.
    """
    __tablename__ = "negocios"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    contato_id: Mapped[int] = mapped_column(
        Integer, 
        ForeignKey("contatos.id", ondelete="CASCADE"), 
        nullable=False
    )
    
    # Detalhes extraídos pelo Agente
    tipo_evento: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    data_evento: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # YYYY-MM-DD ou textual
    orcamento_estimado: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    # Controle de funil: 'NOVO', 'EM_QUALIFICACAO', 'ALINHAMENTO', 'PRONTO_PARA_HUMANO'
    etapa_funil: Mapped[str] = mapped_column(
        String(50), 
        default="NOVO", 
        nullable=False
    )
    
    # Campo para guardar observações gerais extraídas (ex: estilo, flores, local, etc)
    notas_agente: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime, 
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
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


class Atividade(Base):
    """
    Registra o histórico de interações (mensagens enviadas e recebidas) para auditoria.
    """
    __tablename__ = "atividades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    contato_id: Mapped[int] = mapped_column(
        Integer, 
        ForeignKey("contatos.id", ondelete="CASCADE"), 
        nullable=False
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
