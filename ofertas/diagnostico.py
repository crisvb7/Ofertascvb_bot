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

    from .motor import SIMPLES
    for clave, (modulo, de_tienda) in SIMPLES.items():
        if not cfg.activa(clave):
            continue
        nombre = avisos.ETIQUETA_FUENTE.get(clave, clave)
        for prod in cfg.productos:
            try:
                res = modulo.buscar(sesion, f"consola {prod.busquedas[0]}" if de_tienda else prod.busquedas[0])
                lineas.append(_linea(nombre, prod, res))
            except Exception as e:
                lineas.append(_error(nombre, e))
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


