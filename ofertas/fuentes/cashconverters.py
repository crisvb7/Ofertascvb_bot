"""Cash Converters: lee los productos de su página de búsqueda (los más recientes primero)."""
from __future__ import annotations

import html
import json
import re

from ..modelos import Anuncio
from ..red import Bloqueado
from ..utiles import parsear_precio

BASE = "https://www.cashconverters.es"
_TILE = re.compile(r'class="product-tile[^"]*" data-pid="([^"]+)" data-product-datalayer="([^"]+)"')
_IMG = re.compile(r'class="tile-image" src="([^"]+)"')


def buscar(sesion, consulta: str) -> list[Anuncio]:
    r = sesion.get(f"{BASE}/es/es/search/", params={"q": consulta, "srule": "most-recent", "sz": 48},
                   timeout=30, headers={"Accept": "text/html,application/xhtml+xml"})
    if r.status_code in (401, 403, 429):
        raise Bloqueado(f"Cash Converters respondió {r.status_code}")
    r.raise_for_status()
    return parsear(r.text)


def parsear(pagina: str) -> list[Anuncio]:
    marcas = list(_TILE.finditer(pagina))
    anuncios = []
    for i, m in enumerate(marcas):
        fin = marcas[i + 1].start() if i + 1 < len(marcas) else len(pagina)
        trozo = pagina[m.end():fin]
        try:
            datos = json.loads(html.unescape(m.group(2)))
        except ValueError:
            continue
        tramos = str(datos.get("category") or "").lower().split("/")[1:]   # sin "videojuegos y consolas"
        nombre = str(datos.get("name") or "").lower()
        if not any("consola" in t for t in tramos) and not nombre.startswith("consola"):
            continue                          # fuera juegos, mandos y accesorios
        img = _IMG.search(trozo)
        pid = m.group(1)
        anuncios.append(Anuncio(
            fuente="cashconverters",
            id=pid,
            titulo=str(datos.get("name") or "").strip().capitalize(),
            precio=parsear_precio(datos.get("price")),
            url=f"{BASE}/es/es/segunda-mano/{pid}.html",
            imagen=html.unescape(img.group(1)).split("?")[0] if img else None,   # sin ?d=small: tamaño grande
            envio=True,
            estado=datos.get("variant") or None,
        ))
    return anuncios
