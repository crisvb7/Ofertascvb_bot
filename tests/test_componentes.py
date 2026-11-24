"""Piezas de PC: clasificación, un tema del grupo por pieza (nuevo y usado juntos) y fuentes."""
import pytest

from conftest import AvisadorFalso
from ofertas import avisos
from ofertas.fuentes import cashconverters, cex
from ofertas.modelos import Anuncio

from test_motor import pasada, wp

C, D, F = "consola", "dudosa", None     # "consola" = es el producto (la pieza, aquí)


@pytest.fixture
def grupo(cfg, estado):
    from ofertas.motor import Motor
    av = AvisadorFalso(con_grupo=True)
    # límites fijos para los tests (así se pueden cambiar los de config.yaml sin romperlos)
    limites = {"Ryzen 7 5700X3D": (150, 230, 180, 270, 360), "RX 9070": (380, 520, 450, 590, 750)}
    for p in cfg.productos:
        if p.nombre in limites:
            p.usado_min, p.usado_max, p.nuevo_min, p.nuevo_max, p.tope = limites[p.nombre]
    return Motor(cfg, estado, av, pausa=(0, 0)), av


def chollo(id_, titulo, precio, tienda="PcComponentes"):
    return Anuncio(fuente="chollometro", id=id_, titulo=titulo, precio=precio,
                   url=f"https://www.chollometro.com/ofertas/x-{id_}", nuevo=True, tienda=tienda)


def test_los_componentes_se_cargan_como_tales(cfg):
    piezas = [p.nombre for p in cfg.productos if p.es_componente]
    assert piezas == ["Ryzen 7 5700X3D", "Ryzen 7 5800X3D", "Ryzen 5 5600", "RX 9060 XT 16GB", "RX 9070"]
    assert not cfg.producto("PS5").es_componente


@pytest.mark.parametrize("producto,titulo,esperado", [
    ("Ryzen 7 5700X3D", "AMD Ryzen 7 5700X3D", C),
    ("Ryzen 7 5700X3D", "Procesador AMD Ryzen 7 5700X3D 3GHz Socket AM4", C),
    ("Ryzen 7 5700X3D", "Ryzen 7 5700x3d con disipador", C),          # accesorio en medio: vale
    ("Ryzen 7 5700X3D", "R7 5700X3D nuevo precintado", C),
    ("Ryzen 7 5700X3D", "Ryzen 7 5700X3D + placa B550", D),
    ("Ryzen 7 5700X3D", "Pack Ryzen 7 5700X3D y B550", D),
    ("Ryzen 7 5700X3D", "Cambio Ryzen 7 5700X3D por 5800X3D", D),
    ("Ryzen 7 5700X3D", "Ryzen 7 5700X3D usado para minar", D),
    ("Ryzen 7 5700X3D", "Disipador para Ryzen 7 5700X3D", F),
    ("Ryzen 7 5700X3D", "PC Gaming Ryzen 7 5700X3D RX 9070", F),
    ("Ryzen 7 5700X3D", "Torre gaming 5700x3d 32gb", F),
    ("Ryzen 7 5700X3D", "Portátil Ryzen 7 5700X3D", F),
    ("Ryzen 7 5700X3D", "Busco 5700X3D", F),
    ("Ryzen 7 5700X3D", "Ryzen 7 5700X", F),
    ("Ryzen 7 5700X3D", "Ryzen 7 5700X3D (caja vacía)", F),
    ("Ryzen 7 5800X3D", "AMD Ryzen 7 5800X3D 10th Anniversary", C),
    ("Ryzen 7 5800X3D", "Ryzen 7 5800X", F),
    ("Ryzen 5 5600", "AMD Ryzen 5 5600", C),
    ("Ryzen 5 5600", "Ryzen 5 5600X", C),
    ("Ryzen 5 5600", "R5 5600", C),
    ("Ryzen 5 5600", "Ryzen 5 5600G", F),
    ("Ryzen 5 5600", "Ryzen 5 5600X3D", F),
    ("Ryzen 5 5600", "AMD RX 5600 XT", F),                           # es una gráfica vieja
    ("RX 9060 XT 16GB", "Sapphire Pulse AMD Radeon RX 9060 XT 16GB", C),
    ("RX 9060 XT 16GB", "Radeon RX9060XT 16 GB", C),
    ("RX 9060 XT 16GB", "RX 9060 XT 8GB", F),
    ("RX 9060 XT 16GB", "XFX RX 9060XT 8G", F),
    ("RX 9070", "Sapphire Pulse Radeon RX 9070 16GB", C),
    ("RX 9070", "Radeon RX9070", C),
    ("RX 9070", "RX 9070 XT", F),
    ("RX 9070", "RX 9070XT Nitro+", F),
    ("RX 9070", "RX 9070 GRE 12GB", F),
    ("RX 9070", "Backplate RX 9070", F),
    ("RX 9070", "Juego gratis con RX 9070", F),
    ("PS5", "Cambio RX 9070 por PS5", F),                            # se vende la gráfica
])
def test_clasifica_componentes(cfg, producto, titulo, esperado):
    assert cfg.producto(producto).clasificar(wp("1", titulo, 300))[0] == esperado


