"""Configuração central lida de variáveis de ambiente (.env)."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Web Push (VAPID)
    vapid_public_key: str = Field(default="", alias="VAPID_PUBLIC_KEY")
    vapid_private_key: str = Field(default="", alias="VAPID_PRIVATE_KEY")
    vapid_subject: str = Field(default="mailto:contato@stormwatch.app", alias="VAPID_SUBJECT")

    # Banco
    database_path: str = Field(default="./data/stormwatch.db", alias="DATABASE_PATH")

    # Satélite
    goes_bucket: str = Field(default="noaa-goes19", alias="GOES_BUCKET")
    goes_product: str = Field(default="ABI-L2-RRQPEF", alias="GOES_PRODUCT")
    goes_region: str = Field(default="us-east-1", alias="GOES_REGION")

    # Worker
    poll_interval_seconds: int = Field(default=300, alias="POLL_INTERVAL_SECONDS")
    frames_for_motion: int = Field(default=3, alias="FRAMES_FOR_MOTION")

    # Limiares de intensidade (mm/h)
    rain_moderate_mmh: float = Field(default=2.5, alias="RAIN_MODERATE_MMH")
    rain_heavy_mmh: float = Field(default=10.0, alias="RAIN_HEAVY_MMH")
    rain_very_heavy_mmh: float = Field(default=50.0, alias="RAIN_VERY_HEAVY_MMH")

    # Análise
    analysis_radius_km: float = Field(default=120.0, alias="ANALYSIS_RADIUS_KM")

    # CORS
    cors_origins: str = Field(default="http://localhost:5173", alias="CORS_ORIGINS")

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def intensity_thresholds(self) -> dict[str, float]:
        """Mapa nível -> limiar mínimo em mm/h."""
        return {
            "moderada": self.rain_moderate_mmh,
            "forte": self.rain_heavy_mmh,
            "muito_forte": self.rain_very_heavy_mmh,
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()
