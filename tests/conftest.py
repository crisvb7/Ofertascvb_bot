import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from ofertas import config  # noqa: E402
from ofertas.estado import Estado  # noqa: E402


class AvisadorFalso:
    def __init__(self):
        self.avisos = []

    def enviar(self, aviso):
        self.avisos.append(aviso)
        return True


@pytest.fixture
def cfg(monkeypatch):
    for k in ("TELEGRAM_TOKEN", "TELEGRAM_CHAT_ID", "CALLMEBOT_TELEFONO", "CALLMEBOT_APIKEY"):
        monkeypatch.delenv(k, raising=False)
    c = config.cargar(RAIZ / "config.yaml")
    # Límites fijos para los tests: así puedes cambiar los precios de config.yaml sin romperlos.
    limites = {"PS5": (150, 380, 250, 529), "Xbox Series X": (200, 450, 300, 699)}
    for p in c.productos:
        if p.nombre in limites:
            p.usado_min, p.usado_max, p.nuevo_min, p.nuevo_max = limites[p.nombre]
    return c


@pytest.fixture
def estado():
    return Estado(":memory:")


@pytest.fixture
def avisador():
    return AvisadorFalso()


@pytest.fixture
def motor(cfg, estado, avisador):
    from ofertas.motor import Motor
    return Motor(cfg, estado, avisador, pausa=(0, 0))
