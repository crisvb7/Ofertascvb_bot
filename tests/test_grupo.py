"""Apartados en el grupo de Telegram: categorías, seguimiento de estado e índices."""
import time

import pytest

from conftest import AvisadorFalso
from ofertas import avisos
from ofertas.avisos import Aviso, Avisador, Telegram
from ofertas.utiles import hora_local

from test_motor import pasada, wp


@pytest.fixture
def grupo(cfg, estado):
    from ofertas.motor import Motor
    av = AvisadorFalso(con_grupo=True)
    return Motor(cfg, estado, av, pausa=(0, 0)), av


def test_categorias(grupo, cfg):
    motor, av = grupo
    ps5 = cfg.producto("PS5")
    mercado = [wp(f"m{i}", "PS5 Slim", 500 + (i % 3) * 10) for i in range(15)]   # mediana ~510
    pasada(motor, mercado, ps5)
    av.avisos.clear(); av.categorias.clear()
    pasada(motor, [wp("o", "PS5", 370), wp("b", "PS5", 470), wp("r", "PS5", 600)], ps5)
    assert av.categorias == ["oferton", "buen_precio", "resto"]
    assert av.avisos[0].texto.startswith("🔥🔥 OFERTÓN")
    assert av.avisos[1].texto.startswith("💰 BUEN PRECIO")
    assert av.avisos[2].texto.startswith("🏷️ PS5")


def test_marca_vendida_y_cambio_de_precio(grupo, cfg, estado, monkeypatch):
    from ofertas import motor as m
    motor, av = grupo
    pasada(motor, [wp("a", "PS5", 360), wp("b", "PS5", 400)], cfg.producto("PS5"))
    for clave in ("wallapop:a", "wallapop:b"):
        estado.actualizar_mensaje(clave, comprobado=time.time() - 3600)
    respuestas = {"a": ("vendida", None), "b": ("disponible", 380.0)}
    monkeypatch.setattr(m.wallapop, "estado", lambda s, iid: respuestas[iid])
    motor._comprobar_estados()
    ediciones = dict(av.ediciones)
    assert ediciones[1].startswith("❌ <b>YA NO ESTÁ DISPONIBLE</b>")
    assert "Precio actualizado: 380 €</b> (antes 400 €)" in ediciones[2]
    assert estado.mensaje("wallapop:a")["estado"] == "vendida"
    assert estado.mensaje("wallapop:b")["precio"] == 380
    # una vendida no se vuelve a comprobar
    estado.actualizar_mensaje("wallapop:b", comprobado=time.time() - 3600)
    av.ediciones.clear()
    motor._comprobar_estados()
    assert av.ediciones == []                       # b no ha cambiado; a ya no se mira


def test_indice_lo_mas_nuevo_arriba_y_vendidas_abajo(grupo, cfg, estado):
    motor, av = grupo
    ahora = time.time()
    viejo = wp("v", "PS5 vieja", 350); viejo.publicado = ahora - 7200
    nuevo = wp("n", "PS5 nueva", 370); nuevo.publicado = ahora - 60
    medio = wp("x", "PS5 vendida", 300); medio.publicado = ahora - 3600
    pasada(motor, [viejo, nuevo, medio], cfg.producto("PS5"))
    estado.actualizar_mensaje("wallapop:x", estado="vendida")
    motor._actualizar_indices()
    idx = av.indices["oferton"]
    assert idx.startswith("📌 <b>🔥 Ofertones</b> · lo más nuevo arriba")
    assert idx.index("PS5 nueva") < idx.index("PS5 vieja")          # lo más nuevo arriba
    assert "❌ <b>Ya no disponibles</b>" in idx and "<s>300 € · PS5 vendida</s>" in idx


def test_rebajada_marca_el_aviso_viejo(grupo, cfg):
    motor, av = grupo
    ps5 = cfg.producto("PS5")
    pasada(motor, [wp("a", "PS5", 400)], ps5)
    pasada(motor, [wp("a", "PS5", 385)], ps5)
    assert len(av.avisos) == 2
    assert av.ediciones[0][0] == 1 and "Ha bajado a 385 €" in av.ediciones[0][1]


