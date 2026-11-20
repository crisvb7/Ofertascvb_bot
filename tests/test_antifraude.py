import io
import time

import pytest

from ofertas import antifraude
from ofertas.antifraude import Antifraude, distancia, huella
from ofertas.fuentes import wallapop
from ofertas.modelos import Anuncio

from conftest import AvisadorFalso
from test_motor import pasada, wp

PIL = pytest.importorskip("PIL")
from PIL import Image, ImageDraw  # noqa: E402

DIA = 86400
VETERANO = {"nombre": "Ana", "alta": time.time() - 900 * DIA, "valoraciones": 48, "nota": 4.9, "ventas": 35}


def foto(semilla: int, tam=(640, 480)) -> bytes:
    """Una 'foto' distinta para cada semilla."""
    im = Image.new("RGB", tam, (240, 240, 240))
    d = ImageDraw.Draw(im)
    for i in range(6):
        x = (semilla * 97 + i * 131) % tam[0]
        y = (semilla * 53 + i * 71) % tam[1]
        d.rectangle([x, y, x + 120, y + 90], fill=((semilla * 40 + i * 30) % 255, 60, 160))
    b = io.BytesIO()
    im.save(b, "JPEG", quality=85)
    return b.getvalue()


def reescalada(datos: bytes, ancho=320) -> bytes:
    im = Image.open(io.BytesIO(datos))
    im = im.resize((ancho, int(im.height * ancho / im.width)))
    b = io.BytesIO()
    im.save(b, "WEBP", quality=70)
    return b.getvalue()


def test_huella_igual_aunque_la_recompriman():
    a, b = huella(foto(1)), huella(reescalada(foto(1)))
    assert distancia(a, b) <= antifraude.PARECIDO_MAX
    assert distancia(a, huella(foto(2))) > antifraude.PARECIDO_MAX


@pytest.fixture
def af(cfg, estado, monkeypatch):
    cfg.antifraude.activo = True
    perfiles = {"veterano": dict(VETERANO)}
    llamadas = []

    def vendedor(_sesion, uid):
        llamadas.append(uid)
        return perfiles.get(uid)

    monkeypatch.setattr(wallapop, "vendedor", vendedor)
    fotos = {}
    filtro = Antifraude(cfg, estado, sesion=None, pausa=None)
    monkeypatch.setattr(filtro, "_descargar", lambda url: fotos.get(url))
    filtro.perfiles, filtro.fotos, filtro.llamadas = perfiles, fotos, llamadas
    return filtro


def anuncio(id_, vendedor="veterano", precio=350, img=None, fuente="wallapop", desc="", publicado=None):
    a = wp(id_, "PS5 Slim 1TB", precio, desc=desc, img=img)
    a.fuente, a.vendedor, a.publicado = fuente, vendedor, publicado or time.time()
    return a


def test_vendedor_con_valoraciones_pasa_y_se_muestra(af):
    rev = af.revisar(anuncio("1"))
    assert rev.motivo is None
    assert rev.vendedor.startswith("👤 48 valoraciones (4,9★) · en Wallapop desde ")
    af.revisar(anuncio("2"))
    assert af.llamadas == ["veterano"]              # el perfil se guarda: no se vuelve a pedir


def test_sin_valoraciones_fuera(af):
    af.perfiles["nuevo"] = {**VETERANO, "valoraciones": 0}
    assert af.revisar(anuncio("1", "nuevo")).motivo == "el vendedor no tiene ninguna valoración"


def test_cuenta_recien_creada_fuera(af):
    af.perfiles["reciente"] = {**VETERANO, "alta": time.time() - 3 * DIA, "valoraciones": 2}
    assert af.revisar(anuncio("1", "reciente")).motivo == "su cuenta se creó 3 días antes de publicar el anuncio"
    af.perfiles["hoy"] = {**VETERANO, "alta": time.time() - 3600, "valoraciones": 1}
    assert "el mismo día" in af.revisar(anuncio("2", "hoy")).motivo
    # se cuenta desde que publicó el anuncio, no desde hoy
    viejo = anuncio("3", "reciente", publicado=time.time() - 2 * DIA)
    assert "1 días antes" in af.revisar(viejo).motivo or "el mismo día" in af.revisar(viejo).motivo


