import pytest

from ofertas.config import Tienda
from ofertas.fuentes import chollometro
from ofertas.modelos import Anuncio

from test_fuentes import RSS

OVIEDO = (43.3614, -5.8494)
MADRID = (40.4168, -3.7038)


def wp(id_, titulo, precio, lugar=OVIEDO, envio=False, desc="", ciudad="Oviedo"):
    return Anuncio(fuente="wallapop", id=id_, titulo=titulo, precio=precio,
                   url=f"https://es.wallapop.com/item/{id_}", descripcion=desc,
                   ciudad=ciudad, lat=lugar[0], lon=lugar[1], envio=envio)


@pytest.mark.parametrize("titulo,esperado", [
    ("PS5 Slim con lector", True),
    ("Playstation 5 digital + 2 mandos", True),
    ("Play 5 con 3 juegos", True),
    ("Sony PlayStation 5 825GB edición estándar", True),
    ("PS5 Pro 2TB", False),
    ("PlayStation Portal para PS5", False),
    ("Funda para PS5", False),
    ("Busco PS5", False),
    ("PS VR2 para PS5", False),
    ("Volante G29 PS5/PS4", False),
    ("Mando DualSense Edge PS5", False),
    ("PS5 averiada", False),
])
def test_coincide_ps5(cfg, titulo, esperado):
    assert cfg.producto("PS5").coincide(wp("1", titulo, 300)) is esperado


@pytest.mark.parametrize("titulo,esperado", [
    ("Xbox Series X 1TB", True),
    ("Xbox series X digital blanca", True),
    ("XSX con mando y juegos", True),
    ("Xbox Series S 512GB", False),
    ("Forza Horizon Xbox Series X|S", False),
    ("Mando Elite Series 2 Xbox Series X", False),
    ("Xbox One X 1TB", False),
])
def test_coincide_xbox(cfg, titulo, esperado):
    assert cfg.producto("Xbox Series X").coincide(wp("1", titulo, 300)) is esperado


def test_descripcion_excluye(cfg):
    p = cfg.producto("PS5")
    assert not p.coincide(wp("1", "PS5 Slim", 100, desc="Vendo solo la caja, la consola no"))
    assert p.coincide(wp("1", "PS5 Slim", 300, desc="Funciona perfecta, con su caja"))


def test_calentamiento_y_despues_avisos(motor, avisador, cfg):
    ps5 = cfg.producto("PS5")
    primera = [wp("a", "PS5 Slim", 360), wp("b", "PS5 Digital", 370), wp("c", "PS5", 450),
               wp("d", "Mando PS5", 40), wp("e", "PS5 Pro", 300)]
    motor.procesar(primera, ps5, "wallapop")
    assert len(avisador.avisos) == 1                    # un único resumen
    resumen = avisador.avisos[0].texto
    assert "2 ofertas" in resumen and "360 €" in resumen and "450 €" not in resumen

    # segunda pasada: los mismos más uno nuevo barato
    motor.procesar(primera + [wp("f", "PS5 con lector", 340, desc="impecable")], ps5, "wallapop")
    assert len(avisador.avisos) == 2
    aviso = avisador.avisos[1]
    assert "340 €" in aviso.texto and "Por debajo de tu máximo (380 €)" in aviso.texto
    assert '<a href="https://es.wallapop.com/item/f">' in aviso.html

    # y nada más si no cambia nada
    motor.procesar(primera, ps5, "wallapop")
    assert len(avisador.avisos) == 2


def test_bajada_de_precio(motor, avisador, cfg, estado):
    ps5 = cfg.producto("PS5")
    estado.marcar_calentado("wallapop:PS5")
    motor.procesar([wp("a", "PS5", 375)], ps5, "wallapop")
    motor.procesar([wp("a", "PS5", 370)], ps5, "wallapop")   # baja 5 €: no
    motor.procesar([wp("a", "PS5", 360)], ps5, "wallapop")   # baja 15 €: sí
    assert len(avisador.avisos) == 2
    assert "Ha bajado de 375 € a 360 €" in avisador.avisos[1].texto


