"""Web Push via VAPID (pywebpush) + montagem das mensagens de alerta."""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from pywebpush import WebPushException, webpush

from ..config import get_settings

log = logging.getLogger("stormwatch.push")

_ICONS = {"moderada": "🌧️", "forte": "⛈️", "muito_forte": "⛈️"}
_LABELS = {"moderada": "moderada", "forte": "forte", "muito_forte": "muito forte"}


def build_message(intensity: str, eta_minutes: Optional[float], peak_mmh: float) -> dict[str, str]:
    """Monta título/corpo do alerta a partir da célula detectada."""
    icon = _ICONS.get(intensity, "🌧️")
    label = _LABELS.get(intensity, intensity)

    if eta_minutes is None:
        body = f"Chuva {label} se aproximando."
    elif eta_minutes <= 1:
        body = f"Chuva {label} chegando agora."
    else:
        body = f"Chuva {label} se aproximando. ETA: {int(round(eta_minutes))} min."

    title = f"{icon} StormWatch"

    # Aviso extra de granizo em chuva muito forte.
    if intensity == "muito_forte" and peak_mmh >= 80:
        body += " Possível granizo — proteja veículos e objetos expostos."

    return {"title": title, "body": body, "tag": intensity}


def build_escalation_message(intensity: str, eta_minutes: Optional[float], peak_mmh: float) -> dict[str, str]:
    """Mensagem de agravamento: a chuva já avisada ficou mais intensa."""
    label = _LABELS.get(intensity, intensity)
    if eta_minutes is None or eta_minutes <= 1:
        body = f"A chuva está piorando: agora {label}, chegando agora."
    else:
        body = f"A chuva está piorando: agora {label}. ETA: {int(round(eta_minutes))} min."
    if intensity == "muito_forte" and peak_mmh >= 80:
        body += " Possível granizo — proteja veículos e objetos expostos."
    return {"title": "⛈️ StormWatch", "body": body, "tag": "escalate"}


def build_cancel_message() -> dict[str, str]:
    return {
        "title": "🌤️ StormWatch",
        "body": "A chuva mudou de direção. Risco reduzido para o seu local.",
        "tag": "cancel",
    }


def send_push(subscription: dict[str, Any], payload: dict[str, str]) -> bool:
    """Envia um push. Retorna False se a subscription expirou (404/410)."""
    settings = get_settings()
    try:
        webpush(
            subscription_info={
                "endpoint": subscription["endpoint"],
                "keys": {
                    "p256dh": subscription["p256dh"],
                    "auth": subscription["auth"],
                },
            },
            data=json.dumps(payload),
            vapid_private_key=settings.vapid_private_key,
            vapid_claims={"sub": settings.vapid_subject},
            ttl=600,
        )
        return True
    except WebPushException as exc:
        status = getattr(exc.response, "status_code", None)
        if status in (404, 410):
            log.info("Subscription expirada (%s) — remover: %s", status, subscription["endpoint"])
            return False
        log.warning("Falha ao enviar push: %s", exc)
        return True  # falha transitória: não remove a subscription