def test_cuenta_borrada_fuera(af):
    assert af.revisar(anuncio("1", "desaparecido")).motivo == "el vendedor no tiene ninguna valoración"


def test_si_wallapop_no_responde_se_manda_avisando(af, monkeypatch):
    from ofertas.red import Bloqueado

    def falla(*_):
        raise Bloqueado("429")
    monkeypatch.setattr(wallapop, "vendedor", falla)
    rev = af.revisar(anuncio("1", "otro"))
    assert rev.motivo is None and "sin comprobar" in rev.vendedor


@pytest.mark.parametrize("texto,falso", [
    ("Escríbeme por WhatsApp", True),
    ("Pago solo bizum", True),
    ("Paypal amigos y lo envío", True),
    ("Llámame al 612 345 678", True),
    ("Contacto: 612345678", True),
    ("+34 699-123-456", True),
    ("escribe a vendo.ps5@gmail.com", True),
    ("No contesto por WhatsApp, solo por el chat", False),
    ("Nada de bizum, todo por Wallapop", False),
    ("Acepto bizum en mano", False),
    ("PS5 825 GB, firmware 9.60, 2 mandos", False),
    ("Precio 650 € negociable, 1 TB, 2 mandos y 3 juegos", False),
])
def test_frases_de_estafa(af, texto, falso):
    assert (af.revisar(anuncio("1", desc=texto)).motivo is not None) == falso


def test_foto_repetida_de_otro_vendedor_fuera(af):
    af.perfiles["ladron"] = dict(VETERANO)
    original = anuncio("orig", "veterano", img="u1", publicado=time.time() - DIA)
    copia = anuncio("copia", "ladron", precio=250, img="u2")
    af.fotos.update(u1=foto(7), u2=reescalada(foto(7)))
    af.registrar_foto(original)
    af.registrar_foto(copia)
    assert af.revisar(original).motivo is None                     # el primero es el original
    assert af.revisar(copia).motivo == "su foto ya salió en otro anuncio de Wallapop de otro vendedor (a 350 €)"


def test_foto_repetida_del_mismo_vendedor_pasa(af):
    af.fotos.update(u1=foto(7), u2=foto(7))
    for i, img in (("a", "u1"), ("b", "u2")):
        af.registrar_foto(anuncio(i, "veterano", img=img))
    assert af.revisar(anuncio("b", "veterano", img="u2")).motivo is None


def test_foto_repetida_sin_saber_el_vendedor(af):
    """Vinted no dice el vendedor: el mismo precio = la misma persona en otra web; mucho más barato = copia."""
    af.fotos.update(u1=foto(3), u2=foto(3), u3=foto(3))
    af.registrar_foto(anuncio("w", "veterano", precio=400, img="u1", publicado=time.time() - DIA))
    mismo = anuncio("v1", None, precio=390, img="u2", fuente="vinted")
    barato = anuncio("v2", None, precio=300, img="u3", fuente="vinted")
    for a in (mismo, barato):
        af.registrar_foto(a)
    assert af.revisar(mismo).motivo is None
    assert "foto ya salió" in af.revisar(barato).motivo
    assert "sin comprobar" in af.revisar(mismo).vendedor


def test_fotos_distintas_pasan(af):
    af.fotos.update(u1=foto(1), u2=foto(2))
    af.registrar_foto(anuncio("a", "veterano", img="u1"))
    af.registrar_foto(anuncio("b", "otro", img="u2"))
    af.perfiles["otro"] = dict(VETERANO)
    assert af.revisar(anuncio("b", "otro", img="u2")).motivo is None


