"""El Corte Inglés: los productos vienen en el estado que la página trae incrustado."""
from __future__ import annotations

import json
import re

from ..modelos import Anuncio
from ..red import Bloqueado
from ..utiles import parsear_precio

BASE = "https://www.elcorteingles.es"
_ESTADO = re.compile(r"window\.__MOONSHINE_STATE__\s*=\s*")


def buscar(sesion, consulta: str) -> list[Anuncio]:
    r = sesion.get(f"{BASE}/search-nwx/1/", params={"s": consulta, "stype": "text_box"}, timeout=30,
                   headers={"Accept": "text/html,application/xhtml+xml"})
    if r.status_code in (401, 403, 429):
        raise Bloqueado(f"El Corte Inglés respondió {r.status_code}")
    r.raise_for_status()
    return parsear(r.text)


def _productos(nodo, prof: int = 0):
    if prof > 14:
        return
    if isinstance(nodo, dict):
        if "_uri" in nodo and "_status" in nodo and "title" in nodo:
            yield nodo
            return
        for v in nodo.values():
            yield from _productos(v, prof + 1)
    elif isinstance(nodo, list):
        for v in nodo:
            yield from _productos(v, prof + 1)


def parsear(pagina: str) -> list[Anuncio]:
    m = _ESTADO.search(pagina)
    if not m:
        return []
    try:
        estado, _ = json.JSONDecoder().raw_decode(pagina[m.end():])
    except ValueError:
        return []
    anuncios, vistos = [], set()
    for p in _productos(estado):
        pid = str(p.get("id") or p["_uri"])
        if pid in vistos or str(p.get("_status")).upper() == "SOLD_OUT":
            continue
        vistos.add(pid)
        flix = ((p.get("vendors") or {}).get("FlixMedia") or {})
        precio = parsear_precio(flix.get("flixPrice"))
        if precio is None:
            continue
        img = p.get("image") or {}
        imagen = (img.get("sources") or {}).get("big") or img.get("default_source")
        anuncios.append(Anuncio(
            fuente="elcorteingles",
            id=pid,
            titulo=str(p.get("title") or "").strip(),
            precio=precio,
            url=BASE + str(p["_uri"]),
            nuevo=not bool(p.get("isRefurbished")),
            imagen=imagen,
            tienda="El Corte Inglés",
            envio=True,
        ))
    return anuncios
