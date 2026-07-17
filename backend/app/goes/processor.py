"""Detecção de células de chuva, movimento e estimativa de ETA.

Recebe uma sequência de quadros de taxa de chuva (mm/h) recortados ao redor do
local monitorado e responde: existe chuva se aproximando? Com que intensidade e
em quanto tempo (ETA)?

Estratégia:
  1. Limiarizar a taxa de chuva para achar células (componentes conexos).
  2. Estimar o vetor de movimento com fluxo óptico denso (Farneback) entre os
     dois últimos quadros.
  3. Projetar cada célula na direção do movimento e calcular o ETA até o local.
  4. Só considerar células que estão se APROXIMANDO (componente de velocidade
     na direção do alvo é positiva).
"""

from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass
from typing import Optional

import cv2
import numpy as np

from .fetcher import RainField

KM_PER_PIXEL = 2.0   # resolução da grade RRQPEF


@dataclass
class Cell:
    intensity: str          # moderada | forte | muito_forte
    peak_mmh: float
    distance_km: float      # distância atual da borda da célula ao alvo
    bearing_deg: float      # de onde a célula vem (0=N, 90=L)
    speed_kmh: float        # velocidade de translação da célula
    approaching: bool
    eta_minutes: Optional[float]
    cell_key: str           # identidade aproximada p/ deduplicar alertas


def classify_intensity(mmh: float, thresholds: dict[str, float]) -> Optional[str]:
    if mmh >= thresholds["muito_forte"]:
        return "muito_forte"
    if mmh >= thresholds["forte"]:
        return "forte"
    if mmh >= thresholds["moderada"]:
        return "moderada"
    return None


def _intensity_rank(level: str) -> int:
    return {"moderada": 1, "forte": 2, "muito_forte": 3}[level]


def _haversine_km(lat1, lon1, lat2, lon2) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _bearing_deg(lat1, lon1, lat2, lon2) -> float:
    """Rumo de (1) para (2), em graus a partir do Norte, sentido horário."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    x = math.sin(dl) * math.cos(p2)
    y = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def _centroid(field: np.ndarray) -> tuple[float, float] | None:
    """Centróide de massa (x, y) ponderado pela taxa de chuva; None se não há chuva."""
    total = float(field.sum())
    if total <= 0:
        return None
    ys, xs = np.indices(field.shape)
    cx = float((xs * field).sum() / total)
    cy = float((ys * field).sum() / total)
    return cx, cy


def _estimate_motion(prev: np.ndarray, curr: np.ndarray) -> tuple[float, float]:
    """Vetor de deslocamento (dx, dy) em pixels entre dois quadros.

    dx>0 = movimento para a direita (leste), dy>0 = para baixo (sul),
    coerente com a orientação das matrizes de load_crop.

    Estratégia principal: deslocamento do centróide de massa (robusto a campos
    de intensidade uniforme, ao contrário do fluxo óptico denso). Reforço:
    phase correlation (cv2.phaseCorrelate) quando ambos os quadros têm textura.
    """
    c_prev = _centroid(prev)
    c_curr = _centroid(curr)
    if c_prev is None or c_curr is None:
        return 0.0, 0.0

    dx = c_curr[0] - c_prev[0]
    dy = c_curr[1] - c_prev[1]

    # Se o centróide mal se moveu (célula estacionária ou crescimento simétrico),
    # tenta o phase correlation para captar translação de padrão.
    if abs(dx) < 0.5 and abs(dy) < 0.5:
        try:
            p = np.ascontiguousarray(prev, dtype="float32")
            c = np.ascontiguousarray(curr, dtype="float32")
            (sx, sy), _ = cv2.phaseCorrelate(p, c)
            if math.hypot(sx, sy) > math.hypot(dx, dy):
                dx, dy = float(sx), float(sy)
        except cv2.error:
            pass

    return dx, dy


def analyze(
    fields: list[RainField],
    target_lat: float,
    target_lon: float,
    thresholds: dict[str, float],
    alert_radius_km: float,
    min_intensity: str = "moderada",
) -> list[Cell]:
    """Analisa a sequência de quadros e devolve células relevantes (aproximando)."""
    if not fields:
        return []

    last = fields[-1]
    grid = last.rate_mmh
    if grid.size == 0:
        return []

    # Índice do alvo dentro do recorte (centro, por construção do load_crop).
    ty = grid.shape[0] // 2
    tx = grid.shape[1] // 2

    # Movimento (px/quadro) e intervalo entre quadros (min).
    dx = dy = 0.0
    dt_min = 10.0
    if len(fields) >= 2:
        dx, dy = _estimate_motion(fields[-2].rate_mmh, grid)
        secs = (fields[-1].timestamp - fields[-2].timestamp).total_seconds()
        if secs > 0:
            dt_min = secs / 60.0

    speed_px_per_min = math.hypot(dx, dy) / dt_min if dt_min else 0.0
    speed_kmh = speed_px_per_min * KM_PER_PIXEL * 60.0

    # Detecta células acima do limiar mínimo de intensidade.
    min_thr = thresholds[min_intensity]
    binary = (grid >= min_thr).astype("uint8")
    if binary.sum() == 0:
        return []

    n_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(binary, connectivity=8)

    cells: list[Cell] = []
    for label in range(1, n_labels):
        area = stats[label, cv2.CC_STAT_AREA]
        if area < 3:   # ignora ruído (< ~12 km²)
            continue

        cyc, cxc = centroids[label][1], centroids[label][0]   # (linha, coluna)
        cell_mask = labels == label
        peak = float(grid[cell_mask].max())
        level = classify_intensity(peak, thresholds)
        if level is None or _intensity_rank(level) < _intensity_rank(min_intensity):
            continue

        # Geometria célula -> alvo.
        clat = float(np.interp(cyc, np.arange(len(last.lats)), last.lats))
        clon = float(np.interp(cxc, np.arange(len(last.lons)), last.lons))
        distance_km = _haversine_km(clat, clon, target_lat, target_lon)
        bearing = _bearing_deg(clat, clon, target_lat, target_lon)

        # A célula está se aproximando? Vetor alvo (em pixels) vs. vetor de movimento.
        to_target = np.array([tx - cxc, ty - cyc], dtype="float64")
        norm_t = np.linalg.norm(to_target)
        motion = np.array([dx, dy], dtype="float64")
        approaching = False
        eta_minutes: Optional[float] = None
        if norm_t > 0 and speed_px_per_min > 0:
            unit_t = to_target / norm_t
            closing_px_per_min = float(np.dot(motion, unit_t)) / dt_min
            if closing_px_per_min > 0:
                approaching = True
                # ETA até a BORDA da célula tocar o alvo (desconta o raio de alerta).
                edge_px = max(0.0, norm_t - (alert_radius_km / KM_PER_PIXEL))
                eta_minutes = round(edge_px / closing_px_per_min, 1)

        # Chave de dedup: setor de rumo (30°) + faixa de distância (20 km).
        cell_key = f"{level}:{int(bearing // 30)}:{int(distance_km // 20)}"

        cells.append(
            Cell(
                intensity=level,
                peak_mmh=round(peak, 1),
                distance_km=round(distance_km, 1),
                bearing_deg=round(bearing, 0),
                speed_kmh=round(speed_kmh, 1),
                approaching=approaching,
                eta_minutes=eta_minutes,
                cell_key=cell_key,
            )
        )

    # Prioriza células que se aproximam, mais intensas e mais próximas.
    cells.sort(key=lambda c: (not c.approaching, -_intensity_rank(c.intensity), c.distance_km))
    return cells
