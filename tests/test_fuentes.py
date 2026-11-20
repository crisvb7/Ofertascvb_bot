import json

import pytest

from ofertas.fuentes import chollometro, tiendas, wallapop
from ofertas.fuentes.vinted import Vinted
from ofertas.red import Bloqueado
from ofertas.utiles import euros, parsear_precio

WALLAPOP_NUEVO = {
    "data": {"section": {"payload": {"items": [
        {"id": "abc1", "title": "PS5 Slim con lector + 2 mandos", "description": "Perfecta",
         "price": {"amount": 350, "currency": "EUR"}, "web_slug": "ps5-slim-abc1",
         "location": {"city": "Gijón", "latitude": 43.53, "longitude": -5.66},
         "reserved": {"flag": False},
         "shipping": {"item_is_shippable": True, "user_allows_shipping": False},
         "images": [{"urls": {"small": "s.jpg", "medium": "m.jpg", "big": "b.jpg"}}]},
        {"id": "abc6", "title": "PS5 reservada", "price": {"amount": 300, "currency": "EUR"},
         "reserved": {"flag": True}},
    ]}}},
    "meta": {"next_page": "tok123"},
}
WALLAPOP_ANTIGUO = {"search_objects": [
    {"id": "x9", "title": "Xbox Series X 1TB", "price": 399.0, "currency": "EUR",
     "web_slug": "xbox-x9", "location": {"city": "Oviedo", "latitude": 43.36, "longitude": -5.84},
     "flags": {"reserved": False}, "supports_shipping": True,
     "images": [{"original": "o.jpg", "medium": "m.jpg"}]},
]}


class Resp:
    def __init__(self, status=200, datos=None, contenido=b""):
        self.status_code = status
        self._datos = datos
        self.content = contenido
        self.text = contenido.decode() if isinstance(contenido, bytes) else contenido
        self.ok = status < 400

    def json(self):
        return self._datos

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


class SesionFalsa:
    def __init__(self, respuestas):
        self.respuestas = list(respuestas)
        self.llamadas = []

    def get(self, url, params=None, headers=None, timeout=None):
        self.llamadas.append((url, params, headers))
        return self.respuestas.pop(0)


def test_parsear_precio():
    assert parsear_precio("99,95€") == 99.95
    assert parsear_precio("1.299,00€") == 1299.0
    assert parsear_precio("1.299€") == 1299.0
    assert parsear_precio("549€") == 549.0
    assert parsear_precio("400.0") == 400.0
    assert parsear_precio("549.99") == 549.99
    assert parsear_precio("1,299.99") == 1299.99
    assert parsear_precio(350) == 350.0
    assert parsear_precio("GRATIS") == 0.0
    assert parsear_precio("") is None
    assert parsear_precio(None) is None
    assert euros(549) == "549 €"
    assert euros(1299.9) == "1.299,90 €"


def test_wallapop_formato_nuevo():
    s = SesionFalsa([Resp(datos=WALLAPOP_NUEVO)])
    res = wallapop.buscar(s, "ps5", 43.36, -5.84, precio_min=150)
    url, params, cab = s.llamadas[0]
    assert url == wallapop.URL_BUSQUEDA
    assert cab["X-Platform"] == "web"
    assert params["keywords"] == "ps5" and params["min_sale_price"] == 150
    a = res[0]
    assert (a.id, a.precio, a.ciudad, a.envio, a.reservado) == ("abc1", 350.0, "Gijón", False, False)
    assert a.url == "https://es.wallapop.com/item/ps5-slim-abc1"
    assert a.imagen == "m.jpg"
    assert res[1].reservado is True


def test_wallapop_paginacion(monkeypatch):
    s = SesionFalsa([Resp(datos=WALLAPOP_NUEVO), Resp(datos=WALLAPOP_ANTIGUO)])
    monkeypatch.setattr(wallapop.time, "sleep", lambda _: None)
    res = wallapop.buscar(s, "ps5", 0, 0, paginas=2)
    assert s.llamadas[1][1] == {"next_page": "tok123"}
    assert len(res) == 3


def test_wallapop_formato_antiguo():
    res = wallapop.buscar(SesionFalsa([Resp(datos=WALLAPOP_ANTIGUO)]), "xbox", 0, 0)
    a = res[0]
    assert (a.precio, a.envio, a.reservado, a.imagen) == (399.0, True, False, "m.jpg")


def test_wallapop_formato_desconocido_busca_la_lista():
    raro = {"resultado": {"bloques": [{"cosas": [{"id": 1, "title": "PS5", "price": 300}]}]}}
    assert wallapop.buscar(SesionFalsa([Resp(datos=raro)]), "ps5", 0, 0)[0].precio == 300


def test_wallapop_bloqueado():
    with pytest.raises(Bloqueado):
        wallapop.buscar(SesionFalsa([Resp(status=403)]), "ps5", 0, 0)


