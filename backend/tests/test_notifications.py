"""Testa a máquina de estados de notificação (sem flood).

Regras esperadas:
  - 1 alerta na entrada da chuva;
  - nenhum novo alerta enquanto ela só se aproxima na mesma intensidade;
  - 1 aviso quando a intensidade sobe (agravamento);
  - nenhum aviso quando enfraquece;
  - "passou" só após CLEAR_CYCLES_TO_CANCEL ciclos seguidos sem ameaça.
"""

from __future__ import annotations

from app.goes.processor import Cell
from app.worker import CLEAR_CYCLES_TO_CANCEL, decide_notification


def _cell(intensity: str, eta: float = 20.0, dist: float = 30.0) -> Cell:
    return Cell(
        intensity=intensity,
        peak_mmh={"moderada": 5.0, "forte": 20.0, "muito_forte": 70.0}[intensity],
        distance_km=dist,
        bearing_deg=270,
        speed_kmh=30,
        approaching=True,
        eta_minutes=eta,
        cell_key="k",
    )


def test_entrada_gera_um_alerta():
    d = decide_notification(prev_level=None, clear_cycles=0, threats=[_cell("moderada")])
    assert d.action == "alert"
    assert d.state_level == "moderada"


def test_nao_repete_mesma_intensidade():
    # Já notificado moderada; a chuva continua moderada e mais perto -> sem novo push.
    d = decide_notification("moderada", 0, [_cell("moderada", eta=10, dist=15)])
    assert d.action == "none"
    assert d.state_level == "moderada"


def test_agravamento_gera_aviso():
    d = decide_notification("moderada", 0, [_cell("forte")])
    assert d.action == "escalate"
    assert d.state_level == "forte"


def test_enfraquecer_nao_notifica():
    d = decide_notification("forte", 0, [_cell("moderada")])
    assert d.action == "none"
    assert d.state_level == "forte"  # mantém o pico já avisado


def test_escala_progressiva_moderada_forte_muito_forte():
    # Sequência de uma tempestade que se aproxima e intensifica.
    s = decide_notification(None, 0, [_cell("moderada")])
    assert s.action == "alert"
    s = decide_notification(s.state_level, s.clear_cycles, [_cell("moderada")])
    assert s.action == "none"                      # não floodou
    s = decide_notification(s.state_level, s.clear_cycles, [_cell("forte")])
    assert s.action == "escalate"
    s = decide_notification(s.state_level, s.clear_cycles, [_cell("muito_forte")])
    assert s.action == "escalate"
    s = decide_notification(s.state_level, s.clear_cycles, [_cell("muito_forte")])
    assert s.action == "none"                      # estabilizou, sem repetir


def test_cancelamento_com_folga():
    # Ameaça some: 1º ciclo sem ameaça não cancela; atinge o limiar depois.
    d = decide_notification("forte", 0, threats=[])
    assert d.action == "none"
    assert d.clear_cycles == 1
    # Avança ciclos até o limiar.
    d = decide_notification("forte", CLEAR_CYCLES_TO_CANCEL - 1, threats=[])
    assert d.action == "cancel"
    assert d.state_level is None


def test_nova_chuva_apos_passar():
    d = decide_notification(prev_level=None, clear_cycles=0, threats=[_cell("forte")])
    assert d.action == "alert"


def test_chuva_passa_ceu_limpa_e_volta_notifica_de_novo():
    """forte -> céu limpa (cancela) -> fica sem chuva -> volta a chover (novo alerta)."""
    # 1) Chuva forte chega.
    s = decide_notification(None, 0, [_cell("forte")])
    assert s.action == "alert"

    # 2) Para de detectar; após a folga, cancela ("a chuva passou").
    s = decide_notification(s.state_level, s.clear_cycles, threats=[])
    assert s.action == "none" and s.clear_cycles == 1
    s = decide_notification(s.state_level, s.clear_cycles, threats=[])
    assert s.action == "cancel" and s.state_level is None

    # 3) Céu segue limpo por mais tempo — silêncio total.
    s = decide_notification(s.state_level, s.clear_cycles, threats=[])
    assert s.action == "none" and s.state_level is None

    # 4) A chuva volta -> DEVE notificar de novo (evento novo).
    s = decide_notification(s.state_level, s.clear_cycles, [_cell("moderada")])
    assert s.action == "alert"
    assert s.state_level == "moderada"
