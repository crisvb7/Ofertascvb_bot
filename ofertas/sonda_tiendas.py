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


def formatos2() -> None:
    s = sesion_navegador()
    h = {"Accept": "text/html,application/json;q=0.9,*/*;q=0.8"}
    for url in ("https://www.game.es/buscar/consola-ps5", "https://www.game.es/buscar/consola-xbox-series-x"):
        try:
            r = s.get(url, timeout=25, headers=h)
            t = r.text
            log.info("F2 game %s -> %s (%s)", url, r.status_code, str(r.url)[:100])
            i = t.find('ProductListCard-module')
            j = t.find('ProductListCard-module', i + 5000)
            log.info("F2 game card: %s", " ".join(t[max(0, i - 300):i + 4500].split())[:4000])
            hrefs = re.findall(r'href="(/[a-z0-9-]+/\d{5,7})"', t)
            log.info("F2 game %d enlaces de producto: %s", len(set(hrefs)), sorted(set(hrefs))[:12])
            m = re.search(r'self\.__next_f\.push', t)
            log.info("F2 game rsc=%s next_data=%s", bool(m), "__NEXT_DATA__" in t)
        except Exception as e:
            log.info("F2 game error %s", e)
    try:
        t = s.get(TIENDAS["elcorteingles"], timeout=25, headers=h).text
        for patron in (r'"price"\s*:', r'"final"\s*:', r'"name"\s*:\s*"Consola', r'__NUXT__|__INITIAL|window\.__'):
            for m in list(re.finditer(patron, t))[:2]:
                log.info("F2 eci [%s] …%s…", patron, " ".join(t[max(0, m.start() - 300):m.start() + 500].split()))
        arts = re.findall(r'<article[^>]*class="product_preview(?! skeleton)[^"]*"', t)
        log.info("F2 eci %d artículos no-esqueleto", len(arts))
        i = t.find('js_preview_image')
        log.info("F2 eci producto: %s", " ".join(t[max(0, i - 2500):i + 2500].split())[:4000])
    except Exception as e:
        log.info("F2 eci error %s", e)
    try:
        j = s.get(TIENDAS["carrefour_api"], timeout=25, headers=h).json()
        for it in ((j.get("catalog") or {}).get("content") or [])[:4]:
            log.info("F2 carref %s | %s | %s | %s | stock=%s | bundle=%s | %s", it.get("display_name"),
                     it.get("active_price"), it.get("list_price"), (it.get("urls") or {}).get("nonFood"),
                     it.get("stock"), it.get("is_bundle"), it.get("image_path"))
        log.info("F2 carref otras claves: %s", sorted(k for k in j.keys()))
    except Exception as e:
        log.info("F2 carref error %s", e)
