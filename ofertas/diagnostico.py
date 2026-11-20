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
from .utiles import euros

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

    lineas.append("Si todo sale ✅ y no te llegan avisos, es que no hay ofertas por debajo de tus máximos.")
    for linea in lineas:
        log.info(linea)
    avisador.enviar(avisos.Aviso(html=html.escape("\n".join(lineas)), texto="\n".join(lineas)))
    return lineas
