"""Apartados en el grupo de Telegram: categorías, seguimiento de estado e índices."""
import time

import pytest

from conftest import AvisadorFalso
from ofertas import avisos
from ofertas.avisos import Aviso, Avisador, Telegram
from ofertas.modelos import Anuncio
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
    assert av.categorias == ["usada_oferton", "usada_buen_precio", "usada_resto"]
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
    idx = av.indices["usada_oferton"]
    assert idx.startswith("📌 <b>♻️ Segunda mano · 🔥 Ofertones</b> · lo más nuevo arriba")
    assert set(av.indices) == set(avisos.CATEGORIAS)                 # un índice por sección
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
    ref = av.enviar_oferta(Aviso("<b>PS5</b>", "PS5"), "usada_oferton")
    assert ref["message_id"] == 1 and estado.leer("tema:-100123:usada_oferton") == "11"
    av.indice("usada_oferton", "📌 índice v1")
    av.indice("usada_oferton", "📌 índice v1")                   # igual: no hace nada
    av.indice("usada_oferton", "📌 índice v2")
    metodos = [m for m, _ in t.s.llamadas]
    assert metodos == ["createForumTopic", "sendMessage", "sendMessage", "pinChatMessage", "editMessageText"]
    assert t.s.llamadas[2][1]["message_thread_id"] == 11


def test_nuevas_y_usadas_van_a_secciones_distintas(grupo, cfg):
    motor, av = grupo
    ps5 = cfg.producto("PS5")
    nueva = Anuncio(fuente="game", id="g1", titulo="Consola PlayStation 5", precio=499, nuevo=True,
                    url="https://www.game.es/x/g1", tienda="GAME")
    pasada(motor, [nueva, wp("u", "PS5 Slim", 350)], ps5)
    assert sorted(av.categorias) == ["nueva_oferton", "usada_oferton"]
    assert avisos.seccion(True, "resto") == "nueva_buen_precio"


def test_migracion_de_categorias_antiguas(tmp_path):
    from ofertas.estado import Estado
    ruta = str(tmp_path / "v1.db")
    e = Estado(ruta)
    e.db.execute("DELETE FROM meta WHERE k='migracion:secciones'")
    e.db.execute("INSERT INTO mensajes (clave, fuente, categoria, enviado) VALUES ('wallapop:1','wallapop','oferton',?)", (time.time(),))
    e.db.execute("INSERT INTO mensajes (clave, fuente, categoria, enviado) VALUES ('game:1','game','resto',?)", (time.time(),))
    e.guardar("indice:-100:oferton", "55")
    e.guardar("tema:-100:resto", "12")
    e.db.commit()
    e2 = Estado(ruta)
    cats = dict(e2.db.execute("SELECT clave, categoria FROM mensajes").fetchall())
    assert cats == {"wallapop:1": "usada_oferton", "game:1": "nueva_buen_precio"}
    assert e2.leer("indice:-100:usada_oferton") == "55" and e2.leer("tema:-100:usada_resto") == "12"


def test_preparar_temas_crea_los_que_faltan_y_renombra(monkeypatch, estado):
    n = len(avisos.CATEGORIAS)       # 6 de consolas + uno por pieza de PC (si ya se registraron)
    crea = [{"ok": True, "result": {"message_thread_id": 20 + i}} for i in range(n - 1)]
    # orden de las secciones: nueva_oferton, nueva_buen_precio, usada_oferton (ya existe: renombrar), ...
    respuestas = crea[:2] + [{"ok": True, "result": True}] + crea[2:]
    t = tg(respuestas, monkeypatch)
    av = Avisador([], telegram=t, grupo_id="-100123", estado=estado, temas={"usada_oferton": 3})
    av.preparar_temas()
    metodos = [m for m, _ in t.s.llamadas]
    assert metodos.count("createForumTopic") == n - 1 and metodos.count("editForumTopic") == 1
    nombres = [d["name"] for m, d in t.s.llamadas]
    assert "🆕 Nuevas · 🔥 Ofertones" in nombres and "♻️ Segunda mano · 🔥 Ofertones" in nombres
    av.preparar_temas()                                                           # segunda vez: nada
    assert len(t.s.llamadas) == n
    assert "❓ Revisar · ¿es consola?" in nombres


def test_dudosas_van_a_revisar_con_el_motivo(grupo, cfg):
    motor, av = grupo
    pasada(motor, [wp("d", "PlayStation 5 (safe mode)", 300), wp("c", "PS5 Slim 1TB", 350),
                   wp("x", "Volant ps5", 220)], cfg.producto("PS5"))
    assert sorted(av.categorias) == ["revisar", "usada_oferton"]
    dudosa = next(a for a, c in zip(av.avisos, av.categorias) if c == "revisar")
    assert dudosa.texto.startswith("❓ ¿ES UNA CONSOLA? Revísalo tú")
    assert "🤔 Dudo porque pone «safe mode»" in dudosa.texto


