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


def test_vinted_renueva_cookie_y_parsea():
    datos = {"items": [{"id": 123, "title": "PS5 Digital como nueva",
                        "price": {"amount": "360.0", "currency_code": "EUR"},
                        "total_item_price": {"amount": "378.7", "currency_code": "EUR"},
                        "url": "https://www.vinted.es/items/123-ps5",
                        "photo": {"url": "https://img/x.jpg"}, "status": "Muy bueno"}]}
    s = SesionFalsa([Resp(), Resp(status=401), Resp(), Resp(datos=datos)])
    v = Vinted(s)
    a = v.buscar("ps5", 150)[0]
    assert [ll[0] for ll in s.llamadas] == [
        "https://www.vinted.es/", "https://www.vinted.es/api/v2/catalog/items",
        "https://www.vinted.es/", "https://www.vinted.es/api/v2/catalog/items"]
    assert s.llamadas[1][1]["price_from"] == 150
    assert (a.precio, a.precio_total, a.estado, a.envio) == (360.0, 378.7, "Muy bueno", True)


def test_vinted_precio_antiguo_y_url_relativa():
    v = Vinted(None)
    a = v.a_anuncio({"id": 5, "title": "Xbox Series X", "price": "410.0", "url": "/items/5-x"})
    assert a.precio == 410.0 and a.url == "https://www.vinted.es/items/5-x"


def test_vinted_bloqueado():
    with pytest.raises(Bloqueado):
        Vinted(SesionFalsa([Resp(), Resp(status=403)])).buscar("ps5")


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
