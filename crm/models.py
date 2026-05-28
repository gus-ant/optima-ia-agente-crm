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
