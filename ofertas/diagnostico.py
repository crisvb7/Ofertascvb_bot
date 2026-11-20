"""Diagnóstico: comprueba cada plataforma desde donde se ejecuta el bot y manda un informe.

No guarda nada ni cuenta como aviso: solo responde a "¿está conectado bien?"."""
from __future__ import annotations

import html
import logging

from . import avisos
from .config import Config, Producto
from .fuentes import chollometro, tiendas, wallapop
from .fuentes.vinted import Vinted
from .modelos import Anuncio
from .red import ERRORES_RED, MOTOR, Bloqueado, sesion_navegador
from .utiles import distancia_km, euros

log = logging.getLogger(__name__)


def _validos(anuncios: list[Anuncio], prod: Producto) -> list[Anuncio]:
    res = []
    for a in anuncios:
        pmin, _ = prod.limites(a.nuevo)
        if a.precio is None or a.reservado or not prod.coincide(a):
            continue
        if pmin is not None and a.precio < pmin:
            continue
        res.append(a)
    return res


def _linea(fuente: str, prod: Producto, recibidos: list[Anuncio]) -> str:
    validos = _validos(recibidos, prod)
    txt = f"✅ {fuente} · {prod.nombre}: {len(recibidos)} anuncios recibidos, {len(validos)} válidos"
    if validos:
        barato = min(validos, key=lambda a: a.precio)
        _, pmax = prod.limites(barato.nuevo)
        txt += f", el más barato {euros(barato.precio)}"
        if pmax is not None:
            txt += f" (tu máximo: {euros(pmax)})"
    return txt


def _detalle(cfg: Config, prod: Producto, anuncios: list[Anuncio]) -> None:
    """Escribe en el log los anuncios por debajo del máximo y por qué se avisarían o no."""
    _, pmax = prod.limites(False)
    items = wallapop.extraer_items(wallapop.ultima_respuesta or {})
    if items:
        muestra = items[0]
        log.info("Muestra cruda Wallapop: claves=%s", sorted(muestra.keys()))
        for k in ("shipping", "location", "reserved", "flags", "price"):
            if k in muestra:
                log.info("   %s = %s", k, str(muestra[k])[:300])
    for a in sorted(_validos(anuncios, prod), key=lambda x: x.precio):
        if pmax is not None and a.precio > pmax:
            break
        dist = (distancia_km(cfg.lat, cfg.lon, a.lat, a.lon)
                if a.lat is not None and a.lon is not None else None)
        lejos = bool(cfg.radio_km and dist is not None and dist > cfg.radio_km)
        avisaria = not lejos or (cfg.aceptar_envio and a.envio)
        log.info("   %s %s | %s | %s | %s km | envío=%s | %s",
                 "AVISARÍA" if avisaria else "descartado", euros(a.precio), a.titulo[:60],
                 a.ciudad, f"{dist:.0f}" if dist is not None else "?", a.envio, a.url)


def _error(fuente: str, e: Exception) -> str:
    if isinstance(e, Bloqueado):
        return f"❌ {fuente}: me bloquea ({e})"
    if isinstance(e, ERRORES_RED):
        return f"❌ {fuente}: error de red ({str(e)[:120]})"
    return f"❌ {fuente}: error inesperado ({type(e).__name__}: {str(e)[:120]})"


def ejecutar(cfg: Config, avisador: avisos.Avisador) -> list[str]:
    lineas = [f"🩺 Diagnóstico del bot (HTTP: {MOTOR})"]
    sesion = sesion_navegador()

    if cfg.activa("wallapop"):
        for prod in cfg.productos:
            try:
                res = wallapop.buscar(sesion, prod.busquedas[0], cfg.lat, cfg.lon, prod.usado_min)
                lineas.append(_linea("Wallapop", prod, res))
                _detalle(cfg, prod, res)
            except Exception as e:
                lineas.append(_error("Wallapop", e))
                break

    if cfg.activa("vinted"):
        vinted = Vinted(sesion_navegador(), cfg.dominio_vinted)
        for prod in cfg.productos:
            try:
                res = vinted.buscar(prod.busquedas[0], prod.usado_min)
                lineas.append(_linea("Vinted", prod, res))
            except Exception as e:
                lineas.append(_error("Vinted", e))
                break

    if cfg.activa("chollometro"):
        try:
            chollos: list[Anuncio] = []
            for url in cfg.feeds_chollometro:
                chollos += chollometro.leer(sesion, url)
            partes = [f"{p.nombre}: {len(_validos(chollos, p))}" for p in cfg.productos]
            lineas.append(f"✅ Chollometro: {len(chollos)} chollos nuevos en el feed; de consolas → "
                          + ", ".join(partes))
        except Exception as e:
            lineas.append(_error("Chollometro", e))

    if cfg.activa("tiendas"):
        for t in cfg.tiendas:
            try:
                info = tiendas.consultar(sesion, t.url)
                stock = {True: "con stock", False: "sin stock", None: "stock desconocido"}[info.get("en_stock")]
                lineas.append(f"✅ {t.nombre} · {t.producto}: {euros(info.get('precio'))}, {stock}")
            except Exception as e:
                lineas.append(_error(t.nombre, e))

    if cfg.telegram_token:
        try:
            grupos = [c for c in avisos.Telegram(cfg.telegram_token, None).chats()
                      if c["tipo"] in ("group", "supergroup")]
            for g in grupos:
                temas = "con temas ✅" if g["foro"] else "SIN temas (actívalos en el grupo)"
                lineas.append(f"👥 Grupo «{g['nombre']}»: id {g['id']} · {temas}")
            if cfg.telegram_grupo_id:
                lineas.append(f"📨 Las ofertas van al grupo {cfg.telegram_grupo_id}")
        except Exception as e:
            lineas.append(f"❌ Telegram (lista de grupos): {str(e)[:100]}")

    lineas.append("Si todo sale ✅ y no te llegan avisos, es que no hay ofertas por debajo de tus máximos.")
    for linea in lineas:
        log.info(linea)
    avisador.enviar(avisos.Aviso(html=html.escape("\n".join(lineas)), texto="\n".join(lineas)))
    return lineas



