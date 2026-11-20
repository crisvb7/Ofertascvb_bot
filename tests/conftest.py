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
    return config.cargar(RAIZ / "config.yaml")


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
