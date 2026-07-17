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
from typing import Any

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

-- Estado de alerta POR LOCAL (uma ameaça por vez). Evita flood: só notificamos
-- na entrada da chuva, num agravamento de intensidade, ou quando ela passa.
CREATE TABLE IF NOT EXISTS alert_state (
    monitor_id    INTEGER PRIMARY KEY,
    level         TEXT,               -- moderada|forte|muito_forte; NULL = sem ameaça
    eta_minutes   REAL,
    clear_cycles  INTEGER NOT NULL DEFAULT 0,  -- ciclos seguidos sem ameaça (p/ cancelar com folga)
    updated_at    REAL    NOT NULL,
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


# ─── Estado de alerta por local ────────────────────────────────────────

def get_alert_state(monitor_id: int) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM alert_state WHERE monitor_id = ?", (monitor_id,)
        ).fetchone()
        return dict(row) if row else None


def set_alert_state(
    monitor_id: int, level: str | None, eta_minutes: float | None, clear_cycles: int
) -> None:
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO alert_state (monitor_id, level, eta_minutes, clear_cycles, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(monitor_id) DO UPDATE SET
                level=excluded.level, eta_minutes=excluded.eta_minutes,
                clear_cycles=excluded.clear_cycles, updated_at=excluded.updated_at
            """,
            (monitor_id, level, eta_minutes, clear_cycles, time.time()),
        )
        conn.commit()