def test_tiendas_no_se_revisan(af):
    a = anuncio("1", None, fuente="cex", desc="llama al 612345678")
    assert af.revisar(a).motivo is None and af.revisar(a).vendedor == ""


def test_el_motor_no_manda_los_falsos(cfg, estado, af):
    from ofertas.motor import Motor
    av = AvisadorFalso()
    motor = Motor(cfg, estado, av, pausa=(0, 0))
    motor.antifraude = af
    af.perfiles["sin"] = {**VETERANO, "valoraciones": 0}
    # la búsqueda viene de más nuevo a más antiguo: la copia (más nueva) antes que el original
    af.fotos.update(u1=foto(9), u2=foto(9))
    lista = [anuncio("copia", "sin2", precio=300, img="u2"),
             anuncio("bueno", "veterano", precio=360, img="u1", publicado=time.time() - DIA),
             anuncio("sinval", "sin", precio=340)]
    af.perfiles["sin2"] = dict(VETERANO)
    pasada(motor, lista, cfg.producto("PS5"))
    textos = [a.texto for a in av.avisos]
    assert len(textos) == 1 and "360 €" in textos[0]
    assert "👤 48 valoraciones (4,9★)" in textos[0]


def test_quita_lo_ya_enviado_que_parece_falso(cfg, estado, af, monkeypatch):
    from ofertas.motor import Motor
    av = AvisadorFalso(con_grupo=True)
    motor = Motor(cfg, estado, av, pausa=(0, 0))
    motor.antifraude = af
    af.perfiles["sin"] = {**VETERANO, "valoraciones": 0}
    duenos = {"m1": "sin", "m2": "veterano", "m3": "sin"}
    monkeypatch.setattr(wallapop, "dueno", lambda _s, iid: duenos.get(iid))
    for mid, iid in enumerate(("m1", "m2", "m3"), start=1):
        estado.guardar_mensaje(wp(iid, "PS5 Slim 1TB", 350), iid, "PS5", "usada_oferton",
                               {"chat_id": "-100123", "message_id": mid, "con_foto": False}, "<b>orig</b>")
    av.no_borrables = {3}
    motor._limpiar_falsos_enviados()
    assert sorted(av.borrados) == [1, 3]
    assert av.ediciones[0][0] == 3 and av.ediciones[0][1].startswith("🚫 <b>POSIBLE ANUNCIO FALSO</b>")
    assert estado.mensaje("wallapop:m1")["estado"] == "borrada"
    assert estado.mensaje("wallapop:m2")["estado"] == "disponible"
    assert estado.mensaje("wallapop:m3")["estado"] == "descartada"
    av.borrados.clear()
    motor._limpiar_falsos_enviados()
    assert av.borrados == []                    # cada aviso se revisa una sola vez


def test_wallapop_vendedor_lee_perfil_y_valoraciones(monkeypatch):
    monkeypatch.setattr(wallapop.time, "sleep", lambda _: None)

    class R:
        def __init__(self, codigo, datos):
            self.status_code, self._d = codigo, datos

        def json(self):
            return self._d

        def raise_for_status(self):
            pass

    class S:
        def get(self, url, **_):
            if url.endswith("/stats"):
                return R(200, {"ratings": [{"type": "reviews", "value": 98}], "rating_average": 4.9,
                               "counters": [{"type": "reviews", "value": 48}, {"type": "sells", "value": 35}]})
            if "/users/" in url:
                return R(200, {"micro_name": "Alan G.", "register_date": 1518422413000})
            return R(404, {})

    assert wallapop.vendedor(S(), "u") == {"nombre": "Alan G.", "alta": 1518422413.0, "valoraciones": 48,
                                           "nota": 4.9, "ventas": 35}
    a = wallapop.a_anuncio({"id": "x", "title": "PS5", "price": {"amount": 350}, "user_id": "abc"})
    assert isinstance(a, Anuncio) and a.vendedor == "abc"
