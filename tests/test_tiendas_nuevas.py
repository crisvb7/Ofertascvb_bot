"""Tiendas de primera mano: Carrefour, GAME y El Corte Inglés (estructuras vistas en sus webs)."""
import json

from ofertas.fuentes import carrefour, elcorteingles, game

from test_fuentes import Resp, SesionFalsa


def test_carrefour():
    datos = {"catalog": {"content": [
        {"product_id": "VC4A-31794263", "display_name": "Consola PlayStation 5 Estándar E 1TB - Blanco",
         "active_price": 549.0, "list_price": 649.99, "stock": 100,
         "urls": {"nonFood": "/consola-playstation-5-estandar-e-1tb-blanco/VC4A-31794263/p"},
         "image_path": {"nonFood": "https://static.carrefour.es/hd_350x_/x/654346_00_1.jpg"}},
        {"product_id": "AGOTADA", "display_name": "Consola PS5", "active_price": 500, "stock": 0, "urls": {}},
    ]}}
    s = SesionFalsa([Resp(datos=datos)])
    res = carrefour.buscar(s, "consola ps5")
    assert s.llamadas[0][1]["query"] == "consola ps5"
    assert len(res) == 1
    a = res[0]
    assert (a.precio, a.nuevo, a.tienda, a.estado) == (549.0, True, "Carrefour", "antes 649,99 €")
    assert a.url == "https://www.carrefour.es/consola-playstation-5-estandar-e-1tb-blanco/VC4A-31794263/p"
    assert a.imagen.endswith("654346_00_1.jpg")


def tarjeta(href, titulo, precio, etiqueta=None):
    tag = (f'<div class="Tag-module-scss-module__wR2UUq__tag"><svg></svg><span class="Text">{etiqueta}</span></div>'
           if etiqueta else "")
    return (f'<li><article class="ProductListCard-module-scss-module__VLNX9W__card"><a href="{href}">'
            f'<img alt="{titulo}" src="/_next/image?url=https%3A%2F%2Fmedia.game.es%2FCOVERV2%2F3D_L%2F269%2F269172.png&amp;w=3840&amp;q=75"/></a>'
            f'<a href="{href}"><h3 class="x">{titulo}</h3></a><div class="priceInfoSection">{tag}'
            f'<span class="Text">{precio}€</span></div></article></li>')


def test_game():
    pagina = (tarjeta("/consola-playstation-5-chassis-e-aon/269172", "Consola PlayStation 5 Chassis E AON", "549,95")
              + tarjeta("/consola-playstation-5-digital/269173", "Consola PlayStation 5 Digital", "499,95", "Agotado")
              + tarjeta("/playstation-5-seminuevo/S1", "PlayStation 5 Seminuevo", "399,95"))
    s = SesionFalsa([Resp(contenido=pagina.encode())])
    res = game.buscar(s, "consola ps5")
    assert s.llamadas[0][0] == "https://www.game.es/buscar/consola-ps5"
    assert [(a.id, a.precio, a.nuevo) for a in res] == [("269172", 549.95, True), ("S1", 399.95, False)]
    assert res[0].url == "https://www.game.es/consola-playstation-5-chassis-e-aon/269172"
    assert res[0].imagen == "https://media.game.es/COVERV2/3D_L/269/269172.png"


def test_elcorteingles():
    estado = {"_internals": {}, "store": {"search": {"products": [
        {"_uri": "/videojuegos/A200069099-consola-playstation-5-digital/", "_status": "ADD", "id": "A200069099",
         "title": "Consola PlayStation 5 Digital", "isRefurbished": False,
         "image": {"sources": {"big": "https://dam.elcorteingles.es/producto/www-001094481001207-00.jpg"}},
         "vendors": {"FlixMedia": {"flixPrice": "599.9"}}},
        {"_uri": "/videojuegos/A203921340-pack/", "_status": "SOLD_OUT", "id": "A203921340",
         "title": "PACK PlayStation 5", "vendors": {"FlixMedia": {"flixPrice": "699"}}},
    ]}}}
    pagina = f"<script>window.__MOONSHINE_STATE__ = {json.dumps(estado)};</script>"
    s = SesionFalsa([Resp(contenido=pagina.encode())])
    res = elcorteingles.buscar(s, "consola ps5")
    assert s.llamadas[0][1] == {"s": "consola ps5", "stype": "text_box"}
    assert len(res) == 1
    a = res[0]
    assert (a.id, a.precio, a.nuevo, a.tienda) == ("A200069099", 599.9, True, "El Corte Inglés")
    assert a.url == "https://www.elcorteingles.es/videojuegos/A200069099-consola-playstation-5-digital/"