def test_reclasifica_lo_ya_enviado(grupo, cfg, estado):
    motor, av = grupo
    for clave, titulo in (("a", "Volant ps5"), ("b", "PlayStation 5/GTA VI"), ("c", "PS5 Slim 1TB")):
        a = wp(clave, titulo, 300)
        estado.guardar_mensaje(a, clave, "PS5", "usada_oferton",
                               {"chat_id": "-100123", "message_id": ord(clave), "con_foto": False}, "<b>orig</b>")
    motor._reclasificar_enviados()
    ediciones = dict(av.ediciones)
    assert ediciones[ord("a")].startswith("🚫 <b>NO ES UNA CONSOLA</b>")
    assert ediciones[ord("b")].startswith("❓ <b>PUEDE QUE NO SEA UNA CONSOLA</b>")
    assert ord("c") not in ediciones
    assert estado.mensaje("wallapop:a")["estado"] == "descartada"
    av.ediciones.clear()
    motor._reclasificar_enviados()
    assert av.ediciones == []                     # solo una vez
    motor._actualizar_indices()
    assert "Volant" not in av.indices["usada_oferton"]


def test_config_real_no_baja_de_300():
    from ofertas import config
    from conftest import RAIZ
    for p in config.cargar(RAIZ / "config.yaml").productos:
        if p.es_componente:            # las piezas de PC tienen sus propios precios
            assert 0 < p.usado_min < p.usado_max < p.tope and 0 < p.nuevo_min < p.nuevo_max < p.tope, p.nombre
            continue
        assert p.usado_min >= 300 and p.nuevo_min >= 300, p.nombre


def test_quita_lo_ya_enviado_por_debajo_del_minimo(grupo, cfg, estado):
    motor, av = grupo
    ps5 = cfg.producto("PS5")
    ps5.usado_min = ps5.nuevo_min = 300
    filas = (("a", 250, "usada_oferton", 1), ("b", 280, "revisar", 2), ("c", 299, "usada_oferton", 3),
             ("d", 300, "usada_oferton", 4), ("e", 260, "nueva_oferton", 5))
    for clave, precio, cat, mid in filas:
        estado.guardar_mensaje(wp(clave, "PS5 Slim 1TB", precio), clave, "PS5", cat,
                               {"chat_id": "-100123", "message_id": mid, "con_foto": False}, "<b>orig</b>")
    av.no_borrables = {3}                          # más de 48 h: Telegram no deja borrarlo
    motor._quitar_baratos_enviados()
    assert sorted(av.borrados) == [1, 2, 3, 5]
    assert [mid for mid, _ in av.ediciones] == [3]
    assert av.ediciones[0][1].startswith("🚫 <b>PRECIO POR DEBAJO DE 300 €</b>")
    assert estado.mensaje("wallapop:a")["estado"] == "borrada"
    assert estado.mensaje("wallapop:c")["estado"] == "descartada"
    assert estado.mensaje("wallapop:d")["estado"] == "disponible"
    av.borrados.clear()
    motor._quitar_baratos_enviados()
    assert av.borrados == []                       # una sola vez...
    ps5.usado_min = 310
    av.ediciones.clear()
    motor._quitar_baratos_enviados()
    assert av.borrados == [3, 4]                   # ...salvo que cambies el mínimo
    assert av.ediciones == []                      # el 3 ya estaba marcado: no se vuelve a editar
    motor._actualizar_indices()
    assert "300 €" not in av.indices.get("usada_oferton", "")


def test_no_manda_nada_por_debajo_de_300(grupo, cfg):
    motor, av = grupo
    ps5 = cfg.producto("PS5")
    ps5.usado_min = 300
    pasada(motor, [wp("x", "PS5 Slim 1TB", 299), wp("y", "PS5 Slim 1TB", 300)], ps5)
    assert len(av.categorias) == 1 and "300 €" in av.avisos[0].texto


def test_pone_el_nombre_del_grupo_una_vez(monkeypatch, estado):
    t = tg([{"ok": True, "result": True}], monkeypatch)
    av = Avisador([], telegram=t, grupo_id="-100123", estado=estado)
    av.nombrar_grupo("Ofertas")
    av.nombrar_grupo("Ofertas")                                  # ya lo tiene: no repite
    assert t.s.llamadas == [("setChatTitle", {"chat_id": "-100123", "title": "Ofertas"})]


def test_sin_permiso_para_el_nombre_avisa_una_vez(monkeypatch, estado):
    sin_permiso = {"ok": False, "description": "Bad Request: not enough rights to change chat title"}
    t = tg([sin_permiso, sin_permiso], monkeypatch)
    sistema = []
    av = Avisador([type("C", (), {"enviar": lambda self, a: sistema.append(a) or True})()],
                  telegram=t, grupo_id="-100123", estado=estado)
    av.nombrar_grupo("Ofertas")
    av.nombrar_grupo("Ofertas")                                  # antes de 1 h no lo reintenta
    assert len(t.s.llamadas) == 1
    estado.guardar("grupo_nombre_intento:-100123", time.time() - 3700)
    av.nombrar_grupo("Ofertas")                                  # lo reintenta, pero no vuelve a avisar
    assert len(t.s.llamadas) == 2 and len(sistema) == 1
    assert "Cambiar información del grupo" in sistema[0].texto


def test_config_tiene_nombre_de_grupo(cfg):
    assert cfg.telegram_nombre_grupo == "Ofertas"
