"""
tasks/reminders.py
------------------
Lembretes automáticos via APScheduler.

Envia:
- 24h antes: Confirmar presença
- 30min antes: Lembrete final (pronto para sair?)

Setup:
1. APScheduler inicia no lifespan da API (api/main.py)
2. Verifica a cada 5 minutos se há agendamentos próximos
3. Envia via WhatsApp
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Templates de mensagens
TEMPLATES = {
    "lembrete_24h": """
📢 *Lembrete — Confirmação de Presença* 📢

Olá {nome}! 👋

Recebi que você tem agendamento conosco:

📅 {data} às {hora}
📍 {local}

Confirma presença? 
[✅ Sim, confirmo] [❌ Preciso reagendar]
    """,
    "lembrete_30min": """
🕐 *Faltam 30 minutos!* 🕐

Oi {nome}! Tudo bem?

Seu agendamento começa em 30 minutos:
📍 {local}

Está no caminho? 
[✅ Já estou saindo] [❌ Vou atrasar]
    """,
    "confirmacao_recebida": """
✅ *Presença Confirmada!*

Ótimo {nome}! Sua confirmação foi registrada.

Até breve! 👋
📅 {data} às {hora}
📍 {local}
    """,
}


class ReminderScheduler:
    """Gerencia lembretes automáticos com APScheduler."""

    def __init__(self, scheduler=None):
        """
        Inicializa scheduler de lembretes.

        Args:
            scheduler: Instância de AsyncIOScheduler (se None, cria uma)
        """
        if scheduler is None:
            from apscheduler.schedulers.asyncio import AsyncIOScheduler

            scheduler = AsyncIOScheduler()

        self.scheduler = scheduler
        self.is_running = False

    async def start(self):
        """Inicia scheduler de lembretes."""
        if self.is_running:
            logger.warning("Reminder scheduler already running")
            return

        # Job que verifica a cada 5 minutos
        self.scheduler.add_job(
            self._check_and_send_reminders,
            "interval",
            minutes=5,
            id="check_reminders_job",
            replace_existing=True,
        )

        self.scheduler.start()
        self.is_running = True
        logger.info("Reminder scheduler started ✓")

    async def stop(self):
        """Para scheduler."""
        if self.scheduler.running:
            self.scheduler.shutdown()
            self.is_running = False
            logger.info("Reminder scheduler stopped")

    async def _check_and_send_reminders(self):
        """Job principal: verifica agendamentos próximos e envia lembretes."""
        from crm.database import get_db_session
        from crm.models import Agendamento
        from crm.agenda_rules import (
            deve_enviar_lembrete_24h,
            deve_enviar_lembrete_30min,
        )

        try:
            async with get_db_session() as session:
                # Buscar agendamentos confirmados nos próximos 24h+
                agora = datetime.now()
                limites = (
                    agora - timedelta(minutes=15),  # Margem de segurança
                    agora + timedelta(hours=24, minutes=30),
                )

                stmt = select(Agendamento).filter(
                    and_(
                        Agendamento.data_agendamento >= limites[0],
                        Agendamento.data_agendamento <= limites[1],
                        Agendamento.confirmado.is_(True),
                        Agendamento.cancelado_em.is_(None),
                    )
                )

                result = await session.execute(stmt)
                agendamentos = result.scalars().all()

                for agd in agendamentos:
                    await self._processar_agendamento(session, agd)

        except Exception as exc:
            logger.error("Erro ao verificar lembretes: %s", exc, exc_info=True)

    async def _processar_agendamento(
        self, session: AsyncSession, agendamento
    ):
        """Processa um agendamento e envia lembretes se necessário."""
        from crm.agenda_rules import (
            deve_enviar_lembrete_24h,
            deve_enviar_lembrete_30min,
        )

        try:
            # Verificar lembrete de 24h
            if deve_enviar_lembrete_24h(agendamento.data_agendamento):
                await self._enviar_lembrete(
                    agendamento, "lembrete_24h"
                )

            # Verificar lembrete de 30min
            elif deve_enviar_lembrete_30min(agendamento.data_agendamento):
                await self._enviar_lembrete(agendamento, "lembrete_30min")

        except Exception as exc:
            logger.error(
                "Erro ao processar agendamento %s: %s",
                agendamento.id,
                exc,
                exc_info=True,
            )

    async def _enviar_lembrete(self, agendamento, tipo_lembrete: str):
        """Envia lembrete via WhatsApp."""
        try:
            from whatsapp.provider_config import get_whatsapp_client

            # Verificar se já foi enviado
            if await self._ja_enviado(agendamento.id, tipo_lembrete):
                logger.debug(
                    f"Lembrete {tipo_lembrete} já enviado para agendamento {agendamento.id}"
                )
                return

            # Montar mensagem
            template = TEMPLATES.get(tipo_lembrete, "")
            mensagem = template.format(
                nome=agendamento.contato.nome or "Cliente",
                data=agendamento.data_agendamento.strftime("%d/%m/%Y"),
                hora=agendamento.data_agendamento.strftime("%H:%M"),
                local=agendamento.local_atendimento or "Local a confirmar",
            )

            # Enviar WhatsApp
            client = get_whatsapp_client()
            resultado = await client.send_message(
                to=agendamento.contato.whatsapp_id,
                text=mensagem,
            )

            if resultado.get("status") == "sent":
                logger.info(
                    f"Lembrete {tipo_lembrete} enviado para agendamento {agendamento.id}"
                )
                # Registrar envio
                await self._marcar_como_enviado(
                    agendamento.id, tipo_lembrete
                )
            else:
                logger.warning(
                    f"Falha ao enviar lembrete {tipo_lembrete} para agendamento {agendamento.id}"
                )

        except Exception as exc:
            logger.error(
                f"Erro ao enviar lembrete {tipo_lembrete}: %s",
                exc,
                exc_info=True,
            )

    async def _ja_enviado(self, agendamento_id: int, tipo: str) -> bool:
        """Verifica se lembrete já foi enviado (anti-spam)."""
        # TODO: Implementar com Redis ou campo na tabela
        # Por enquanto, retorna False (sempre envia)
        return False

    async def _marcar_como_enviado(self, agendamento_id: int, tipo: str):
        """Marca lembrete como enviado."""
        # TODO: Implementar com Redis ttl ou campo na tabela
        pass


# Singleton global
_reminder_scheduler: Optional[ReminderScheduler] = None


def get_reminder_scheduler() -> ReminderScheduler:
    """Retorna instância singleton do scheduler."""
    global _reminder_scheduler
    if _reminder_scheduler is None:
        _reminder_scheduler = ReminderScheduler()
    return _reminder_scheduler


async def init_reminders(scheduler=None):
    """Inicializa scheduler de lembretes (chamado no lifespan)."""
    rm = get_reminder_scheduler()
    if scheduler:
        rm.scheduler = scheduler
    await rm.start()


async def shutdown_reminders():
    """Encerra scheduler (chamado no shutdown)."""
    rm = get_reminder_scheduler()
    await rm.stop()