def test_estrenar_grupo_reenvia_lo_publicado(cfg, estado):
    from ofertas.motor import Motor
    privado = Motor(cfg, estado, AvisadorFalso(), pausa=(0, 0))
    pasada(privado, [wp("a", "PS5", 360)], cfg.producto("PS5"))
    av = AvisadorFalso(con_grupo=True)
    motor = Motor(cfg, estado, av, pausa=(0, 0))
    motor._estrenar_grupo()
    pasada(motor, [wp("a", "PS5", 360)], cfg.producto("PS5"))
    assert len(av.avisos) == 1                      # vuelve a salir, ahora en el grupo
    motor._estrenar_grupo()
    pasada(motor, [wp("a", "PS5", 360)], cfg.producto("PS5"))
    assert len(av.avisos) == 1                      # solo la primera vez


def test_indice_no_pasa_del_limite():
    filas = [{"estado": "disponible", "precio": 300 + i, "producto": "PS5", "url": f"https://x/{i}",
              "titulo": "PS5 " * 20, "ciudad": "Oviedo", "publicado": time.time()} for i in range(200)]
    assert len(avisos.construir_indice("resto", filas, 3, max_disponibles=200)) <= 4000


def test_hora_local():
    ahora = 1795160000          # 20/11/2026 ~08:33 en Madrid
    assert hora_local(ahora - 60, ahora).startswith("hoy ")
    assert hora_local(ahora - 86400, ahora).startswith("ayer ")
    assert hora_local(ahora - 5 * 86400, ahora) == "15/11 " + hora_local(ahora - 5 * 86400, ahora)[6:]


# --- cliente de Telegram (sin red) ------------------------------------------------

class RespJSON:
    def __init__(self, datos, status=200):
        self._d, self.status_code, self.ok = datos, status, status < 400
        self.text = str(datos)

    def json(self):
        return self._d


class SesionTG:
    def __init__(self, respuestas):
        self.respuestas, self.llamadas = list(respuestas), []

    def post(self, url, json=None, timeout=None):
        self.llamadas.append((url.rsplit("/", 1)[-1], json))
        return RespJSON(self.respuestas.pop(0))


def tg(respuestas, monkeypatch):
    monkeypatch.setattr(avisos.time, "sleep", lambda _: None)
    t = Telegram("TOKEN", "655")
    t.s = SesionTG(respuestas)
    return t


def test_telegram_envia_foto_al_tema_y_reintenta_429(monkeypatch):
    t = tg([{"ok": False, "error_code": 429, "parameters": {"retry_after": 3}},
            {"ok": True, "result": {"message_id": 77}}], monkeypatch)
    ref = t.enviar(Aviso("<b>hola</b>", "hola", "https://img/x.jpg"), chat_id="-100123", thread_id=5)
    assert ref == {"chat_id": "-100123", "message_id": 77, "con_foto": True}
    metodo, datos = t.s.llamadas[-1]
    assert metodo == "sendPhoto" and datos["message_thread_id"] == 5 and datos["photo"] == "https://img/x.jpg"
    assert len(t.s.llamadas) == 2


def test_telegram_editar(monkeypatch):
    t = tg([{"ok": False, "description": "Bad Request: message is not modified"},
            {"ok": False, "description": "Bad Request: message to edit not found"},
            {"ok": False, "description": "Internal error"}], monkeypatch)
    assert t.editar("-1", 1, "x", True) is True
    assert t.editar("-1", 1, "x", False) is False
    assert t.editar("-1", 1, "x", False) is None
    assert t.s.llamadas[0][0] == "editMessageCaption" and t.s.llamadas[1][0] == "editMessageText"


def test_avisador_crea_temas_y_fija_indice(monkeypatch, estado):
    t = tg([{"ok": True, "result": {"message_thread_id": 11}},     # crea tema ofertones
            {"ok": True, "result": {"message_id": 1}},             # oferta
            {"ok": True, "result": {"message_id": 2}},             # índice
            {"ok": True, "result": True},                          # fijar
            {"ok": True, "result": {"message_id": 2}}],            # editar índice
           monkeypatch)
    av = Avisador([], telegram=t, grupo_id="-100123", estado=estado)
    ref = av.enviar_oferta(Aviso("<b>PS5</b>", "PS5"), "oferton")
    assert ref["message_id"] == 1 and estado.leer("tema:-100123:oferton") == "11"
    av.indice("oferton", "📌 índice v1")
    av.indice("oferton", "📌 índice v1")                         # igual: no hace nada
    av.indice("oferton", "📌 índice v2")
    metodos = [m for m, _ in t.s.llamadas]
    assert metodos == ["createForumTopic", "sendMessage", "sendMessage", "pinChatMessage", "editMessageText"]
    assert t.s.llamadas[2][1]["message_thread_id"] == 11
