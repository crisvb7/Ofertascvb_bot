"""Fichas de producto de tiendas: lee el precio y el stock de los datos estructurados
(JSON-LD de schema.org) que casi todas las tiendas incluyen para Google."""
from __future__ import annotations

import json
import re

from ..red import Bloqueado
from ..utiles import parsear_precio

_JSONLD = re.compile(
    r"<script[^>]*type=[\"']application/ld\+json[\"'][^>]*>(.*?)</script>", re.S | re.I)
_META = re.compile(r"<meta\s+[^>]*>", re.I)
_ATTR = re.compile(r"([\w:-]+)\s*=\s*[\"']([^\"']*)[\"']")
_ITEMPROP_PRECIO = re.compile(
    r"itemprop=[\"']price[\"'][^>]*content=[\"']([^\"']+)[\"']"
    r"|content=[\"']([^\"']+)[\"'][^>]*itemprop=[\"']price[\"']", re.I)

_SI = ("instock", "limitedavailability", "onlineonly", "instoreonly", "preorder", "presale", "backorder")
_NO = ("outofstock", "soldout", "discontinued")


def consultar(sesion, url: str) -> dict:
    r = sesion.get(url, timeout=25, headers={"Accept": "text/html,application/xhtml+xml"})
    if r.status_code in (403, 429, 503):
        raise Bloqueado(f"{url} respondió {r.status_code}")
    r.raise_for_status()
    return extraer(r.text)


def extraer(html: str) -> dict:
    """Devuelve {'precio', 'en_stock', 'nombre', 'imagen'} (lo que encuentre)."""
    res = {"precio": None, "en_stock": None, "nombre": None, "imagen": None}
    ofertas = []
    for bloque in _JSONLD.findall(html):
        try:
            datos = json.loads(bloque.strip())
        except ValueError:
            continue
        for obj in _objetos(datos):
            tipos = obj.get("@type")
            tipos = tipos if isinstance(tipos, list) else [tipos]
            if not ({"Product", "ProductGroup"} & {t for t in tipos if isinstance(t, str)}):
                continue
            res["nombre"] = res["nombre"] or obj.get("name")
            res["imagen"] = res["imagen"] or _imagen(obj.get("image"))
            for of in _lista(obj.get("offers")):
                if not isinstance(of, dict):
                    continue
                precio = of.get("price", of.get("lowPrice"))
                if precio is None and isinstance(of.get("priceSpecification"), dict):
                    precio = of["priceSpecification"].get("price")
                ofertas.append((parsear_precio(precio), _disponible(of.get("availability"))))

    validas = [(p, s) for p, s in ofertas if p is not None and p > 0]
    if validas:
        en_stock = [p for p, s in validas if s is True]
        res["precio"] = min(en_stock) if en_stock else min(p for p, _ in validas)
        estados = [s for _, s in validas if s is not None]
        res["en_stock"] = True if True in estados else (False if estados else None)

    if res["precio"] is None or res["nombre"] is None:
        metas = {}
        for etiqueta in _META.findall(html):
            attrs = dict((k.lower(), v) for k, v in _ATTR.findall(etiqueta))
            clave = attrs.get("property") or attrs.get("name") or attrs.get("itemprop")
            if clave and "content" in attrs:
                metas.setdefault(clave.lower(), attrs["content"])
        if res["precio"] is None:
            for k in ("product:price:amount", "og:price:amount", "price"):
                if metas.get(k):
                    res["precio"] = parsear_precio(metas[k])
                    break
        if res["precio"] is None:
            m = _ITEMPROP_PRECIO.search(html)
            if m:
                res["precio"] = parsear_precio(m.group(1) or m.group(2))
        if res["en_stock"] is None and metas.get("product:availability"):
            res["en_stock"] = _disponible(metas["product:availability"])
        res["nombre"] = res["nombre"] or metas.get("og:title")
        res["imagen"] = res["imagen"] or metas.get("og:image")
    return res


def _objetos(nodo):
    if isinstance(nodo, dict):
        yield nodo
        for v in nodo.values():
            if isinstance(v, (dict, list)):
                yield from _objetos(v)
    elif isinstance(nodo, list):
        for x in nodo:
            yield from _objetos(x)


def _lista(v):
    if v is None:
        return []
    return v if isinstance(v, list) else [v]


def _disponible(valor) -> bool | None:
    if not isinstance(valor, str):
        return None
    v = valor.rsplit("/", 1)[-1].replace(" ", "").lower()
    if any(x in v for x in _NO):
        return False
    if any(x in v for x in _SI) or v in ("in stock", "available"):
        return True
    return None


def _imagen(v) -> str | None:
    if isinstance(v, str):
        return v
    if isinstance(v, list) and v:
        return _imagen(v[0])
    if isinstance(v, dict):
        return v.get("url") or v.get("contentUrl")
    return None
