"""Worker periódico: processa cada local monitorado e dispara alertas.

Roda como uma task assíncrona dentro do processo FastAPI (lifespan). Para cada
monitor:
  1. Roda o nowcast (download + análise GOES).
  2. Para cada célula que se aproxima e atinge a intensidade mínima do usuário,
     verifica se já existe alerta ativo (dedup) e, se não, envia push.
  3. Cancela alertas cujas células não ameaçam mais (mudança de direção).
"""

from __future__ import annotations

import asyncio
import logging

from . import database as db
from .config import get_settings
from .goes import nowcast
from .notifications import push

log = logging.getLogger("stormwatch.worker")

# Chave S3 do último quadro processado por posição (evita reprocesso).
_last_frame: dict[str, str] = {}


def _pos_key(lat: float, lon: float) -> str:
    return f"{round(lat, 3)},{round(lon, 3)}"


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

    active = db.get_active_alerts(monitor["id"])
    approaching = [c for c in result.cells if c.approaching]
    seen_keys: list[str] = []

    for cell in approaching:
        seen_keys.append(cell.cell_key)
        if cell.cell_key in active:
            # Já notificado: atualiza ETA sem reenviar push.
            db.record_alert(monitor["id"], cell.cell_key, cell.intensity, cell.eta_minutes or 0)
            continue

        payload = push.build_message(cell.intensity, cell.eta_minutes, cell.peak_mmh)
        ok = push.send_push(subscription, payload)
        if not ok:
            db.delete_monitor(monitor["id"])
            log.info("Monitor %s removido (subscription expirada)", monitor["id"])
            return
        db.record_alert(monitor["id"], cell.cell_key, cell.intensity, cell.eta_minutes or 0)
        log.info("Alerta enviado monitor=%s %s", monitor["id"], payload["body"])

    # Cancela alertas de células que não ameaçam mais (só se houve quadro válido).
    if result.frame_time:
        removed = db.clear_alerts_except(monitor["id"], seen_keys)
        if removed:
            push.send_push(subscription, push.build_cancel_message())
            log.info("Cancelamento enviado monitor=%s (%d célula[s])", monitor["id"], len(removed))


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