def test_mediana_del_mercado(motor, avisador, cfg, estado):
    ps5 = cfg.producto("PS5")
    estado.marcar_calentado("wallapop:PS5")
    mercado = [wp(f"m{i}", "PS5 Slim", 500 + (i % 3) * 10) for i in range(15)]
    motor.procesar(mercado, ps5, "wallapop")
    assert avisador.avisos == []                         # todos caros
    motor.procesar([wp("x", "PS5 Slim", 390)], ps5, "wallapop")
    assert len(avisador.avisos) == 1
    t = avisador.avisos[0].texto
    assert "más barato que la mediana" in t and "Mediana de segunda mano: 510 €" in t
    assert "estafa" not in t
    motor.procesar([wp("y", "PS5 Slim", 200)], ps5, "wallapop")
    assert "estafa" in avisador.avisos[-1].texto


def test_distancia_y_envio(motor, avisador, cfg, estado):
    ps5 = cfg.producto("PS5")
    estado.marcar_calentado("wallapop:PS5")
    motor.procesar([wp("lejos", "PS5", 300, MADRID, envio=False, ciudad="Madrid")], ps5, "wallapop")
    assert avisador.avisos == []
    motor.procesar([wp("lejos2", "PS5", 300, MADRID, envio=True, ciudad="Madrid")], ps5, "wallapop")
    assert len(avisador.avisos) == 1
    assert "Madrid (" in avisador.avisos[0].texto and "con envío" in avisador.avisos[0].texto


def test_chollometro(motor, avisador, cfg, estado):
    for p in cfg.productos:
        estado.marcar_calentado(f"chollometro:{p.nombre}")
    chollos = chollometro.parsear(RSS.encode())
    for p in cfg.productos:
        motor.procesar(chollos, p, "chollometro")
    assert len(avisador.avisos) == 1                    # solo la PS5 a 499,99 €
    t = avisador.avisos[0].texto
    assert "499,99 €" in t and "MediaMarkt" in t and "Por debajo de tu máximo (529 €)" in t


def test_tienda_precio_y_stock(motor, avisador, cfg):
    xbox = cfg.producto("Xbox Series X")
    t = Tienda(producto="Xbox Series X", nombre="MediaMarkt", url="https://tienda/x", avisar_stock=True)
    motor.procesar_tienda(t, xbox, {"precio": 799.99, "en_stock": False})
    assert avisador.avisos == []
    motor.procesar_tienda(t, xbox, {"precio": 799.99, "en_stock": True})
    assert "Vuelve a haber stock" in avisador.avisos[-1].texto
    motor.procesar_tienda(t, xbox, {"precio": 679.0, "en_stock": True})
    assert "Por debajo de tu máximo (699 €) y con stock" in avisador.avisos[-1].texto
    motor.procesar_tienda(t, xbox, {"precio": 679.0, "en_stock": True})
    assert len(avisador.avisos) == 2                    # no repite
    motor.procesar_tienda(t, xbox, {"precio": 749.0, "en_stock": True})
    motor.procesar_tienda(t, xbox, {"precio": 679.0, "en_stock": True})
    assert len(avisador.avisos) == 3                    # subió y volvió a bajar


def test_ciclo_completo_con_fuentes_simuladas(motor, avisador, monkeypatch):
    from ofertas import motor as m
    llamadas = []

    def falso_wallapop(sesion, q, lat, lon, pmin, paginas):
        llamadas.append(("wallapop", q, pmin))
        return [wp(f"{q}-1", "PS5 Slim" if "p" in q else "Xbox Series X", 300)]

    monkeypatch.setattr(m.wallapop, "buscar", falso_wallapop)
    monkeypatch.setattr(motor.vinted, "buscar", lambda q, pmin: llamadas.append(("vinted", q)) or [])
    monkeypatch.setattr(m.chollometro, "leer", lambda s, url: [])
    n = motor.ciclo(forzar=True)
    assert ("wallapop", "ps5", 150) in llamadas and ("wallapop", "xbox series x", 200) in llamadas
    assert ("vinted", "playstation 5") in llamadas
    assert n == 2                                        # dos resúmenes de primera pasada
    # ahora no le toca a nadie
    assert motor.ciclo() == 0


def test_fuente_bloqueada_baja_el_ritmo(motor, monkeypatch):
    from ofertas import motor as m
    from ofertas.red import Bloqueado

    def bloqueado(*a, **k):
        raise Bloqueado("403")

    monkeypatch.setattr(m.wallapop, "buscar", bloqueado)
    monkeypatch.setattr(motor.vinted, "buscar", lambda q, pmin: [])
    monkeypatch.setattr(m.chollometro, "leer", lambda s, url: [])
    motor.ciclo(forzar=True)
    assert motor.castigo["wallapop"] == 2 and motor.castigo["vinted"] == 1


