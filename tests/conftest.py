import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from ofertas import config  # noqa: E402
from ofertas.estado import Estado  # noqa: E402


class AvisadorFalso:
    """Imita al Avisador: guarda lo que se enviaría, editaría o fijaría."""

    def __init__(self, con_grupo=False):
        self.avisos = []          # todo lo enviado (ofertas y sistema), en orden
        self.categorias = []      # categoría de cada oferta enviada
        self.ediciones = []       # (message_id, html)
        self.borrados = []        # message_id borrados
        self.no_borrables = set()  # message_id que Telegram no deja borrar (más de 48 h)
        self.indices = {}         # categoría -> html del índice
        self.con_grupo = con_grupo
        self.grupo_id = "-100123" if con_grupo else None
        self.grupo_pc_id = None
        self.movidos = {}         # categoría -> aviso de "se ha pasado al grupo de piezas"
        self._n = 0

    def enviar(self, aviso):
        self.avisos.append(aviso)
        return True

    def enviar_oferta(self, aviso, categoria):
        self.avisos.append(aviso)
        self.categorias.append(categoria)
        self._n += 1
        return {"chat_id": "-100123", "message_id": self._n, "con_foto": bool(aviso.imagen)}

    def editar(self, ref, html):
        self.ediciones.append((ref["message_id"], html))
        return True

    def borrar(self, ref):
        self.borrados.append(ref["message_id"])
        return ref["message_id"] not in self.no_borrables

    def indice(self, categoria, html):
        self.indices[categoria] = html

    def preparar_temas(self):
        self.temas_preparados = True

    def nombrar_grupo(self, nombre, grupo=None):
        self.nombre_grupo = nombre

    def indice_movido(self, categoria, html):
        self.movidos[categoria] = html


@pytest.fixture
def cfg(monkeypatch):
    for k in ("TELEGRAM_TOKEN", "TELEGRAM_CHAT_ID", "CALLMEBOT_TELEFONO", "CALLMEBOT_APIKEY"):
        monkeypatch.delenv(k, raising=False)
    c = config.cargar(RAIZ / "config.yaml")
    # Límites fijos para los tests: así puedes cambiar los precios de config.yaml sin romperlos.
    c.fuentes = {"wallapop": True, "vinted": True, "chollometro": True, "tiendas": True,
                 "cex": False, "cashconverters": False, "carrefour": False, "game": False,
                 "elcorteingles": False}
    c.avisar_todas, c.max_por_pasada = True, 25
    c.antifraude.activo = False          # cada test de antifraude lo enciende (sin red)
    limites = {"PS5": (150, 380, 250, 529, 650), "Xbox Series X": (200, 450, 300, 699, 800)}
    for p in c.productos:
        if p.nombre in limites:
            p.usado_min, p.usado_max, p.nuevo_min, p.nuevo_max, p.tope = limites[p.nombre]
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
