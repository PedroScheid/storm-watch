"""Orquestração do nowcasting para um único local monitorado."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from ..config import get_settings
from . import fetcher, processor
from .processor import Cell


@dataclass
class Nowcast:
    lat: float
    lon: float
    generated_at: float
    frame_time: str | None
    cells: list[Cell]


def run_for_location(
    lat: float,
    lon: float,
    min_intensity: str = "moderada",
    alert_radius_km: float = 50.0,
) -> Nowcast:
    """Baixa os quadros recentes do GOES-19 e analisa a chuva ao redor de (lat, lon)."""
    settings = get_settings()
    fields = fetcher.load_recent_fields(
        lat, lon,
        radius_km=settings.analysis_radius_km,
        n=settings.frames_for_motion,
    )
    cells = processor.analyze(
        fields,
        target_lat=lat,
        target_lon=lon,
        thresholds=settings.intensity_thresholds,
        alert_radius_km=alert_radius_km,
        min_intensity=min_intensity,
    )
    frame_time = fields[-1].timestamp.isoformat() if fields else None
    return Nowcast(
        lat=lat,
        lon=lon,
        generated_at=dt.datetime.now(dt.timezone.utc).timestamp(),
        frame_time=frame_time,
        cells=cells,
    )
