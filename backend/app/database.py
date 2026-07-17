"""Camada SQLite mínima.

Armazenamos apenas o necessário para os alertas funcionarem com o app fechado:
coordenadas do local monitorado, a subscription de push do navegador e a
preferência de intensidade. Nenhum dado pessoal (nome, e-mail, senha, histórico).
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Iterable

from .config import get_settings

_SCHEMA = """
CREATE TABLE IF NOT EXISTS monitors (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    lat             REAL    NOT NULL,
    lon             REAL    NOT NULL,
    min_intensity   TEXT    NOT NULL DEFAULT 'moderada',   -- moderada|forte|muito_forte
    alert_radius_km REAL    NOT NULL DEFAULT 50.0,
    push_endpoint   TEXT    NOT NULL,
    push_p256dh     TEXT    NOT NULL,
    push_auth       TEXT    NOT NULL,
    created_at      REAL    NOT NULL,
    UNIQUE(push_endpoint)
);

-- Estado de alertas ativos, para deduplicar e permitir cancelamento
-- quando uma célula muda de direção e deixa de ameaçar o local.
CREATE TABLE IF NOT EXISTS active_alerts (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    monitor_id    INTEGER NOT NULL,
    cell_key      TEXT    NOT NULL,     -- identidade aproximada da célula de chuva
    intensity     TEXT    NOT NULL,
    eta_minutes   REAL    NOT NULL,
    notified_at   REAL    NOT NULL,
    UNIQUE(monitor_id, cell_key),
    FOREIGN KEY(monitor_id) REFERENCES monitors(id) ON DELETE CASCADE
);
"""


def _connect() -> sqlite3.Connection:
    settings = get_settings()
    path = Path(settings.database_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.executescript(_SCHEMA)


# ─── Monitores ────────────────────────────────────────────────────────

def upsert_monitor(
    lat: float,
    lon: float,
    min_intensity: str,
    alert_radius_km: float,
    push: dict[str, str],
) -> int:
    """Cria ou atualiza um monitor identificado pela subscription de push."""
    with _connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO monitors (lat, lon, min_intensity, alert_radius_km,
                                  push_endpoint, push_p256dh, push_auth, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(push_endpoint) DO UPDATE SET
                lat=excluded.lat, lon=excluded.lon,
                min_intensity=excluded.min_intensity,
                alert_radius_km=excluded.alert_radius_km,
                push_p256dh=excluded.push_p256dh, push_auth=excluded.push_auth
            """,
            (
                lat, lon, min_intensity, alert_radius_km,
                push["endpoint"], push["p256dh"], push["auth"], time.time(),
            ),
        )
        conn.commit()
        row = conn.execute(
            "SELECT id FROM monitors WHERE push_endpoint = ?", (push["endpoint"],)
        ).fetchone()
        return int(row["id"])


def list_monitors() -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM monitors").fetchall()
        return [dict(r) for r in rows]


def delete_monitor(monitor_id: int) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM monitors WHERE id = ?", (monitor_id,))
        conn.commit()


def delete_monitor_by_endpoint(endpoint: str) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM monitors WHERE push_endpoint = ?", (endpoint,))
        conn.commit()


# ─── Alertas ativos (dedup / cancelamento) ─────────────────────────────

def get_active_alerts(monitor_id: int) -> dict[str, dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM active_alerts WHERE monitor_id = ?", (monitor_id,)
        ).fetchall()
        return {r["cell_key"]: dict(r) for r in rows}


def record_alert(monitor_id: int, cell_key: str, intensity: str, eta_minutes: float) -> None:
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO active_alerts (monitor_id, cell_key, intensity, eta_minutes, notified_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(monitor_id, cell_key) DO UPDATE SET
                intensity=excluded.intensity, eta_minutes=excluded.eta_minutes,
                notified_at=excluded.notified_at
            """,
            (monitor_id, cell_key, intensity, eta_minutes, time.time()),
        )
        conn.commit()


def clear_alerts_except(monitor_id: int, keep_cell_keys: Iterable[str]) -> list[dict[str, Any]]:
    """Remove alertas ativos cujas células não estão mais ameaçando.

    Retorna os alertas removidos (para eventual notificação de cancelamento).
    """
    keep = set(keep_cell_keys)
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM active_alerts WHERE monitor_id = ?", (monitor_id,)
        ).fetchall()
        removed = [dict(r) for r in rows if r["cell_key"] not in keep]
        if removed:
            placeholders = ",".join("?" for _ in removed)
            ids = [r["id"] for r in removed]
            conn.execute(
                f"DELETE FROM active_alerts WHERE id IN ({placeholders})", ids
            )
            conn.commit()
        return removed
