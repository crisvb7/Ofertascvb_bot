import pytest

from ofertas.config import Tienda
from ofertas.fuentes import chollometro
from ofertas.modelos import Anuncio

from test_fuentes import RSS

OVIEDO = (43.3614, -5.8494)
MADRID = (40.4168, -3.7038)


def wp(id_, titulo, precio, lugar=OVIEDO, envio=False, desc="", ciudad="Oviedo", img=None):
    return Anuncio(fuente="wallapop", id=id_, titulo=titulo, precio=precio,
                   url=f"https://es.wallapop.com/item/{id_}", descripcion=desc,
                   ciudad=ciudad, lat=lugar[0], lon=lugar[1], envio=envio, imagen=img)


C, D, F = "consola", "dudosa", None


@pytest.mark.parametrize("titulo,esperado", [
    ("PS5 Slim con lector", C),
    ("Playstation 5 digital + 2 mandos", C),
    ("Play 5 con 3 juegos", C),
    ("Sony PlayStation 5 825GB edición estándar", C),
    ("PS5 normal", C),
    ("Play station 5", C),
    ("PS5 Slim + GTA VI", C),
    ("Consola PS5 con mando", C),
    ("PS5 Slim - Très bon état", C),
    ("PS5 slim + 2 manettes", C),
    ("Ps5 Semi Nova", C),
    ("Ps5 slim 1Tb joystick", C),
    ("PlayStation 5 FAT Disco 825GB FW 13.60 + Pad Hall", C),
    ("PS5 (PlayStation 5) 825GB + Mando + Auriculares", C),
    ("PS5 FAT con lector + cambio Xbox Series X", C),
    ("PS5 slim acepto cambios", C),
    ("Consola PlayStation 5 Estándar 1TB E con Marvel Lobezno y Marvel's Spider-Man 2", C),
    # dudosas: te llegan al tema Revisar
    ("PS5 averiada", D),
    ("PlayStation 5 (safe mode)", D),
    ("PlayStation 5/GTA VI", D),
    ("Nieuwe GTA 6 controller PlayStation 5", D),
    ("PlayStation 5 veuillez bien lire la description", D),
    ("PlayStation 5 veuillez lire annonce", D),
    ("Playstation 5 1tb leggi descrizione", D),
    ("Mando DualSense + consola PS5 slim", D),
    # fuera
    ("PS5 Pro 2TB", F),
    ("PlayStation Portal para PS5", F),
    ("Funda para PS5", F),
    ("Busco PS5", F),
    ("PS VR2 para PS5", F),
    ("Volante G29 PS5/PS4", F),
    ("Volant ps5", F),
    ("Volant Thrustmaster T598 Direct Drive + pédales PS5/PC", F),
    ("Mando DualSense Edge PS5", F),
    ("Mando DualSense PS5 Edición Grand Theft Auto", F),
    ("Control DualSense Grand Theft Auto VI Nuevo", F),
    ("Mando Inalámbrico SCUF Omega para PS5 y PC", F),
    ("GTA VI Edición Coleccionista PS5", F),
    ("Juego Astro Bot PS5", F),
    ("Manette PS5 GTA 6 édition limitée", F),
    ("Cerco PS5", F),
    ("🎮 Concours pour gagner une PS5 🔥", F),
    ("Vendo Foto Playstation 5 fat A4", F),
    ("PS5 portable", F),
    ("Unidad de disco para consolas PlayStation 5 Edición Digital Slim", F),
    ("Cambio PlayStation 5 Pro por Xbox series x +400€", F),
    ("Lot de 7 jeux neuf ps5", F),
    ("Vários jogos playstation5 (sealed)", F),
    ("Lot indissociable manette ps5 GTA6", F),
    ("PS5 Controller GTA VI White limited edition", F),
    ("Sony PS5 DualSense Controller GTA VI 6 Limited Edition - Black & White", F),
    ("PS5 sans manette", C),
    ("Lot console PS5 slim + 2 manettes", D),
    ("PACK PlayStation 5 + mando inalámbrico + EA Sports FC27", C),
    ("Ps5 slim + câbles (lire la description )", D),
])
def test_clasifica_ps5(cfg, titulo, esperado):
    assert cfg.producto("PS5").clasificar(wp("1", titulo, 300))[0] == esperado