def test_segunda_mano_va_a_su_tema(grupo, cfg):
    motor, av = grupo
    cpu = cfg.producto("Ryzen 7 5700X3D")
    pasada(motor, [wp("a", "AMD Ryzen 7 5700X3D", 220), wp("b", "Ryzen 7 5700X3D", 300),
                   wp("c", "Ryzen 7 5700X3D + placa B550", 340), wp("d", "Disipador 5700X3D", 160)], cpu)
    assert av.categorias == ["pc_ryzen-7-5700x3d"] * 3          # dudosa incluida; el disipador, fuera
    oferton, normal, dudosa = (a.texto for a in av.avisos)
    assert oferton.startswith("🔥🔥 OFERTÓN 🔥🔥\n🖥️ Ryzen 7 5700X3D · Wallapop · segunda mano")
    assert "70 € por encima de tu máximo (230 €)" in normal
    assert dudosa.startswith("❓ ¿ES LA PIEZA SUELTA? Revísalo tú")
    assert "consola" not in " ".join(a.texto.lower() for a in av.avisos)


def test_nuevos_van_al_tema_de_su_pieza_y_no_se_mezclan_con_las_consolas(grupo, cfg):
    motor, av = grupo
    chollos = [chollo("1", "Sapphire Pulse Radeon RX 9070 16GB", 579),
               chollo("2", "PowerColor Reaper RX 9070", 640),
               chollo("3", "RX 9070 XT Nitro+", 600),
               chollo("4", "PS5 Slim Digital", 399)]
    pasada(motor, chollos, cfg.producto("RX 9070"), fuente="chollometro")
    pasada(motor, chollos, cfg.producto("PS5"), fuente="chollometro")
    assert av.categorias == ["pc_rx-9070", "pc_rx-9070", "nueva_oferton"]
    assert av.avisos[0].texto.startswith("🔥🔥 OFERTÓN 🔥🔥\n🖥️ RX 9070 · Chollometro · nuevo")
    assert av.avisos[1].texto.startswith("💰 BUEN PRECIO\n🖥️ RX 9070")
    assert av.avisos[2].texto.startswith("🔥🔥 OFERTÓN 🔥🔥\n🎮 PS5")


def test_nuevo_y_usado_de_una_pieza_van_al_mismo_tema(grupo, cfg):
    motor, av = grupo
    gpu = cfg.producto("RX 9070")
    pasada(motor, [wp("u", "Sapphire Pulse RX 9070", 500)], gpu)
    pasada(motor, [chollo("1", "Radeon RX 9070", 560)], gpu, fuente="chollometro")
    assert av.categorias == ["pc_rx-9070", "pc_rx-9070"]
    assert "· segunda mano" in av.avisos[0].texto and "· nuevo" in av.avisos[1].texto


