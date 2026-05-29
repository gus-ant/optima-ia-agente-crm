"""
crm/agenda_rules.py
-------------------
Regras de negócio para gerenciar a agenda de agendamentos.

Regras:
- Segunda a sexta: 08:00 - 16:30
- Sábado: 08:00 - 11:00
- Consulta: 40 minutos
- Atendimento completo: 60 minutos
- Máximo 5 agendamentos por dia
- Intervalo mínimo de 15 minutos entre agendamentos
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, time
from typing import Optional, Literal

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# --- Constantes de Configuração ---

class AgendaConfig:
    """Configuração centralizada da agenda."""

    # Horários de funcionamento
    HORARIO_ABERTURA = 8  # 8 AM
    HORARIO_FECHAMENTO = 17  # 5 PM (até 16:30 efetivamente)

    # Dias da semana (0 = seg, 6 = dom)
    DIAS_FUNCIONAMENTO = {
        0: ("seg", time(8, 0), time(16, 30)),  # Segunda
        1: ("ter", time(8, 0), time(16, 30)),  # Terça
        2: ("qua", time(8, 0), time(16, 30)),  # Quarta
        3: ("qui", time(8, 0), time(16, 30)),  # Quinta
        4: ("sex", time(8, 0), time(16, 30)),  # Sexta
        5: ("sab", time(8, 0), time(11, 0)),   # Sábado
        6: None,  # Domingo (fechado)
    }

    # Durações
    DURACAO_CONSULTA = 40  # minutos
    DURACAO_ATENDIMENTO = 60  # minutos
    INTERVALO_MINIMO = 15  # minutos entre agendamentos

    # Limites de capacidade
    MAX_AGENDAMENTOS_POR_DIA = 5
    MAX_AGENDAMENTOS_POR_HORA = 2

    # Aviso antecipado
    DIAS_AVISO_MINIMO = 1  # Mínimo 1 dia de antecedência
    HORAS_CONFIRMACAO = 24  # 24 horas para confirmar


def get_horario_funcionamento(data: datetime) -> Optional[tuple[time, time]]:
    """
    Retorna (hora_abertura, hora_fechamento) para o dia da semana.

    Args:
        data: Data a verificar

    Returns:
        Tupla (time_abertura, time_fechamento) ou None se fechado
    """
    dia_semana = data.weekday()  # 0=seg, 6=dom
    info = AgendaConfig.DIAS_FUNCIONAMENTO.get(dia_semana)
    return (info[1], info[2]) if info else None


def eh_dia_funcionamento(data: datetime) -> bool:
    """Verifica se é dia de funcionamento."""
    return get_horario_funcionamento(data) is not None


def eh_horario_valido(data_hora: datetime) -> tuple[bool, Optional[str]]:
    """
    Valida se o horário/dia está dentro do funcionamento.

    Returns:
        (é_válido, mensagem_erro)
    """
    # Verificar se não é no passado
    if data_hora < datetime.now():
        return False, "❌ Não é possível agendar no passado"

    # Verificar dias de antecedência
    dias_diff = (data_hora.date() - datetime.now().date()).days
    if dias_diff < AgendaConfig.DIAS_AVISO_MINIMO:
        return False, f"❌ Mínimo {AgendaConfig.DIAS_AVISO_MINIMO} dia de antecedência"

    horarios = get_horario_funcionamento(data_hora)

    if not horarios:
        dia_nome = data_hora.strftime("%A")  # "Sunday", "Monday", etc
        return False, f"❌ Não funcionamos aos {dia_nome}s"

    abertura, fechamento = horarios
    hora = data_hora.time()

    if hora < abertura:
        return (
            False,
            f"❌ Abrimos às {abertura.strftime('%H:%M')}",
        )

    if hora >= fechamento:
        return (
            False,
            f"❌ Fechamos às {fechamento.strftime('%H:%M')}",
        )

    return True, None


async def validar_disponibilidade(
    session: AsyncSession,
    data_hora: datetime,
    duracao_minutos: int = 60,
) -> tuple[bool, Optional[str]]:
    """
    Valida se um horário está disponível.

    Checks:
    1. Horário dentro de funcionamento
    2. Não tem conflito com outro agendamento
    3. Não ultrapassa limite de agendamentos/dia
    4. Intervalo mínimo entre agendamentos respeitado

    Args:
        session: Sessão do banco de dados
        data_hora: Data/hora desejada
        duracao_minutos: Duração do agendamento

    Returns:
        (está_disponível, mensagem_erro)
    """
    from crm.models import Agendamento

    # 1. Validar horário
    valido, erro = eh_horario_valido(data_hora)
    if not valido:
        return False, erro

    # 2. Verificar limite de agendamentos por dia
    data = data_hora.date()
    stmt_dia = select(Agendamento).filter(
        and_(
            Agendamento.data_agendamento >= datetime.combine(data, time.min),
            Agendamento.data_agendamento < datetime.combine(data, time.max),
            Agendamento.cancelado_em.is_(None),  # Não contar cancelados
        )
    )

    result = await session.execute(stmt_dia)
    agendamentos_dia = result.scalars().all()

    if len(agendamentos_dia) >= AgendaConfig.MAX_AGENDAMENTOS_POR_DIA:
        return False, "❌ Agenda lotada para este dia"

    # 3. Verificar conflitos e intervalo mínimo
    fim_desejado = data_hora + timedelta(minutes=duracao_minutos)
    margem = timedelta(minutes=AgendaConfig.INTERVALO_MINIMO)

    for agd in agendamentos_dia:
        agd_fim = agd.data_agendamento + timedelta(minutes=agd.duracao_minutos)

        # Conflito direto
        if (data_hora < agd_fim and fim_desejado > agd.data_agendamento):
            return False, f"❌ Conflito com agendamento existente"

        # Intervalo mínimo não respeitado
        if (
            (data_hora - margem < agd_fim and data_hora >= agd_fim)
            or (fim_desejado <= agd.data_agendamento and fim_desejado + margem > agd.data_agendamento)
        ):
            return False, f"❌ Intervalo de {AgendaConfig.INTERVALO_MINIMO}min não respeitado"

    return True, None


async def get_slots_disponiveis(
    session: AsyncSession,
    data_inicio: datetime,
    num_opcoes: int = 3,
    duracao_minutos: int = 60,
) -> list[dict]:
    """
    Retorna próximos slots disponíveis a partir de uma data.

    Args:
        session: Sessão do banco de dados
        data_inicio: Data a começar a buscar
        num_opcoes: Quantas opções retornar
        duracao_minutos: Duração do agendamento

    Returns:
        Lista de dicts com slots disponíveis: [{'data': '2026-06-15', 'hora': '14:30', 'datetime': ...}]
    """
    from crm.models import Agendamento

    slots = []
    data_atual = max(
        data_inicio,
        datetime.now() + timedelta(days=AgendaConfig.DIAS_AVISO_MINIMO),
    )

    # Buscar 15 dias à frente
    for offset_dias in range(15):
        if len(slots) >= num_opcoes:
            break

        dia = data_atual.date() + timedelta(days=offset_dias)
        horarios = get_horario_funcionamento(datetime.combine(dia, time.noon))

        if not horarios:
            continue  # Dia fechado

        abertura, fechamento = horarios
        hora_atual = datetime.combine(dia, abertura)

        while hora_atual.time() < fechamento:
            disponivel, _ = await validar_disponibilidade(
                session, hora_atual, duracao_minutos
            )

            if disponivel:
                slots.append({
                    "data": hora_atual.date().isoformat(),
                    "hora": hora_atual.time().strftime("%H:%M"),
                    "datetime": hora_atual.isoformat(),
                    "dia_semana": hora_atual.strftime("%A"),
                })

            # Avançar em 30 minutos
            hora_atual += timedelta(minutes=30)

    return slots


async def confirmar_slot(
    session: AsyncSession,
    data_hora: datetime,
    duracao_minutos: int = 60,
) -> tuple[bool, Optional[str]]:
    """
    Valida e "reserva" um slot (marcar como reservado).

    Retorna sucesso ou motivo da rejeição.
    """
    return await validar_disponibilidade(session, data_hora, duracao_minutos)


def calcular_horario_fim(data_inicio: datetime, duracao_minutos: int) -> datetime:
    """Calcula horário de fim baseado na duração."""
    return data_inicio + timedelta(minutes=duracao_minutos)


def tempo_ate_agendamento(data_agendamento: datetime) -> dict:
    """
    Calcula tempo restante até agendamento.

    Returns: {'dias': 2, 'horas': 3, 'minutos': 30, 'total_minutos': 3210}
    """
    agora = datetime.now()
    delta = data_agendamento - agora

    minutos_totais = int(delta.total_seconds() / 60)
    dias = delta.days
    horas = (delta.seconds // 3600)
    minutos = (delta.seconds % 3600) // 60

    return {
        "dias": dias,
        "horas": horas,
        "minutos": minutos,
        "total_minutos": minutos_totais,
    }


def deve_enviar_lembrete_24h(data_agendamento: datetime) -> bool:
    """Verifica se deve enviar lembrete de 24h antes."""
    tempo = tempo_ate_agendamento(data_agendamento)
    # Enviar quando faltam ~24h (margem de ±10 minutos)
    return 1430 <= tempo["total_minutos"] <= 1450


def deve_enviar_lembrete_30min(data_agendamento: datetime) -> bool:
    """Verifica se deve enviar lembrete de 30min antes."""
    tempo = tempo_ate_agendamento(data_agendamento)
    # Enviar quando faltam ~30min (margem de ±5 minutos)
    return 20 <= tempo["total_minutos"] <= 35


def formatar_agendamento_para_mensagem(
    data_agendamento: datetime,
    tipo: str,
    local: Optional[str] = None,
) -> str:
    """
    Formata agendamento em mensagem legível para WhatsApp.

    Args:
        data_agendamento: Data/hora do agendamento
        tipo: 'consulta_inicial', 'visita_local', 'apresentacao_orcamento'
        local: Local do atendimento

    Returns:
        String formatada para WhatsApp
    """
    data_fmt = data_agendamento.strftime("%d/%m/%Y")
    hora_fmt = data_agendamento.strftime("%H:%M")
    dia_semana = data_agendamento.strftime("%A")

    tipo_label = {
        "consulta_inicial": "📞 Consulta Inicial",
        "visita_local": "🏠 Visita Local",
        "apresentacao_orcamento": "📊 Apresentação de Orçamento",
    }.get(tipo, tipo)

    msg = f"""
✅ Agendamento Confirmado!

{tipo_label}
📅 {data_fmt} ({dia_semana})
🕐 {hora_fmt}
📍 Local: {local or 'A confirmar'}

[Confirmar Presença] [Reagendar] [Cancelar]
    """
    return msg.strip()
