"""Worker periódico: processa cada local monitorado e dispara alertas.

Roda como uma task assíncrona dentro do processo FastAPI (lifespan). Para cada
monitor, mantém UM estado de ameaça por local e evita flood de notificações:

  - Envia UM alerta quando a chuva entra no raio (na intensidade mínima do usuário).
  - Envia UM aviso de agravamento se a intensidade subir (moderada→forte→muito forte).
  - NÃO repete enquanto a chuva só se aproxima (o ETA cai sozinho).
  - Envia "passou" só após alguns ciclos seguidos sem ameaça (com folga, sem flip-flop).
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Optional

from . import database as db
from .config import get_settings
from .goes import nowcast
from .goes.processor import Cell

from .notifications import push

log = logging.getLogger("stormwatch.worker")

# Ciclos seguidos sem ameaça antes de mandar "a chuva passou" (evita flip-flop).
CLEAR_CYCLES_TO_CANCEL = 2

_RANK = {"moderada": 1, "forte": 2, "muito_forte": 3}

# Chave S3 do último quadro processado por posição (evita reprocesso).
_last_frame: dict[str, str] = {}


def _pos_key(lat: float, lon: float) -> str:
    return f"{round(lat, 3)},{round(lon, 3)}"


@dataclass
class Decision:
    action: str                 # "alert" | "escalate" | "cancel" | "none"
    cell: Optional[Cell]        # célula relevante para a mensagem (alert/escalate)
    state_level: Optional[str]  # novo nível a persistir (None = sem ameaça)
    clear_cycles: int           # novo contador de ciclos sem ameaça


def decide_notification(
    prev_level: Optional[str], clear_cycles: int, threats: list[Cell]
) -> Decision:
    """Decide (de forma pura) o que notificar e qual o novo estado.

    Regras: 1 alerta na entrada; 1 aviso quando a intensidade sobe; nada quando só
    se aproxima ou quando enfraquece; "passou" após CLEAR_CYCLES_TO_CANCEL ciclos
    seguidos sem ameaça.
    """
    if threats:
        # Pior ameaça: maior intensidade e, empatando, menor ETA.
        worst = max(threats, key=lambda c: (_RANK[c.intensity], -(c.eta_minutes or 1e9)))
        if prev_level is None:
            return Decision("alert", worst, worst.intensity, 0)
        if _RANK[worst.intensity] > _RANK[prev_level]:
            return Decision("escalate", worst, worst.intensity, 0)
        # Mesmo nível ou mais fraco: não notifica; mantém o estado e zera o contador.
        return Decision("none", worst, prev_level, 0)

    # Sem ameaça neste ciclo.
    if prev_level is not None:
        c = clear_cycles + 1
        if c >= CLEAR_CYCLES_TO_CANCEL:
            return Decision("cancel", None, None, 0)
        return Decision("none", None, prev_level, c)
    return Decision("none", None, None, 0)


def process_monitor(monitor: dict) -> None:
    lat, lon = monitor["lat"], monitor["lon"]
    min_intensity = monitor["min_intensity"]
    radius = monitor["alert_radius_km"]

    result = nowcast.run_for_location(lat, lon, min_intensity, radius)

    # Evita reprocessar o mesmo quadro para a mesma posição.
    pos = _pos_key(lat, lon)
    if result.frame_time and _last_frame.get(pos) == result.frame_time:
        log.debug("Sem quadro novo para %s", pos)
        # ainda assim segue: o estado de alertas pode precisar de cancelamento
    _last_frame[pos] = result.frame_time or _last_frame.get(pos, "")

    subscription = {
        "endpoint": monitor["push_endpoint"],
        "p256dh": monitor["push_p256dh"],
        "auth": monitor["push_auth"],
    }

    # Ameaças = células se aproximando E dentro do raio configurado pelo usuário.
    threats = [c for c in result.cells if c.approaching and c.distance_km <= radius]

    # Sem quadro válido, não mexe no estado (evita cancelar por falta de dado).
    if not result.frame_time:
        return

    state = db.get_alert_state(monitor["id"]) or {}
    prev_level = state.get("level")
    clear_cycles = state.get("clear_cycles", 0) or 0

    decision = decide_notification(prev_level, clear_cycles, threats)

    payload = None
    if decision.action == "alert":
        payload = push.build_message(
            decision.cell.intensity, decision.cell.eta_minutes, decision.cell.peak_mmh
        )
    elif decision.action == "escalate":
        payload = push.build_escalation_message(
            decision.cell.intensity, decision.cell.eta_minutes, decision.cell.peak_mmh
        )
    elif decision.action == "cancel":
        payload = push.build_cancel_message()

    if payload is not None:
        ok = push.send_push(subscription, payload)
        if not ok:
            db.delete_monitor(monitor["id"])
            log.info("Monitor %s removido (subscription expirada)", monitor["id"])
            return
        log.info("Push [%s] monitor=%s: %s", decision.action, monitor["id"], payload["body"])

    eta = decision.cell.eta_minutes if decision.cell else None
    db.set_alert_state(monitor["id"], decision.state_level, eta, decision.clear_cycles)


def run_cycle() -> None:
    monitors = db.list_monitors()
    log.info("Ciclo: %d monitor(es)", len(monitors))
    for monitor in monitors:
        try:
            process_monitor(monitor)
        except Exception:  # noqa: BLE001 — isolar falha por monitor
            log.exception("Falha ao processar monitor %s", monitor.get("id"))


async def worker_loop(stop: asyncio.Event) -> None:
    settings = get_settings()
    log.info("Worker iniciado (intervalo=%ss)", settings.poll_interval_seconds)
    while not stop.is_set():
        # run_cycle é síncrono (I/O de rede + CPU); roda em thread para não travar o loop.
        await asyncio.to_thread(run_cycle)
        try:
            await asyncio.wait_for(stop.wait(), timeout=settings.poll_interval_seconds)
        except asyncio.TimeoutError:
            pass