VINTED_HTML = """<div data-testid="product-item-id-111"><div data-testid="product-item-id-111--image">
<img src="https://images1.vinted.net/t/a/310x430/x.webp?s=1" alt="PS5 Slim con lector, Marca: Sony, Estado: Muy bueno, 380.00 €, 399.70 €" class="web_ui__Image__content" data-testid="product-item-id-111--image--img"/></div>
<a href="/items/111-ps5-slim?referrer=catalog" class="NoC3Da_new-item-box__overlay" data-testid="product-item-id-111--overlay-link" title="PS5 Slim con lector, Marca: Sony, Estado: Muy bueno, 380.00 €, 399.70 €" target="_self"></a></div>
<div data-testid="product-item-id-222"><img src="https://images1.vinted.net/t/b.webp" alt="Mando, PS5 &amp; cable, Estado: Bueno, 1.050,00 €" class="c" data-testid="product-item-id-222--image--img"/>
<a href="/items/222-mando?referrer=catalog" class="o" data-testid="product-item-id-222--overlay-link" title="Mando, PS5 &amp; cable, Estado: Bueno, 1.050,00 €"></a></div>"""


def test_vinted_lee_la_pagina_del_catalogo():
    s = SesionFalsa([Resp(contenido=VINTED_HTML.encode())])
    res = Vinted(s).buscar("ps5", 150)
    url, params, _ = s.llamadas[0]
    assert url == "https://www.vinted.es/catalog" and params["price_from"] == 150
    a, b = res
    assert (a.id, a.titulo, a.precio, a.precio_total, a.estado) == ("111", "PS5 Slim con lector", 380.0, 399.7, "Muy bueno")
    assert a.url == "https://www.vinted.es/items/111-ps5-slim" and a.imagen.startswith("https://images1.vinted.net/t/a/")
    assert (b.titulo, b.precio, b.precio_total) == ("Mando, PS5 & cable", 1050.0, None)


def test_vinted_bloqueado():
    with pytest.raises(Bloqueado):
        Vinted(SesionFalsa([Resp(status=403)])).buscar("ps5")


CEX_HIT = {"boxId": "SPS5825GBW003", "boxName": "Playstation 5, 825GB, Blanca, Rebajada", "sellPrice": 590,
           "categoryFriendlyName": "PS5 Consolas", "stores": ["Madrid Atocha", "Oviedo Uría"],
           "inStockOnline": 1, "ecomQuantity": 3, "Condición": ["Sin Caja"],
           "imageUrls": {"large": "https://es.static.webuy.com/product_images/Juegos/PS5 Consolas/SPS5825GBW003_l.jpg"},
           "firstStockInDate": "2026-11-19 10:00:00"}


class SesionPost(SesionFalsa):
    def post(self, url, data=None, headers=None, timeout=None):
        self.llamadas.append((url, json.loads(data), headers))
        return self.respuestas.pop(0)


def test_cex():
    from ofertas.fuentes import cex
    juego = {**CEX_HIT, "boxId": "J1", "categoryFriendlyName": "PS5 Juegos"}
    agotada = {**CEX_HIT, "boxId": "A1", "stores": [], "inStockOnline": 0, "ecomQuantity": 0}
    s = SesionPost([Resp(datos={"results": [{"hits": [CEX_HIT, juego, agotada]}]})])
    res = cex.buscar(s, "ps5")
    assert s.llamadas[0][1]["requests"][0]["indexName"] == "prod_cex_es"
    assert len(res) == 1
    a = res[0]
    assert (a.precio, a.ciudad, a.envio, a.estado) == (590.0, "Tienda Oviedo Uría", True, "Sin Caja")
    assert a.url == "https://es.webuy.com/product-detail?id=SPS5825GBW003"
    assert " " not in a.imagen and a.imagen.endswith("PS5%20Consolas/SPS5825GBW003_l.jpg")
    assert a.publicado is not None


CASH_HTML = """<div class="product-tile search-link" data-pid="CC100_E1_0" data-product-datalayer="{&quot;id&quot;:&quot;CC100_E1_0&quot;,&quot;name&quot;:&quot;consola ps5 sony playstation 5&quot;,&quot;category&quot;:&quot;videojuegos y consolas/ps5/consolas/playstation 5&quot;,&quot;price&quot;:594.95,&quot;variant&quot;:&quot;Bueno&quot;}">
<div class="image-container"><img loading="eager" class="tile-image" src="https://images.cashconverters.es/productslive/a_0.jpg?d=small" alt="x"/></div></div>
<div class="product-tile search-link" data-pid="CC1_J_0" data-product-datalayer="{&quot;name&quot;:&quot;juego ps5 gta&quot;,&quot;category&quot;:&quot;videojuegos y consolas/ps5/juegos&quot;,&quot;price&quot;:40}">
<img class="tile-image" src="https://images.cashconverters.es/b.jpg"/></div>"""


