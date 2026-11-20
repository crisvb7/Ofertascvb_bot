"""TEMPORAL: comprueba qué tiendas responden desde aquí (solo escribe en el log)."""
from __future__ import annotations

import logging
import re

from .red import sesion_navegador

log = logging.getLogger(__name__)

TIENDAS = {
    "amazon": "https://www.amazon.es/s?k=consola+ps5",
    "mediamarkt": "https://www.mediamarkt.es/es/search.html?query=consola%20ps5",
    "pccomponentes": "https://www.pccomponentes.com/buscar/?query=consola%20ps5",
    "elcorteingles": "https://www.elcorteingles.es/search-nwx/1/?s=consola+ps5&stype=text_box",
    "carrefour_web": "https://www.carrefour.es/?q=consola+ps5",
    "carrefour_api": "https://api.empathy.co/search/v1/query/carrefour/search?query=consola%20ps5&lang=es&rows=12&start=0",
    "game": "https://www.game.es/buscar/consola-ps5",
    "fnac": "https://www.fnac.es/SearchResult/ResultList.aspx?Search=consola+ps5",
    "worten": "https://www.worten.es/search?query=consola%20ps5",
    "xtralife": "https://www.xtralife.com/busqueda?q=consola%20ps5",
    "psdirect": "https://direct.playstation.com/es-es/buy-consoles/playstation5-console",
    "xbox": "https://www.xbox.com/es-ES/consoles/xbox-series-x",
    "alcampo": "https://www.compraonline.alcampo.es/search?q=consola%20ps5",
    "toysrus": "https://www.toysrus.es/buscar?q=consola+ps5",
}
MARCAS = ("__NEXT_DATA__", "__NUXT__", "__INITIAL_STATE__", "__PRELOADED_STATE__", "application/ld+json",
          '"@type":"Product"', '"@type": "Product"', "captcha", "Just a moment", "Access Denied",
          "Pardon Our Interruption", "datadome", "Robot Check", "data-asin", '"price"', "itemprop=\"price\"")


def ejecutar() -> None:
    s = sesion_navegador()
    for nombre, url in TIENDAS.items():
        try:
            r = s.get(url, timeout=25, headers={"Accept": "text/html,application/json;q=0.9,*/*;q=0.8"})
            t = r.text or ""
            marcas = [m for m in MARCAS if m.lower() in t.lower()]
            euros = len(re.findall(r"\d+[,.]\d{2}\s?€|€\s?\d+", t))
            log.info("Tienda %-14s %s · %7d bytes · %3d precios€ · %s", nombre, r.status_code, len(t), euros, marcas)
            titulo = re.search(r"<title[^>]*>(.*?)</title>", t, re.S | re.I)
            log.info("Tienda %-14s  título: %s · url final: %s", nombre,
                     " ".join((titulo.group(1) if titulo else t[:120]).split())[:120], str(getattr(r, "url", ""))[:110])
        except Exception as e:
            log.info("Tienda %-14s error: %s", nombre, str(e)[:150])


def formatos() -> None:
    import json as _json
    s = sesion_navegador()
    h = {"Accept": "text/html,application/json;q=0.9,*/*;q=0.8"}

    def trozo(nombre, t, patron, ancho=700, n=2):
        for m in list(re.finditer(patron, t))[:n]:
            log.info("Fmt %-8s …%s…", nombre, " ".join(t[max(0, m.start() - 150):m.start() + ancho].split()))

    try:
        t = s.get(TIENDAS["elcorteingles"], timeout=25, headers=h).text
        trozo("eci", t, r"(?i)data-json|data-product|product_preview|js-product", 900, 2)
        trozo("eci", t, r"(?i)PlayStation\s?5[^<]{0,60}</", 500, 1)
    except Exception as e:
        log.info("Fmt eci error %s", e)
    try:
        j = s.get(TIENDAS["carrefour_api"], timeout=25, headers=h).json()
        cont = (j.get("catalog") or {}).get("content") or []
        log.info("Fmt carref %d items; claves=%s", len(cont), sorted(cont[0].keys()) if cont else None)
        for it in cont[:3]:
            log.info("Fmt carref %s", " ".join(_json.dumps({k: it.get(k) for k in it if k != "tagging"},
                                                              ensure_ascii=False)[:700].split()))
    except Exception as e:
        log.info("Fmt carref error %s", e)
    try:
        t = s.get(TIENDAS["game"], timeout=25, headers=h).text
        for b in re.findall(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', t, re.S)[:3]:
            log.info("Fmt game ld %s", " ".join(b[:600].split()))
        trozo("game", t, r"(?i)class=\"[^\"]*(product|item)[^\"]*\"[^>]*data-", 900, 1)
        trozo("game", t, r"\d+,\d{2}\s?€", 500, 1)
    except Exception as e:
        log.info("Fmt game error %s", e)
    try:
        t = s.get(TIENDAS["alcampo"], timeout=25, headers=h).text
        m = re.search(r"window\.__INITIAL_STATE__\s*=\s*", t)
        log.info("Fmt alcampo state en %s", m.start() if m else None)
        trozo("alcampo", t, r'"price"', 600, 2)
        for b in re.findall(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', t, re.S)[:2]:
            log.info("Fmt alcampo ld %s", " ".join(b[:500].split()))
    except Exception as e:
        log.info("Fmt alcampo error %s", e)
    for url in ("https://www.xtralife.com/buscar?q=consola%20ps5", "https://www.xtralife.com/buscador?q=consola+ps5",
                "https://www.xtralife.com/listado/consolas-ps5/1"):
        try:
            r = s.get(url, timeout=25, headers=h)
            log.info("Fmt xtralife %s %s %d bytes %d precios", url, r.status_code, len(r.text),
                     len(re.findall(r"\d+[,.]\d{2}\s?€", r.text)))
        except Exception as e:
            log.info("Fmt xtralife error %s", e)