def test_un_tema_por_pieza_con_su_indice(grupo, cfg):
    motor, av = grupo
    pasada(motor, [wp("a", "Ryzen 7 5700X3D", 220)], cfg.producto("Ryzen 7 5700X3D"))
    gpu = cfg.producto("RX 9070")
    pasada(motor, [wp("u", "Sapphire Pulse RX 9070", 500)], gpu)
    pasada(motor, [chollo("1", "Radeon RX 9070", 560)], gpu, fuente="chollometro")
    motor._actualizar_indices()
    piezas = {k: v[0] for k, v in avisos.CATEGORIAS.items() if k.startswith("pc_")}
    assert piezas == {"pc_ryzen-7-5700x3d": "🖥️ Ryzen 7 5700X3D", "pc_ryzen-7-5800x3d": "🖥️ Ryzen 7 5800X3D",
                      "pc_ryzen-5-5600": "🖥️ Ryzen 5 5600", "pc_rx-9060-xt-16gb": "🖥️ RX 9060 XT 16GB",
                      "pc_rx-9070": "🖥️ RX 9070"}
    assert set(av.indices) == set(avisos.CATEGORIAS)                 # un índice por tema
    cpu = av.indices["pc_ryzen-7-5700x3d"]
    assert cpu.startswith("📌 <b>🖥️ Ryzen 7 5700X3D</b>") and "220 €</b> · ♻️ usada" in cpu
    idx = av.indices["pc_rx-9070"]
    assert "560 €</b> · 🆕 nueva" in idx and "500 €</b> · ♻️ usada" in idx
    assert "RX 9070" not in cpu


def test_seccion():
    assert avisos.seccion(True, "oferton", pieza="RX 9070") == "pc_rx-9070"
    assert avisos.seccion(False, "resto", dudosa=True, pieza="Ryzen 5 5600") == "pc_ryzen-5-5600"
    assert avisos.seccion(False, "resto", dudosa=True) == "revisar"
    assert avisos.seccion_pieza("RX 9060 XT 16GB") == "pc_rx-9060-xt-16gb"


def test_minimo_se_aplica_a_lo_enviado_en_temas_de_pc(grupo, cfg, estado):
    motor, av = grupo
    cpu = cfg.producto("Ryzen 7 5700X3D")
    pasada(motor, [wp("a", "Ryzen 7 5700X3D", 160)], cpu)
    cpu.usado_min = 170
    motor._quitar_baratos_enviados()
    assert av.borrados == [1]


def test_tiendas_buscan_la_pieza_sin_consola(cfg):
    from ofertas.motor import consultas_simples
    ps5, cpu = cfg.producto("PS5"), cfg.producto("Ryzen 7 5700X3D")
    assert consultas_simples("carrefour", ps5, True) == (["consola ps5"], {})
    assert consultas_simples("carrefour", cpu, True) == (["5700x3d"], {})
    assert consultas_simples("cex", cpu, False) == (["5700x3d"], {"solo_consolas": False})
    assert consultas_simples("cex", ps5, False) == (["ps5", "playstation 5"], {})


def test_cex_sin_filtro_de_consolas():
    h = {"boxId": "SGRA9070", "boxName": "AMD Radeon RX 9070 16GB", "sellPrice": 520,
         "categoryFriendlyName": "Tarjetas Gráficas PCI-E", "inStockOnline": True, "stores": []}
    assert cex.a_anuncio(h) is None                             # por defecto: solo consolas
    a = cex.a_anuncio(h, solo_consolas=False)
    assert a and a.precio == 520 and a.titulo == "AMD Radeon RX 9070 16GB"
    portatil = {**h, "categoryFriendlyName": "Portátiles Windows"}
    assert cex.a_anuncio(portatil, solo_consolas=False) is None


def test_cashconverters_sin_filtro_de_consolas():
    import html
    import json

    def tile(pid, nombre, categoria, precio):
        datos = html.escape(json.dumps({"name": nombre, "category": categoria, "price": precio}), quote=True)
        return (f'<div class="product-tile x" data-pid="{pid}" data-product-datalayer="{datos}">'
                f'<img class="tile-image" src="https://img/{pid}.jpg?d=small"></div>')

    pagina = (tile("1", "Procesador AMD Ryzen 7 5700X3D", "informatica/componentes/procesadores", 230)
              + tile("2", "Consola PS5 Slim", "videojuegos y consolas/consolas/ps5", 380))
    assert [a.titulo for a in cashconverters.parsear(pagina)] == ["Consola ps5 slim"]
    assert [a.titulo for a in cashconverters.parsear(pagina, solo_consolas=False)] == [
        "Procesador amd ryzen 7 5700x3d"]
