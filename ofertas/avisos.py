"""Envío de avisos: Telegram (recomendado) y/o WhatsApp vía CallMeBot."""
from __future__ import annotations

import html
import logging
import time
from dataclasses import dataclass

from .red import sesion_simple
from .utiles import euros

log = logging.getLogger(__name__)

ETIQUETA_FUENTE = {
    "wallapop": "Wallapop",
    "vinted": "Vinted",
    "chollometro": "Chollometro",
    "tienda": "Tienda",
}


@dataclass
class Aviso:
    html: str            # para Telegram
    texto: str           # para WhatsApp / consola
    imagen: str | None = None


class Telegram:
    def __init__(self, token: str, chat_id: str):
        self.url = f"https://api.telegram.org/bot{token}/"
        self.chat_id = chat_id
        self.s = sesion_simple()

    def enviar(self, aviso: Aviso) -> bool:
        if aviso.imagen and len(aviso.html) <= 1024:
            r = self.s.post(self.url + "sendPhoto", timeout=20, data={
                "chat_id": self.chat_id, "photo": aviso.imagen,
                "caption": aviso.html, "parse_mode": "HTML"})
            if r.ok:
                return True
            log.debug("sendPhoto falló (%s), mando solo texto", r.status_code)
        r = self.s.post(self.url + "sendMessage", timeout=20, json={
            "chat_id": self.chat_id, "text": aviso.html, "parse_mode": "HTML",
            "disable_web_page_preview": False})
        if not r.ok:
            log.error("Telegram respondió %s: %s", r.status_code, r.text[:300])
        return r.ok

    def chats(self) -> list[tuple[str, str]]:
        """Chats que han escrito al bot (para averiguar tu TELEGRAM_CHAT_ID)."""
        r = self.s.get(self.url + "getUpdates", timeout=20)
        r.raise_for_status()
        vistos = {}
        for u in r.json().get("result", []):
            msg = u.get("message") or u.get("channel_post") or {}
            chat = msg.get("chat") or {}
            if "id" in chat:
                nombre = chat.get("title") or " ".join(
                    x for x in (chat.get("first_name"), chat.get("last_name")) if x) or chat.get("username", "")
                vistos[str(chat["id"])] = nombre
        return list(vistos.items())


class WhatsApp:
    """CallMeBot: API gratuita para mandarte WhatsApps a ti mismo (solo uso personal)."""

    URL = "https://api.callmebot.com/whatsapp.php"

    def __init__(self, telefono: str, apikey: str):
        self.telefono = telefono
        self.apikey = apikey
        self.s = sesion_simple()
        self._ultimo = 0.0

    def enviar(self, aviso: Aviso) -> bool:
        espera = 4 - (time.time() - self._ultimo)   # CallMeBot no quiere ráfagas
        if espera > 0:
            time.sleep(espera)
        r = self.s.get(self.URL, timeout=30, params={
            "phone": self.telefono, "text": aviso.texto, "apikey": self.apikey})
        self._ultimo = time.time()
        if not r.ok:
            log.error("CallMeBot respondió %s: %s", r.status_code, r.text[:300])
        return r.ok


class Consola:
    def enviar(self, aviso: Aviso) -> bool:
        print("\n" + "─" * 60 + "\n" + aviso.texto + "\n" + "─" * 60)
        return True


class Avisador:
    """Reparte cada aviso por todos los canales configurados."""

    def __init__(self, canales: list):
        self.canales = canales

    def enviar(self, aviso: Aviso) -> bool:
        ok = False
        for c in self.canales:
            try:
                ok = c.enviar(aviso) or ok
            except Exception as e:  # un canal caído no debe tumbar el bot
                log.error("Error enviando por %s: %s", type(c).__name__, e)
        return ok