@pytest.mark.parametrize("titulo,esperado", [
    ("Xbox Series X 1TB", C),
    ("Xbox series X digital blanca", C),
    ("XSX con mando y juegos", C),
    ("Xbox Series X 1TO avec manette", C),
    ("Xbox Séries X", C),
    ("Xbox Series X + Controller a elegir", C),
    ("Cambio Xbox Series X por PS5", D),
    ("Xbox Series X (no incluye caja ni mando)", C),
    ("Xbox Series S 512GB", F),
    ("Forza Horizon Xbox Series X|S", F),
    ("Mando Elite Series 2 Xbox Series X", F),
    ("Xbox One X 1TB", F),
    ("PS5 FAT con lector + cambio Xbox Series X", F),     # es una PS5
])
def test_clasifica_xbox(cfg, titulo, esperado):
    assert cfg.producto("Xbox Series X").clasificar(wp("1", titulo, 300))[0] == esperado


def test_descripcion_excluye(cfg):
    p = cfg.producto("PS5")
    assert not p.coincide(wp("1", "PS5 Slim", 100, desc="Vendo solo la caja, la consola no"))
    assert p.coincide(wp("1", "PS5 Slim", 300, desc="Funciona perfecta, con su caja"))


def pasada(motor, anuncios, prod, fuente="wallapop"):
    motor.pendientes = []
    motor.procesar(anuncios, prod, fuente)
    motor._enviar_pendientes()


def test_una_a_una_ordenadas_con_ofertones(motor, avisador, cfg):
    ps5 = cfg.producto("PS5")
    primera = [wp("c", "PS5", 450), wp("a", "PS5 Slim", 360, img="https://cdn/a.jpg"), wp("x", "PS5 Slim", 700),
               wp("d", "Mando PS5", 40), wp("e", "PS5 Pro", 300), wp("b", "PS5 Digital", 370)]
    pasada(motor, primera, ps5)
    textos = [a.texto for a in avisador.avisos]
    assert len(textos) == 3                              # 700 € pasa del tope; mando y Pro fuera
    assert ["360 €" in textos[0], "370 €" in textos[1], "450 €" in textos[2]] == [True] * 3
    assert textos[0].startswith("🔥🔥 OFERTÓN") and textos[1].startswith("🔥🔥 OFERTÓN")
    assert textos[2].startswith("🏷️ PS5") and "70 € por encima de tu máximo (380 €)" in textos[2]
    assert avisador.avisos[0].imagen == "https://cdn/a.jpg"         # va con su foto
    assert '<a href="https://es.wallapop.com/item/a"><b>Ver en Wallapop</b></a>' in avisador.avisos[0].html

    # segunda pasada: los mismos más uno nuevo barato → solo el nuevo
    pasada(motor, primera + [wp("f", "PS5 con lector", 340, desc="impecable")], ps5)
    assert len(avisador.avisos) == 4
    assert "340 €" in avisador.avisos[3].texto and "OFERTÓN" in avisador.avisos[3].texto
    pasada(motor, primera, ps5)
    assert len(avisador.avisos) == 4


def test_solo_ofertones_si_se_configura(motor, avisador, cfg):
    cfg.avisar_todas = False
    pasada(motor, [wp("a", "PS5", 360), wp("b", "PS5", 450)], cfg.producto("PS5"))
    assert len(avisador.avisos) == 1 and "360 €" in avisador.avisos[0].texto


def test_maximo_por_pasada_deja_el_resto_para_la_siguiente(motor, avisador, cfg):
    cfg.max_por_pasada = 2
    anuncios = [wp(str(i), "PS5", 300 + i * 10) for i in range(5)]
    pasada(motor, anuncios, cfg.producto("PS5"))
    assert [a.texto.count("300 €") + a.texto.count("310 €") for a in avisador.avisos] == [1, 1]
    pasada(motor, anuncios, cfg.producto("PS5"))
    assert len(avisador.avisos) == 4 and "320 €" in avisador.avisos[2].texto


