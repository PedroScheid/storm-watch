"""Testes do algoritmo de detecção/ETA com quadros sintéticos.

Não dependem de rede: fabricamos campos de chuva e verificamos que uma célula
se movendo em direção ao alvo é detectada, classificada e recebe um ETA coerente.
"""

from __future__ import annotations

import datetime as dt

import numpy as np

from app.goes.fetcher import RainField
from app.goes.processor import analyze, classify_intensity

THRESHOLDS = {"moderada": 2.5, "forte": 10.0, "muito_forte": 50.0}


def _blank(n=121):
    """Grade quadrada com alvo no centro; ~2 km/pixel, janela ~120 km."""
    return np.zeros((n, n), dtype="float32")


def _disk(grid, cy, cx, radius, value):
    yy, xx = np.ogrid[: grid.shape[0], : grid.shape[1]]
    mask = (yy - cy) ** 2 + (xx - cx) ** 2 <= radius**2
    grid[mask] = value
    return grid


def _field(grid, minutes_ago):
    t = dt.datetime(2026, 7, 17, 12, 0, tzinfo=dt.timezone.utc) - dt.timedelta(minutes=minutes_ago)
    n = grid.shape[0]
    lat, lon = -25.0, -49.0
    span = 120 / 111.0
    lats = np.linspace(lat + span, lat - span, n)
    lons = np.linspace(lon - span, lon + span, n)
    return RainField(rate_mmh=grid, lats=lats, lons=lons, timestamp=t)


def test_classify_intensity():
    assert classify_intensity(1.0, THRESHOLDS) is None
    assert classify_intensity(5.0, THRESHOLDS) == "moderada"
    assert classify_intensity(20.0, THRESHOLDS) == "forte"
    assert classify_intensity(60.0, THRESHOLDS) == "muito_forte"


def test_cell_approaching_gets_eta():
    center = 60  # alvo no centro de uma grade 121x121

    # Célula forte (15 mm/h) vindo do oeste, aproximando-se do centro.
    g_prev = _disk(_blank(), cy=center, cx=20, radius=6, value=15.0)
    g_curr = _disk(_blank(), cy=center, cx=32, radius=6, value=15.0)

    cells = analyze(
        [_field(g_prev, 10), _field(g_curr, 0)],
        target_lat=-25.0, target_lon=-49.0,
        thresholds=THRESHOLDS, alert_radius_km=10.0, min_intensity="moderada",
    )

    assert cells, "deveria detectar ao menos uma célula"
    top = cells[0]
    assert top.intensity == "forte"
    assert top.approaching is True
    assert top.eta_minutes is not None and top.eta_minutes > 0
    assert top.speed_kmh > 0


def test_no_cell_below_threshold():
    g = _disk(_blank(), cy=60, cx=30, radius=6, value=1.0)  # abaixo de moderada
    cells = analyze(
        [_field(g, 10), _field(g, 0)],
        target_lat=-25.0, target_lon=-49.0,
        thresholds=THRESHOLDS, alert_radius_km=10.0, min_intensity="moderada",
    )
    assert cells == []


def test_min_intensity_filter():
    # Célula apenas moderada, mas usuário quer só "forte" -> nada.
    g_prev = _disk(_blank(), cy=60, cx=20, radius=6, value=5.0)
    g_curr = _disk(_blank(), cy=60, cx=32, radius=6, value=5.0)
    cells = analyze(
        [_field(g_prev, 10), _field(g_curr, 0)],
        target_lat=-25.0, target_lon=-49.0,
        thresholds=THRESHOLDS, alert_radius_km=10.0, min_intensity="forte",
    )
    assert cells == []