def crear_avisador(cfg, solo_consola: bool = False) -> Avisador:
    canales = []
    if not solo_consola:
        if cfg.telegram_token and cfg.telegram_chat_id:
            canales.append(Telegram(cfg.telegram_token, cfg.telegram_chat_id))
        if cfg.callmebot_telefono and cfg.callmebot_apikey:
            canales.append(WhatsApp(cfg.callmebot_telefono, cfg.callmebot_apikey))
        if not canales:
            log.warning("No hay Telegram ni WhatsApp configurados en .env: los avisos salen solo por consola")
    if solo_consola or not canales:
        canales.append(Consola())
    return Avisador(canales)


# --- formato de los mensajes -------------------------------------------------

def formatear(a, producto: str, motivo: str, mediana: float | None = None, muestras: int = 0,
              distancia: float | None = None, sospechoso: bool = False) -> Aviso:
    e = html.escape
    fuente = ETIQUETA_FUENTE.get(a.fuente, a.fuente)
    cabecera = "🆕" if a.nuevo else "♻️"
    h = [f"{cabecera} <b>{e(producto)}</b> · {e(fuente)}",
         f"<b>{euros(a.precio)}</b> — {e(a.titulo[:180])}"]
    t = [f"{cabecera} {producto} · {fuente}", f"{euros(a.precio)} — {a.titulo[:180]}"]

    if a.tienda and a.fuente != "wallapop":
        h.append(f"🏬 {e(a.tienda)}")
        t.append(f"Tienda: {a.tienda}")
    lugar = []
    if a.ciudad:
        lugar.append(f"📍 {a.ciudad}" + (f" ({distancia:.0f} km)" if distancia is not None else ""))
    if a.envio and a.fuente == "wallapop":
        lugar.append("📦 con envío")
    if lugar:
        h.append(e(" · ".join(lugar)))
        t.append(" · ".join(lugar))
    if a.estado:
        h.append(f"✨ Estado: {e(a.estado)}")
        t.append(f"Estado: {a.estado}")
    if a.precio_total and a.precio and a.precio_total > a.precio + 0.01:
        h.append(f"💳 Total con protección al comprador: {euros(a.precio_total)}")
        t.append(f"Total con protección: {euros(a.precio_total)}")
    if mediana and a.precio is not None:
        dif = (a.precio / mediana - 1) * 100
        linea = f"📊 Mediana de segunda mano: {euros(mediana)} ({dif:+.0f}%, {muestras} anuncios)"
        h.append(e(linea))
        t.append(linea)
    h.append(f"✅ {e(motivo)}")
    t.append(f"✅ {motivo}")
    if sospechoso:
        aviso = "⚠️ Muy por debajo del mercado: puede ser estafa. Paga solo dentro de la plataforma."
        h.append(e(aviso))
        t.append(aviso)
    h.append(f'<a href="{e(a.url, quote=True)}">Abrir el anuncio</a>')
    t.append(a.url)
    return Aviso(html="\n".join(h), texto="\n".join(t), imagen=a.imagen)


def formatear_resumen(producto: str, fuente: str, candidatos: list, total: int) -> Aviso:
    """Primer arranque: en vez de 30 avisos, uno con lo mejor que ya hay publicado."""
    e = html.escape
    nombre = ETIQUETA_FUENTE.get(fuente, fuente)
    h = [f"📋 <b>{e(producto)}</b> · {e(nombre)}: {len(candidatos)} ofertas que ya cumplen tus filtros"]
    t = [f"📋 {producto} · {nombre}: {len(candidatos)} ofertas que ya cumplen tus filtros"]
    for a, _ in sorted(candidatos, key=lambda c: c[0].precio or 0)[:total]:
        h.append(f'• <b>{euros(a.precio)}</b> <a href="{e(a.url, quote=True)}">{e(a.titulo[:70])}</a>')
        t.append(f"• {euros(a.precio)} {a.titulo[:70]} {a.url}")
    h.append("A partir de ahora te aviso solo de las nuevas.")
    t.append("A partir de ahora te aviso solo de las nuevas.")
    return Aviso(html="\n".join(h), texto="\n".join(t))