def test_ritmo_y_fallos_sobreviven_entre_ejecuciones(cfg, estado, avisador, monkeypatch):
    """Simula GitHub Actions: un proceso nuevo cada 10 minutos con la misma BD."""
    from ofertas import motor as m
    from ofertas.red import Bloqueado
    reloj = {"t": 1_000_000.0}
    monkeypatch.setattr(m.time, "time", lambda: reloj["t"])
    monkeypatch.setattr(m.random, "uniform", lambda a, b: 1.0)
    llamadas = []

    def vinted_bloqueado(q, pmin):
        llamadas.append(("vinted", reloj["t"]))
        raise Bloqueado("403")

    monkeypatch.setattr(m.wallapop, "buscar", lambda *a, **k: llamadas.append(("wallapop", reloj["t"])) or [])
    monkeypatch.setattr(m.chollometro, "leer", lambda s, url: [])

    for _ in range(7):                       # 7 ejecuciones, una cada 10 min
        motor = m.Motor(cfg, estado, avisador, pausa=(0, 0))
        monkeypatch.setattr(motor.vinted, "buscar", vinted_bloqueado)
        motor.ciclo(margen=180)
        reloj["t"] += 600

    n_wallapop = sum(1 for f, _ in llamadas if f == "wallapop")
    n_vinted = sum(1 for f, _ in llamadas if f == "vinted")
    assert n_wallapop == 7 * 3               # 3 búsquedas en cada ejecución
    assert n_vinted == 3                     # bloqueado: a los 0, 20 y 60 min (freno x2, x4...)
    assert int(estado.leer("castigo:vinted")) > 1
    assert int(estado.leer("fallos:vinted")) >= 1


def test_avisa_si_una_fuente_falla_mucho_y_cuando_vuelve(motor, avisador, monkeypatch):
    from ofertas import motor as m
    from ofertas.red import Bloqueado
    estado = {"roto": True}

    def wallapop_inestable(*a, **k):
        if estado["roto"]:
            raise Bloqueado("403")
        return []

    monkeypatch.setattr(m.wallapop, "buscar", wallapop_inestable)
    monkeypatch.setattr(motor.vinted, "buscar", lambda q, pmin: [])
    monkeypatch.setattr(m.chollometro, "leer", lambda s, url: [])
    for _ in range(m.FALLOS_PARA_AVISAR + 2):
        motor.ciclo(forzar=True)
    avisos_wallapop = [a.texto for a in avisador.avisos if "wallapop" in a.texto]
    assert len(avisos_wallapop) == 1 and "fallando" in avisos_wallapop[0]
    estado["roto"] = False
    motor.ciclo(forzar=True)
    assert "vuelve a funcionar" in avisador.avisos[-1].texto


def test_diagnostico(cfg, avisador, monkeypatch):
    from ofertas import diagnostico as d
    from ofertas.red import Bloqueado

    def wallapop_falso(sesion, q, lat, lon, pmin):
        if "xbox" in q:
            return [wp("x1", "Xbox Series X 1TB", 420), wp("x2", "Mando Xbox Series X", 45)]
        return [wp("p1", "PS5 Slim", 360), wp("p2", "PS5 Slim lector", 330), wp("p3", "Funda PS5", 200)]

    class VintedBloqueado:
        def __init__(self, *a):
            pass

        def buscar(self, q, pmin):
            raise Bloqueado("Vinted respondió 403")

    monkeypatch.setattr(d.wallapop, "buscar", wallapop_falso)
    monkeypatch.setattr(d, "Vinted", VintedBloqueado)
    monkeypatch.setattr(d.chollometro, "leer", lambda s, url: chollometro.parsear(RSS.encode()))
    lineas = d.ejecutar(cfg, avisador)
    texto = avisador.avisos[0].texto
    assert "Wallapop · PS5: 3 anuncios recibidos, 2 válidos, el más barato 330 € (tu máximo: 380 €)" in texto
    assert "Wallapop · Xbox Series X: 2 anuncios recibidos, 1 válidos, el más barato 420 €" in texto
    assert "❌ Vinted: me bloquea (Vinted respondió 403)" in texto
    assert "Chollometro: 4 chollos nuevos en el feed; de consolas → PS5: 1, Xbox Series X: 1" in texto
    assert len(lineas) >= 5
