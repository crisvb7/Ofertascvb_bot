"""CeX (es.webuy.com): segunda mano con garantía. Usa el mismo buscador que su web."""
from __future__ import annotations

import json
from datetime import datetime
from urllib.parse import quote, urlencode

from ..modelos import Anuncio
from ..red import Bloqueado
from ..utiles import parsear_precio

URL = "https://search.webuy.io/1/indexes/*/queries"
INDICE = "prod_cex_es"
CABECERAS = {"Content-Type": "application/json; charset=UTF-8", "Accept": "application/json",
             "Origin": "https://es.webuy.com", "Referer": "https://es.webuy.com/"}


def buscar(sesion, consulta: str, por_pagina: int = 50, solo_consolas: bool = True) -> list[Anuncio]:
    """`solo_consolas=False` para piezas de PC: no filtra por la categoría de consolas."""
    params = urlencode({"query": consulta, "hitsPerPage": por_pagina, "page": 0,
                        "filters": "boxVisibilityOnWeb=1"})
    cuerpo = {"requests": [{"indexName": INDICE, "params": params}]}
    r = sesion.post(URL, data=json.dumps(cuerpo), headers=CABECERAS, timeout=25)
    if r.status_code in (401, 403, 429):
        raise Bloqueado(f"CeX respondió {r.status_code}")
    r.raise_for_status()
    hits = ((r.json().get("results") or [{}])[0]).get("hits") or []
    return [a for a in (a_anuncio(h, solo_consolas) for h in hits) if a]


def a_anuncio(h: dict, solo_consolas: bool = True) -> Anuncio | None:
    if not isinstance(h, dict) or not h.get("boxId"):
        return None
    categoria = str(h.get("categoryFriendlyName") or "").lower()
    if solo_consolas and "consola" not in categoria:   # fuera juegos, mandos y accesorios
        return None
    if not solo_consolas and any(x in categoria for x in ("portatil", "portátil", "consola", "juego")):
        return None                          # pieza de PC: fuera portátiles, consolas y juegos
    tiendas = [t.strip() for t in (h.get("stores") or []) if isinstance(t, str) and t.strip()]
    online = bool(h.get("inStockOnline")) or (h.get("ecomQuantity") or 0) > 0
    if not online and not tiendas:
        return None                          # sin stock en ningún sitio
    asturias = [t for t in tiendas if any(c in t.lower() for c in ("oviedo", "gijón", "gijon", "avilés", "aviles"))]
    if asturias:
        donde = "Tienda " + ", ".join(asturias[:2])
    elif tiendas:
        donde = f"{len(tiendas)} tiendas" + (" + online" if online else "")
    else:
        donde = "Online"
    imagenes = h.get("imageUrls") or {}
    imagen = imagenes.get("large") or imagenes.get("medium")
    publicado = None
    for campo in ("firstStockInDate", "firstStockDate", "timestamp"):
        try:
            publicado = datetime.fromisoformat(str(h[campo])).timestamp()
            break
        except (KeyError, ValueError, TypeError):
            continue
    condicion = h.get("Condición")
    return Anuncio(
        fuente="cex",
        id=str(h["boxId"]),
        titulo=str(h.get("boxName") or "").strip(),
        precio=parsear_precio(h.get("sellPrice")),
        url=f"https://es.webuy.com/product-detail?id={quote(str(h['boxId']))}",
        imagen=quote(imagen, safe=":/?=&%") if imagen else None,
        ciudad=donde,
        envio=online,
        estado=", ".join(condicion) if isinstance(condicion, list) else None,
        publicado=publicado,
    )
