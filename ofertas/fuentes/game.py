"""GAME: su búsqueda redirige a la categoría de consolas; se leen las fichas de la lista."""
from __future__ import annotations

import html
import re
from urllib.parse import parse_qs, urlparse

from ..modelos import Anuncio
from ..red import Bloqueado
from ..utiles import parsear_precio

BASE = "https://www.game.es"
_CARD = re.compile(r'<article class="ProductListCard-module[^"]*__card"')
_HREF = re.compile(r'href="(/[^"/]+/([A-Za-z0-9]+))"')
_TITULO = re.compile(r'<h3[^>]*>(.*?)</h3>', re.S)
_IMG = re.compile(r'<img[^>]*?src="([^"]+)"')
_PRECIO = re.compile(r'>\s*(\d{1,3}(?:\.\d{3})*,\d{2})\s*€\s*<')
_TAG = re.compile(r'Tag-module[^"]*"[^>]*>.*?<span[^>]*>([^<]+)</span>', re.S)
_USADO = re.compile(r"(?i)seminuev|segunda mano|reacondicionad|usad")


def buscar(sesion, consulta: str) -> list[Anuncio]:
    slug = re.sub(r"[^a-z0-9]+", "-", consulta.lower()).strip("-")
    r = sesion.get(f"{BASE}/buscar/{slug}", timeout=30, headers={"Accept": "text/html,application/xhtml+xml"})
    if r.status_code in (401, 403, 429):
        raise Bloqueado(f"GAME respondió {r.status_code}")
    r.raise_for_status()
    return parsear(r.text)


def parsear(pagina: str) -> list[Anuncio]:
    marcas = list(_CARD.finditer(pagina))
    anuncios, vistos = [], set()
    for i, m in enumerate(marcas):
        trozo = pagina[m.start():marcas[i + 1].start() if i + 1 < len(marcas) else len(pagina)]
        enlace, titulo = _HREF.search(trozo), _TITULO.search(trozo)
        if not enlace or not titulo:
            continue
        etiquetas = [html.unescape(t).strip() for t in _TAG.findall(trozo)]
        if any(t.lower().startswith("agotado") for t in etiquetas):
            continue
        precios = [p for p in (parsear_precio(x) for x in _PRECIO.findall(trozo)) if p]
        if not precios or enlace.group(2) in vistos:
            continue
        vistos.add(enlace.group(2))
        nombre = html.unescape(re.sub(r"<[^>]+>", "", titulo.group(1))).strip()
        img = _IMG.search(trozo)
        imagen = None
        if img:
            src = html.unescape(img.group(1))
            imagen = parse_qs(urlparse(src).query).get("url", [None])[0] or (BASE + src if src.startswith("/") else src)
        usado = bool(_USADO.search(nombre) or any(_USADO.search(t) for t in etiquetas))
        anuncios.append(Anuncio(
            fuente="game",
            id=enlace.group(2),
            titulo=nombre,
            precio=min(precios),
            url=BASE + enlace.group(1),
            nuevo=not usado,
            imagen=imagen,
            tienda="GAME",
            envio=True,
            estado=", ".join(etiquetas) or None,
        ))
    return anuncios
