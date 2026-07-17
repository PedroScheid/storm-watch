"""Schemas Pydantic da API."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Intensity = Literal["moderada", "forte", "muito_forte"]


class PushSubscriptionKeys(BaseModel):
    p256dh: str
    auth: str


class PushSubscription(BaseModel):
    endpoint: str
    keys: PushSubscriptionKeys


class MonitorCreate(BaseModel):
    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)
    min_intensity: Intensity = "moderada"
    alert_radius_km: float = Field(default=50.0, gt=0, le=300)
    subscription: PushSubscription


class MonitorOut(BaseModel):
    id: int
    lat: float
    lon: float
    min_intensity: Intensity
    alert_radius_km: float


class UnsubscribeRequest(BaseModel):
    endpoint: str


class VapidPublicKey(BaseModel):
    public_key: str


class NowcastQuery(BaseModel):
    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)


class CellOut(BaseModel):
    intensity: Intensity
    eta_minutes: float | None
    distance_km: float
    bearing_deg: float
    speed_kmh: float
    approaching: bool


class NowcastOut(BaseModel):
    lat: float
    lon: float
    generated_at: float
    frame_time: str | None
    cells: list[CellOut]