SONDAS = {
    "milanuncios": "https://www.milanuncios.com/anuncios/?s=ps5",
    "cex_api": "https://wss2.cex.es.webuy.io/v3/boxes?q=ps5&firstRecord=1&count=20&sortBy=relevance&sortOrder=desc",
    "cex_web": "https://es.webuy.com/search?stext=ps5",
    "ebay_web": "https://www.ebay.es/sch/i.html?_nkw=ps5&_sop=10&LH_PrefLoc=1",
    "todocoleccion": "https://www.todocoleccion.net/buscador?bu=ps5",
    "cashconverters": "https://www.cashconverters.es/es/es/search/?q=ps5",
    "backmarket": "https://www.backmarket.es/es-es/search?q=ps5",
    "rebuy": "https://www.rebuy.es/comprar/search?q=ps5",
    "vinted_portada": "https://www.vinted.es/",
    "vinted_api": "https://www.vinted.es/api/v2/catalog/items?search_text=ps5&per_page=5",
}
MARCAS = ("__NEXT_DATA__", "__INITIAL_PROPS__", "application/ld+json", "window.__", "adId",
          "boxId", "s-item", "captcha", "Just a moment", "datadome", "cf-chl", "\"items\"")


def sonda_plataformas() -> None:
    """Solo log: qué plataformas responden desde aquí y en qué formato."""
    s = sesion_navegador()
    for nombre, url in SONDAS.items():
        try:
            r = s.get(url, timeout=25, headers={"Accept": "text/html,application/json;q=0.9,*/*;q=0.8"})
            texto = r.text or ""
            marcas = [m for m in MARCAS if m.lower() in texto.lower()]
            log.info("Sonda %-15s %s · %s · %d bytes · %s", nombre, r.status_code,
                     (r.headers.get("content-type") or "")[:30], len(texto), marcas)
            log.info("Sonda %-15s  inicio: %s", nombre, " ".join(texto[:220].split()))
        except Exception as e:
            log.info("Sonda %-15s error: %s", nombre, str(e)[:150])


def sonda_formatos() -> None:
    """Solo log: dónde vienen los datos en Cash Converters, rebuy, CeX y Vinted."""
    import json as _json
    import re as _re
    s = sesion_navegador()
    h = {"Accept": "text/html,application/json;q=0.9,*/*;q=0.8"}

    def trozos(nombre, texto, patron, n=3, ancho=260):
        for m in list(_re.finditer(patron, texto))[:n]:
            ini = max(0, m.start() - 40)
            log.info("Formato %-8s …%s…", nombre, " ".join(texto[ini:ini + ancho].split()))

    try:
        t = s.get(SONDAS["cashconverters"], timeout=25, headers=h).text
        for b in _re.findall(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', t, _re.S)[:4]:
            try:
                j = _json.loads(b)
                log.info("Formato cashconv JSON-LD @type=%s claves=%s · %s", j.get("@type") if isinstance(j, dict) else "lista",
                         list(j.keys())[:8] if isinstance(j, dict) else len(j), " ".join(b[:300].split()))
            except ValueError:
                pass
        trozos("cashconv", t, r'data-product|product-tile|product-card|"price"', 3)
    except Exception as e:
        log.info("Formato cashconv error %s", e)
    try:
        t = s.get(SONDAS["rebuy"], timeout=25, headers=h).text
        trozos("rebuy", t, r'"items"\s*:', 2, 400)
        trozos("rebuy", t, r'window\.__[A-Za-z_]+', 3, 120)
    except Exception as e:
        log.info("Formato rebuy error %s", e)
    try:
        t = s.get(SONDAS["cex_web"], timeout=25, headers=h).text
        trozos("cex", t, r'(?i)algolia', 4, 220)
        trozos("cex", t, r'boxName|sellPrice|"boxId"', 3, 220)
        for js in sorted(set(_re.findall(r'src="([^"]+\.js)"', t)))[:12]:
            log.info("Formato cex script %s", js)
    except Exception as e:
        log.info("Formato cex error %s", e)
    try:
        t = s.get(SONDAS["vinted_portada"], timeout=25, headers=h).text
        rutas = sorted(set(_re.findall(r'/api/v\d/[a-z_/]+', t)))
        log.info("Formato vinted rutas api en portada: %s", rutas[:40])
        trozos("vinted", t, r'catalog', 3, 200)
    except Exception as e:
        log.info("Formato vinted error %s", e)