def test_bajada_de_precio(motor, avisador, cfg):
    ps5 = cfg.producto("PS5")
    pasada(motor, [wp("a", "PS5", 375)], ps5)
    pasada(motor, [wp("a", "PS5", 370)], ps5)   # baja 5 €: no
    pasada(motor, [wp("a", "PS5", 360)], ps5)   # baja 15 €: sí
    assert len(avisador.avisos) == 2
    assert "Ha bajado de 375 € a 360 €" in avisador.avisos[1].texto


def test_mediana_del_mercado(motor, avisador, cfg):
    ps5 = cfg.producto("PS5")
    cfg.avisar_todas = False
    mercado = [wp(f"m{i}", "PS5 Slim", 500 + (i % 3) * 10) for i in range(15)]
    pasada(motor, mercado, ps5)
    assert avisador.avisos == []                         # todos caros
    pasada(motor, [wp("x", "PS5 Slim", 390)], ps5)
    assert len(avisador.avisos) == 1
    t = avisador.avisos[0].texto
    assert "OFERTÓN" in t and "más barato que la mediana" in t
    assert "Mediana de segunda mano: 510 €" in t and "estafa" not in t
    pasada(motor, [wp("y", "PS5 Slim", 200)], ps5)
    assert "estafa" in avisador.avisos[-1].texto


def test_distancia_y_envio(motor, avisador, cfg):
    ps5 = cfg.producto("PS5")
    pasada(motor, [wp("lejos", "PS5", 300, MADRID, envio=False, ciudad="Madrid")], ps5)
    assert avisador.avisos == []
    pasada(motor, [wp("lejos2", "PS5", 300, MADRID, envio=True, ciudad="Madrid")], ps5)
    assert len(avisador.avisos) == 1
    assert "Madrid (" in avisador.avisos[0].texto and "con envío" in avisador.avisos[0].texto


def test_chollometro(motor, avisador, cfg):
    chollos = chollometro.parsear(RSS.encode())
    motor.pendientes = []
    for p in cfg.productos:
        motor.procesar(chollos, p, "chollometro")
    motor._enviar_pendientes()
    textos = [a.texto for a in avisador.avisos]
    assert len(textos) == 1                    # PS5 a 499,99 €; la Xbox de 1.049 € pasa del tope
    assert "OFERTÓN" in textos[0] and "499,99 €" in textos[0] and "MediaMarkt" in textos[0]
    assert "Por debajo de tu máximo (529 €)" in textos[0] and "Ver en Chollometro" in avisador.avisos[0].html
    assert avisador.avisos[0].imagen == "https://static.chollometro.com/a.jpg"


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
    assert n == 3                                        # 3 consolas (ps5, playstation 5, xbox)
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
    busquedas = sum(len(p.busquedas) for p in cfg.productos)
    assert n_wallapop == 7 * busquedas       # todas las búsquedas en cada ejecución
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
    assert "Chollometro: 4 chollos nuevos en el feed; por producto → PS5: 1, Xbox Series X: 1" in texto
    assert len(lineas) >= 5


def test_tiendas_de_segunda_mano_en_el_ciclo_y_fuera_de_la_mediana(cfg, estado, avisador, monkeypatch):
    from ofertas import motor as m
    cfg.fuentes.update(cex=True, cashconverters=True, wallapop=False, vinted=False, chollometro=False)
    def cex_falso(sesion, q):
        return [Anuncio(fuente="cex", id="C1", titulo="Playstation 5, 825GB, Blanca", precio=590,
                        url="https://es.webuy.com/product-detail?id=C1", ciudad="Tienda Oviedo")]
    def cash_falso(sesion, q):
        return [Anuncio(fuente="cashconverters", id="K1", titulo="Consola xbox series x 1tb", precio=399,
                        url="https://www.cashconverters.es/es/es/segunda-mano/K1.html")]
    monkeypatch.setattr(m.cex, "buscar", cex_falso)
    monkeypatch.setattr(m.cashconverters, "buscar", cash_falso)
    motor = m.Motor(cfg, estado, avisador, pausa=(0, 0))
    motor.ciclo(forzar=True)
    textos = [a.texto for a in avisador.avisos]
    assert any("CeX" in t and "590 €" in t and "Tienda Oviedo" in t for t in textos)
    assert any("Cash Converters" in t and "399 €" in t and "OFERTÓN" in t for t in textos)
    assert estado.mediana("PS5") == (None, 0)          # las tiendas no cuentan para la mediana
