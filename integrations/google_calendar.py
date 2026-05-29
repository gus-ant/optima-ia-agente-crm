"""
integrations/google_calendar.py
--------------------------------
Sincronização de agendamentos com Google Calendar.

Fluxo:
1. Criar agendamento local
   ↓
2. Sincronizar com Google Calendar (novo evento)
   ↓
3. Cliente confirma (local ou Calendar)
   ↓
4. Se confirmou em Calendar → sincronizar status (local)

Setup:
1. Baixar credenciais de service account em Google Cloud Console
2. Salvar em `google-credentials.json`
3. Adicionar credencial path no .env: GOOGLE_CREDENTIALS_PATH
4. Compartilhar calendário com service account
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta
from typing import Optional

from google.auth.service_account import Credentials
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/calendar"]


class GoogleCalendarSync:
    """Cliente para sincronizar agendamentos com Google Calendar."""

    def __init__(self, credentials_path: Optional[str] = None):
        """
        Inicializa client Google Calendar.

        Args:
            credentials_path: Caminho para google-credentials.json.
                             Se None, usa GOOGLE_CREDENTIALS_PATH do .env
        """
        self.creds_path = (
            credentials_path or os.getenv("GOOGLE_CREDENTIALS_PATH", "")
        )

        if not self.creds_path or not os.path.exists(self.creds_path):
            logger.warning(
                "Google Calendar credentials not found. Sync disabled. "
                "Set GOOGLE_CREDENTIALS_PATH in .env"
            )
            self.service = None
            return

        try:
            creds = Credentials.from_service_account_file(
                self.creds_path, scopes=SCOPES
            )
            self.service = build("calendar", "v3", credentials=creds)
            logger.info("Google Calendar service initialized ✓")
        except Exception as exc:
            logger.error("Failed to initialize Google Calendar: %s", exc)
            self.service = None

    def is_enabled(self) -> bool:
        """Verifica se sincronização está habilitada."""
        return self.service is not None

    async def criar_evento(
        self,
        calendario_id: str,
        titulo: str,
        descricao: str,
        data_inicio: datetime,
        duracao_minutos: int = 60,
        local: Optional[str] = None,
    ) -> Optional[dict]:
        """
        Cria um evento no Google Calendar.

        Args:
            calendario_id: ID do calendário (ex: 'primary' ou email)
            titulo: Título do evento
            descricao: Descrição detalhada
            data_inicio: Data/hora do evento
            duracao_minutos: Duração em minutos
            local: Endereço do evento (opcional)

        Returns:
            dict com 'event_id' e 'html_link' ou None se erro
        """
        if not self.is_enabled():
            logger.warning("Google Calendar not enabled")
            return None

        try:
            data_fim = data_inicio + timedelta(minutes=duracao_minutos)

            event = {
                "summary": titulo,
                "description": descricao,
                "start": {
                    "dateTime": data_inicio.isoformat(),
                    "timeZone": "America/Sao_Paulo",
                },
                "end": {
                    "dateTime": data_fim.isoformat(),
                    "timeZone": "America/Sao_Paulo",
                },
                "reminders": {
                    "useDefault": False,
                    "overrides": [
                        {"method": "email", "minutes": 1440},  # 24h antes
                        {"method": "popup", "minutes": 30},    # 30min antes
                    ],
                },
            }

            if local:
                event["location"] = local

            result = self.service.events().insert(
                calendarId=calendario_id, body=event
            ).execute()

            logger.info(
                "Evento criado no Google Calendar: %s",
                result.get("id"),
            )

            return {
                "event_id": result.get("id"),
                "html_link": result.get("htmlLink"),
                "created": True,
            }

        except HttpError as exc:
            logger.error("Erro ao criar evento Google Calendar: %s", exc)
            return None

    async def atualizar_evento(
        self,
        calendario_id: str,
        event_id: str,
        **campos,
    ) -> Optional[dict]:
        """
        Atualiza um evento existente.

        Args:
            calendario_id: ID do calendário
            event_id: ID do evento
            **campos: Campos a atualizar (summary, description, start, etc)

        Returns:
            dict com resultado ou None se erro
        """
        if not self.is_enabled():
            return None

        try:
            event = self.service.events().get(
                calendarId=calendario_id,
                eventId=event_id,
            ).execute()

            # Atualizar campos
            for key, value in campos.items():
                if key in event:
                    event[key] = value

            result = self.service.events().update(
                calendarId=calendario_id,
                eventId=event_id,
                body=event,
            ).execute()

            logger.info("Evento atualizado: %s", event_id)
            return result

        except HttpError as exc:
            logger.error("Erro ao atualizar evento: %s", exc)
            return None

    async def deletar_evento(
        self,
        calendario_id: str,
        event_id: str,
    ) -> bool:
        """Deleta um evento do calendário."""
        if not self.is_enabled():
            return False

        try:
            self.service.events().delete(
                calendarId=calendario_id,
                eventId=event_id,
            ).execute()

            logger.info("Evento deletado: %s", event_id)
            return True

        except HttpError as exc:
            logger.error("Erro ao deletar evento: %s", exc)
            return False

    async def listar_eventos_livres(
        self,
        calendario_id: str,
        data_inicio: datetime,
        data_fim: datetime,
        duracao_minutos: int = 60,
    ) -> list[dict]:
        """
        Lista horários LIVRES no calendário.
        Útil para mostrar slots disponíveis.

        Args:
            calendario_id: ID do calendário
            data_inicio: Data inicial
            data_fim: Data final
            duracao_minutos: Duração mínima do slot

        Returns:
            Lista de slots livres: [{'inicio': datetime, 'fim': datetime}, ...]
        """
        if not self.is_enabled():
            return []

        try:
            # Buscar eventos no período
            events_result = self.service.events().list(
                calendarId=calendario_id,
                timeMin=data_inicio.isoformat(),
                timeMax=data_fim.isoformat(),
                singleEvents=True,
                orderBy="startTime",
            ).execute()

            eventos = events_result.get("items", [])

            # Calcular slots livres
            slots_livres = []
            hora_atual = data_inicio

            for evento in eventos:
                inicio = datetime.fromisoformat(
                    evento["start"].get("dateTime", "").replace("Z", "+00:00")
                )
                fim = datetime.fromisoformat(
                    evento["end"].get("dateTime", "").replace("Z", "+00:00")
                )

                # Se há gap entre hora_atual e evento
                gap = (inicio - hora_atual).total_seconds() / 60
                if gap >= duracao_minutos:
                    slots_livres.append(
                        {"inicio": hora_atual, "fim": inicio}
                    )

                hora_atual = max(hora_atual, fim)

            # Último slot até fim do período
            gap = (data_fim - hora_atual).total_seconds() / 60
            if gap >= duracao_minutos:
                slots_livres.append({"inicio": hora_atual, "fim": data_fim})

            return slots_livres

        except HttpError as exc:
            logger.error("Erro ao listar eventos: %s", exc)
            return []


# Singleton global
_google_calendar_sync: Optional[GoogleCalendarSync] = None


def get_google_calendar_sync() -> GoogleCalendarSync:
    """Retorna instância singleton do Google Calendar sync."""
    global _google_calendar_sync
    if _google_calendar_sync is None:
        _google_calendar_sync = GoogleCalendarSync()
    return _google_calendar_sync


async def sync_agendamento_to_google(
    agendamento_id: int,
    titulo: str,
    descricao: str,
    data_agendamento: datetime,
    duracao_minutos: int = 60,
    local: Optional[str] = None,
    calendario_id: str = "primary",
) -> Optional[str]:
    """
    Sincroniza um agendamento para Google Calendar.

    Returns:
        event_id se sucesso, None se falha
    """
    gc = get_google_calendar_sync()

    if not gc.is_enabled():
        logger.info("Google Calendar sync disabled, skipping...")
        return None

    resultado = await gc.criar_evento(
        calendario_id=calendario_id,
        titulo=titulo,
        descricao=descricao,
        data_inicio=data_agendamento,
        duracao_minutos=duracao_minutos,
        local=local,
    )

    return resultado.get("event_id") if resultado else None
