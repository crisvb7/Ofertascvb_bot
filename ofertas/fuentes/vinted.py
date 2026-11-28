"""Vinted: lee la página de búsqueda del catálogo (su API interna ya no responde a anónimos).

Cada anuncio de la página trae en su imagen un texto así:
  "PS5 Slim con lector, Marca: Sony, Estado: Muy bueno, 380.00 €, 399.70 €"
(título, marca, estado, precio y precio con la protección al comprador).
"""
from __future__ import annotations
import math

import html
import re

from ..modelos import Anuncio
from ..red import Bloqueado
from ..utiles import parsear_precio

_IMG = re.compile(r'<img src="([^"]+)" alt="([^"]*)"[^>]*?data-testid="product-item-id-(\d+)--image--img"')
_ENLACE = re.compile(r'<a href="(/items/(\d+)[^"?]*)[^"]*"[^>]*?data-testid="product-item-id-\d+--overlay-link"[^>]*?title="([^"]*)"')
_PRECIOS = re.compile(r",\s*([\d.,]+)\s*€(?:,\s*([\d.,]+)\s*€)?\s*$")
_CAMPO = re.compile(r",\s*(Marca|Estado|Talla|Tamaño):\s*([^,]*)")


class Vinted:
    def __init__(self, sesion, dominio: str = "www.vinted.es"):
        self.s = sesion
        self.base = f"https://{dominio}"

    def buscar(self, consulta: str, precio_min: float | None = None,
               precio_max: float | None = None) -> list[Anuncio]:
        params = {"search_text": consulta, "order": "newest_first"}
        if precio_min:
            params.update(price_from=int(precio_min), currency="EUR")
        if precio_max:
            params.update(price_to=math.ceil(precio_max), currency="EUR")
        r = self.s.get(self.base + "/catalog", params=params, timeout=30,
                       headers={"Accept": "text/html,application/xhtml+xml"})
        if r.status_code in (401, 403, 429):
            raise Bloqueado(f"Vinted respondió {r.status_code}")
        r.raise_for_status()
        return parsear(r.text, self.base)


def parsear(pagina: str, base: str = "https://www.vinted.es") -> list[Anuncio]:
    fotos = {iid: src for src, _alt, iid in _IMG.findall(pagina)}
    anuncios, vistos = [], set()
    for ruta, iid, titulo_attr in _ENLACE.findall(pagina):
        if iid in vistos:
            continue
        vistos.add(iid)
        texto = html.unescape(titulo_attr)
        m = _PRECIOS.search(texto)
        if not m:
            continue
        precio, total = parsear_precio(m.group(1)), parsear_precio(m.group(2)) if m.group(2) else None
        resto = texto[:m.start()]
        campos = dict(_CAMPO.findall(resto))
        primer_campo = _CAMPO.search(resto)
        titulo = (resto[:primer_campo.start()] if primer_campo else resto).strip()
        anuncios.append(Anuncio(
            fuente="vinted",
            id=iid,
            titulo=titulo,
            precio=precio,
            url=base + ruta,
            imagen=html.unescape(fotos[iid]) if iid in fotos else None,
            envio=True,
            estado=campos.get("Estado"),
            precio_total=total,
        ))
    return anuncios
