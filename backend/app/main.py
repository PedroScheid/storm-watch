"""API FastAPI do StormWatch."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from . import database as db
from . import worker
from .config import get_settings
from .goes import nowcast
from .notifications import push
from .schemas import (
    CellOut,
    MonitorCreate,
    MonitorOut,
    NowcastOut,
    UnsubscribeRequest,
    VapidPublicKey,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    stop = asyncio.Event()
    task = asyncio.create_task(worker.worker_loop(stop))
    app.state.worker_stop = stop
    app.state.worker_task = task
    try:
        yield
    finally:
        stop.set()
        await task


settings = get_settings()
app = FastAPI(title="StormWatch API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/vapid-public-key", response_model=VapidPublicKey)
def vapid_public_key() -> VapidPublicKey:
    if not settings.vapid_public_key:
        raise HTTPException(500, "VAPID não configurado")
    return VapidPublicKey(public_key=settings.vapid_public_key)


@app.post("/monitors", response_model=MonitorOut, status_code=201)
def create_monitor(payload: MonitorCreate) -> MonitorOut:
    """Cria/atualiza o local monitorado ligado a uma subscription de push."""
    monitor_id = db.upsert_monitor(
        lat=payload.lat,
        lon=payload.lon,
        min_intensity=payload.min_intensity,
        alert_radius_km=payload.alert_radius_km,
        push={
            "endpoint": payload.subscription.endpoint,
            "p256dh": payload.subscription.keys.p256dh,
            "auth": payload.subscription.keys.auth,
        },
    )
    return MonitorOut(
        id=monitor_id,
        lat=payload.lat,
        lon=payload.lon,
        min_intensity=payload.min_intensity,
        alert_radius_km=payload.alert_radius_km,
    )


@app.post("/unsubscribe")
def unsubscribe(payload: UnsubscribeRequest) -> dict[str, bool]:
    db.delete_monitor_by_endpoint(payload.endpoint)
    return {"ok": True}


@app.post("/debug/test-push")
def debug_test_push() -> dict[str, int]:
    """Envia uma notificação de teste para todos os monitores cadastrados.

    Útil para validar o fluxo de push sem precisar esperar chover. Remova ou
    proteja este endpoint em produção.
    """
    monitors = db.list_monitors()
    sent = 0
    for m in monitors:
        payload = push.build_message("forte", 15, 12.0)
        payload["body"] = "🧪 Teste do StormWatch — se você recebeu isto, o push funciona!"
        if push.send_push(
            {"endpoint": m["push_endpoint"], "p256dh": m["push_p256dh"], "auth": m["push_auth"]},
            payload,
        ):
            sent += 1
    return {"monitors": len(monitors), "sent": sent}


@app.get("/debug/frame-stats")
def debug_frame_stats(lat: float, lon: float, radius_km: float = 120.0) -> dict:
    """Diagnóstico do pipeline GOES: valores brutos de chuva no quadro e na janela."""
    from .goes import fetcher
    return fetcher.diagnostics(lat, lon, radius_km)


@app.get("/nowcast", response_model=NowcastOut)
def get_nowcast(lat: float, lon: float, min_intensity: str = "moderada",
                alert_radius_km: float = 50.0) -> NowcastOut:
    """Consulta on-demand do estado de chuva ao redor de um ponto (para a UI)."""
    result = nowcast.run_for_location(lat, lon, min_intensity, alert_radius_km)
    return NowcastOut(
        lat=result.lat,
        lon=result.lon,
        generated_at=result.generated_at,
        frame_time=result.frame_time,
        cells=[
            CellOut(
                intensity=c.intensity,
                eta_minutes=c.eta_minutes,
                distance_km=c.distance_km,
                bearing_deg=c.bearing_deg,
                speed_kmh=c.speed_kmh,
                approaching=c.approaching,
            )
            for c in result.cells
        ],
    )