def test_cashconverters():
    from ofertas.fuentes import cashconverters
    s = SesionFalsa([Resp(contenido=CASH_HTML.encode())])
    res = cashconverters.buscar(s, "ps5")
    assert s.llamadas[0][1]["srule"] == "most-recent"
    assert len(res) == 1
    a = res[0]
    assert (a.titulo, a.precio, a.estado, a.ciudad) == ("Consola ps5 sony playstation 5", 594.95, "Bueno",
                                                       "1 unidad en tienda")
    assert a.url == "https://www.cashconverters.es/es/es/segunda-mano/CC100_E1_0.html"
    assert a.imagen == "https://images.cashconverters.es/productslive/a_0.jpg"


def test_cashconverters_agrupa_unidades_iguales():
    from ofertas.fuentes import cashconverters
    tile = CASH_HTML.split("</div></div>")[0] + "</div></div>"
    otra = tile.replace("CC100_E1_0", "PT006_E2_0")
    barata = tile.replace("CC100_E1_0", "X1").replace("594.95", "399")
    res = cashconverters.parsear(tile + otra + barata)
    assert sorted((a.precio, a.ciudad) for a in res) == [(399.0, "1 unidad en tienda"), (594.95, "2 unidades en tiendas")]
    assert len({a.id for a in res}) == 2 and all(a.id.startswith("g") for a in res)


RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:media="http://search.yahoo.com/mrss/" xmlns:pepper="https://www.pepper.com/rss"
     xmlns:content="http://purl.org/rss/1.0/modules/content/">
<channel><title>Chollometro</title><link>https://www.chollometro.com</link><description>x</description>
<item><category><![CDATA[Gaming]]></category><pepper:merchant name="MediaMarkt" price="499,99€"/>
<media:content medium="image" url="https://static.chollometro.com/a.jpg" width="150" height="150"/>
<title><![CDATA[PS5 Slim con lector 1TB]]></title>
<description><![CDATA[<strong>499,99€ - MediaMarkt</strong><br />Buen precio &amp; envío]]></description>
<link>https://www.chollometro.com/ofertas/ps5-slim-2077100</link>
<pubDate>Thu, 19 Nov 2026 08:01:39 +0100</pubDate>
<guid>https://www.chollometro.com/ofertas/ps5-slim-2077100</guid></item>
<item><title><![CDATA[Ghost of Yotei PS5 por 39,95€]]></title>
<link>https://www.chollometro.com/ofertas/ghost-2077101</link></item>
<item><pepper:merchant name="Amazon" price="1.049,00€"/><title><![CDATA[Xbox Series X 1TB]]></title>
<link>https://www.chollometro.com/ofertas/xbox-2077102</link></item>
<item><pepper:merchant name="Game" price="99,95€"/><title><![CDATA[Tarjeta MicroSD Express]]></title>
<link>https://www.chollometro.com/ofertas/microsd-2077177</link></item>
</channel></rss>"""


def test_chollometro_rss():
    res = chollometro.parsear(RSS.encode())
    assert len(res) == 4
    a = res[0]
    assert (a.id, a.precio, a.tienda, a.nuevo) == ("2077100", 499.99, "MediaMarkt", True)
    assert a.imagen == "https://static.chollometro.com/a.jpg"
    assert "Buen precio & envío" in a.descripcion
    assert res[1].precio == 39.95          # precio sacado del título
    assert res[2].precio == 1049.0


HTML_TIENDA = """<html><head>
<meta property="og:title" content="Consola Xbox Series X 1TB">
<script type="application/ld+json">{"@context":"https://schema.org","@graph":[
 {"@type":"BreadcrumbList"},
 {"@type":"Product","name":"Microsoft Xbox Series X 1TB","image":["https://img/x.jpg"],
  "offers":{"@type":"Offer","price":"%s","priceCurrency":"EUR","availability":"https://schema.org/%s"}}]}
</script></head><body></body></html>"""


def test_tienda_jsonld():
    r = tiendas.extraer(HTML_TIENDA % ("649.00", "InStock"))
    assert r == {"precio": 649.0, "en_stock": True, "nombre": "Microsoft Xbox Series X 1TB",
                 "imagen": "https://img/x.jpg"}
    assert tiendas.extraer(HTML_TIENDA % ("799.99", "OutOfStock"))["en_stock"] is False


def test_tienda_meta_sin_jsonld():
    html = ('<meta property="product:price:amount" content="549,99">'
            '<meta property="og:title" content="PS5 Slim">'
            '<meta property="product:availability" content="in stock">')
    r = tiendas.extraer(html)
    assert (r["precio"], r["nombre"], r["en_stock"]) == (549.99, "PS5 Slim", True)


def test_tienda_varias_ofertas_coge_la_mas_barata_con_stock():
    datos = {"@type": "Product", "name": "PS5", "offers": [
        {"price": 500, "availability": "OutOfStock"},
        {"price": 560, "availability": "InStock"},
        {"price": 600, "availability": "InStock"}]}
    html = f'<script type="application/ld+json">{json.dumps(datos)}</script>'
    r = tiendas.extraer(html)
    assert (r["precio"], r["en_stock"]) == (560.0, True)
