"""Wallapop: API interna de búsqueda que usa su propia web (no es pública ni oficial)."""
from __future__ import annotations

import random
import time

from ..modelos import Anuncio
from ..red import Bloqueado
from ..utiles import numero, parsear_precio

URL_BUSQUEDA = "https://api.wallapop.com/api/v3/search"
ultima_respuesta = None
CABECERAS = {
    "Accept": "application/json, text/plain, */*",
    "X-Platform": "web",   # obligatoria: sin ella la API responde 403
    "X-DeviceOS": "0",
    "Origin": "https://es.wallapop.com",
    "Referer": "https://es.wallapop.com/",
}


def buscar(sesion, consulta: str, lat: float, lon: float,
           precio_min: float | None = None, paginas: int = 1) -> list[Anuncio]:
    """Devuelve los anuncios más recientes para `consulta` (40 por página)."""
    params = {
        "keywords": consulta,
        "source": "search_box",
        "order_by": "newest",
        "latitude": lat,
        "longitude": lon,
    }
    if precio_min:
        params["min_sale_price"] = int(precio_min)

    anuncios: list[Anuncio] = []
    for pagina in range(max(1, paginas)):
        r = sesion.get(URL_BUSQUEDA, params=params, headers=CABECERAS, timeout=20)
        if r.status_code in (401, 403, 429):
            raise Bloqueado(f"Wallapop respondió {r.status_code}")
        r.raise_for_status()
        datos = r.json()
        global ultima_respuesta
        ultima_respuesta = datos          # para el diagnóstico
        anuncios += [a for a in map(a_anuncio, extraer_items(datos)) if a]
        siguiente = (datos.get("meta") or {}).get("next_page") if isinstance(datos, dict) else None
        if not siguiente or pagina + 1 >= paginas:
            break
        params = {"next_page": siguiente}
        time.sleep(random.uniform(1.5, 3.5))
    return anuncios


def extraer_items(datos) -> list[dict]:
    """La forma de la respuesta ha cambiado varias veces; probamos las conocidas."""
    rutas = (
        ("data", "section", "payload", "items"),
        ("data", "section", "items"),
        ("search_objects",),
        ("data", "items"),
        ("items",),
    )
    for ruta in rutas:
        nodo = datos
        for k in ruta:
            nodo = nodo.get(k) if isinstance(nodo, dict) else None
            if nodo is None:
                break
        if isinstance(nodo, list):
            return nodo
    return _buscar_lista(datos)


def _buscar_lista(nodo, prof: int = 0) -> list[dict]:
    if prof > 6:
        return []
    if isinstance(nodo, list):
        if nodo and all(isinstance(x, dict) for x in nodo) and any("id" in x and "title" in x for x in nodo):
            return nodo
        hijos = nodo
    elif isinstance(nodo, dict):
        hijos = nodo.values()
    else:
        return []
    for h in hijos:
        r = _buscar_lista(h, prof + 1)
        if r:
            return r
    return []


def a_anuncio(it: dict) -> Anuncio | None:
    if not isinstance(it, dict) or "id" not in it:
        return None
    precio_raw = it.get("price", it.get("sale_price"))
    if isinstance(precio_raw, dict):
        precio_raw = precio_raw.get("amount")
    slug = it.get("web_slug") or it.get("slug")
    loc = it.get("location") or {}
    reservado = it.get("reserved")
    if isinstance(reservado, dict):
        reservado = reservado.get("flag")
    if reservado is None:
        reservado = (it.get("flags") or {}).get("reserved")
    envio = it.get("shipping")
    if isinstance(envio, dict):
        envio = envio.get("user_allows_shipping", envio.get("item_is_shippable"))
    if envio is None:
        envio = it.get("supports_shipping")
    return Anuncio(
        fuente="wallapop",
        id=str(it["id"]),
        titulo=(it.get("title") or "").strip(),
        precio=parsear_precio(precio_raw),
        url=f"https://es.wallapop.com/item/{slug or it['id']}",
        descripcion=it.get("description") or "",
        imagen=_imagen(it),
        ciudad=loc.get("city") if isinstance(loc, dict) else None,
        lat=numero(loc.get("latitude")) if isinstance(loc, dict) else None,
        lon=numero(loc.get("longitude")) if isinstance(loc, dict) else None,
        envio=bool(envio) if envio is not None else None,
        reservado=bool(reservado),
        publicado=_segundos(it.get("created_at") or it.get("modified_at")),
    )


def _segundos(valor) -> float | None:
    n = numero(valor)
    if n is None:
        return None
    return n / 1000 if n > 1e11 else n      # Wallapop da milisegundos


def estado(sesion, item_id: str) -> tuple[str, float | None]:
    """('vendida', None) si el anuncio ya no existe; ('disponible'|'reservada', precio) si sigue."""
    r = sesion.get(f"https://api.wallapop.com/api/v3/items/{item_id}", headers=CABECERAS, timeout=20)
    if r.status_code in (404, 410):
        return "vendida", None
    if r.status_code in (401, 403, 429):
        raise Bloqueado(f"Wallapop (detalle) respondió {r.status_code}")
    r.raise_for_status()
    d = r.json() or {}
    precio = d.get("price")
    if isinstance(precio, dict):
        precio = (precio.get("cash") or precio).get("amount")
    reservado = d.get("reserved")
    if isinstance(reservado, dict):
        reservado = reservado.get("flag")
    if reservado is None:
        reservado = (d.get("flags") or {}).get("reserved")
    if (d.get("flags") or {}).get("sold") or d.get("sold"):
        return "vendida", parsear_precio(precio)
    return ("reservada" if reservado else "disponible"), parsear_precio(precio)


def _imagen(it: dict) -> str | None:
    imagenes = it.get("images") or []
    if not imagenes:
        return None
    primera = imagenes[0]
    if isinstance(primera, str):
        return primera
    if isinstance(primera, dict):
        urls = primera.get("urls") if isinstance(primera.get("urls"), dict) else primera
        for k in ("medium", "big", "original", "small", "url"):
            if isinstance(urls.get(k), str):
                return urls[k]
    return None
