"""Chollometro: feed RSS de chollos nuevos (cubre Amazon, MediaMarkt, PcComponentes,
El Corte Inglés, PlayStation Direct, Carrefour, Game, AliExpress...)."""
from __future__ import annotations

import html
import re
import xml.etree.ElementTree as ET

from ..modelos import Anuncio
from ..red import Bloqueado
from ..utiles import parsear_precio, precio_en_texto

FEED_NUEVOS = "https://www.chollometro.com/rss/nuevos"
_ID = re.compile(r"-(\d+)/?$")
_ETIQUETAS = re.compile(r"<[^>]+>")


def leer(sesion, url: str = FEED_NUEVOS) -> list[Anuncio]:
    r = sesion.get(url, timeout=20,
                   headers={"Accept": "application/rss+xml, application/xml;q=0.9, */*;q=0.8"})
    if r.status_code in (403, 429):
        raise Bloqueado(f"Chollometro respondió {r.status_code}")
    r.raise_for_status()
    return parsear(r.content)


def parsear(xml: bytes | str) -> list[Anuncio]:
    raiz = ET.fromstring(xml)
    anuncios = []
    for item in raiz.iter("item"):
        titulo = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        guid = (item.findtext("guid") or link).strip()
        tienda = precio_txt = imagen = None
        for hijo in item:
            etiqueta = hijo.tag.rsplit("}", 1)[-1]
            if etiqueta == "merchant":                       # <pepper:merchant name= price=/>
                tienda = hijo.get("name") or None
                precio_txt = hijo.get("price") or None
            elif etiqueta in ("content", "thumbnail") and hijo.get("url") and not imagen:
                imagen = hijo.get("url")
        precio = parsear_precio(precio_txt) if precio_txt else precio_en_texto(titulo)
        desc = html.unescape(_ETIQUETAS.sub(" ", item.findtext("description") or ""))
        m = _ID.search(link)
        anuncios.append(Anuncio(
            fuente="chollometro",
            id=m.group(1) if m else guid,
            titulo=titulo,
            precio=precio,
            url=link or guid,
            nuevo=True,
            descripcion=" ".join(desc.split())[:500],
            imagen=imagen,
            tienda=tienda,
        ))
    return anuncios
