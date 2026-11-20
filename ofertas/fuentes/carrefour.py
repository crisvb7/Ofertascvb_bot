"""Carrefour: buscador de su web (Empathy). Incluye el marketplace, a veces con precios inflados."""
from __future__ import annotations

from ..modelos import Anuncio
from ..red import Bloqueado
from ..utiles import parsear_precio

URL = "https://api.empathy.co/search/v1/query/carrefour/search"
BASE = "https://www.carrefour.es"


def buscar(sesion, consulta: str) -> list[Anuncio]:
    r = sesion.get(URL, params={"query": consulta, "lang": "es", "rows": 24, "start": 0}, timeout=25,
                   headers={"Accept": "application/json", "Origin": BASE, "Referer": BASE + "/"})
    if r.status_code in (401, 403, 429):
        raise Bloqueado(f"Carrefour respondió {r.status_code}")
    r.raise_for_status()
    items = ((r.json().get("catalog") or {}).get("content")) or []
    return [a for a in map(a_anuncio, items) if a]


def a_anuncio(it: dict) -> Anuncio | None:
    if not isinstance(it, dict) or not it.get("product_id"):
        return None
    if it.get("stock") == 0:
        return None
    urls = it.get("urls") or {}
    ruta = urls.get("nonFood") or next(iter(urls.values()), "") if isinstance(urls, dict) else ""
    imagenes = it.get("image_path") or {}
    imagen = (imagenes.get("nonFood") if isinstance(imagenes, dict) else imagenes) or it.get("image_for_play_service")
    precio, antes = parsear_precio(it.get("active_price")), parsear_precio(it.get("list_price"))
    return Anuncio(
        fuente="carrefour",
        id=str(it["product_id"]),
        titulo=str(it.get("display_name") or "").strip(),
        precio=precio,
        url=BASE + ruta if ruta.startswith("/") else (ruta or BASE),
        nuevo=True,
        imagen=imagen,
        tienda="Carrefour",
        estado=f"antes {antes:.2f} €".replace(".", ",") if antes and precio and antes > precio + 0.5 else None,
    )
