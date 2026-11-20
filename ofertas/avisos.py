"""Envío de avisos: Telegram (recomendado) y/o WhatsApp vía CallMeBot.

Con un grupo de Telegram con temas, cada oferta va al tema de su categoría
(🔥 Ofertones, 💰 Buen precio, 🏷️ Resto), los mensajes se actualizan cuando el anuncio
se vende o cambia de precio, y cada tema tiene un índice fijado con lo más nuevo arriba.
"""
from __future__ import annotations

import hashlib
import html
import logging
import time
from dataclasses import dataclass

from .red import sesion_simple
from .utiles import euros, hora_local

log = logging.getLogger(__name__)

ETIQUETA_FUENTE = {
    "wallapop": "Wallapop",
    "vinted": "Vinted",
    "chollometro": "Chollometro",
    "cex": "CeX",
    "cashconverters": "Cash Converters",
    "carrefour": "Carrefour",
    "game": "GAME",
    "elcorteingles": "El Corte Inglés",
    "tienda": "Tienda",
}

# sección del grupo -> (nombre del tema, color del icono permitido por Telegram)
# Primero el tipo de consola (nueva / segunda mano) y luego la categoría de precio.
CATEGORIAS = {
    "nueva_oferton": ("🆕 Nuevas · 🔥 Ofertones", 13338331),
    "nueva_buen_precio": ("🆕 Nuevas · 💰 Buen precio", 9367192),
    "usada_oferton": ("♻️ Segunda mano · 🔥 Ofertones", 16478047),
    "usada_buen_precio": ("♻️ Segunda mano · 💰 Buen precio", 16766590),
    "usada_resto": ("♻️ Segunda mano · 🏷️ Resto", 7322096),
}


def seccion(nuevo: bool, categoria: str) -> str:
    """'oferton' + nueva -> 'nueva_oferton'. Las nuevas no tienen 'resto' (pasan del tope)."""
    clave = f"{'nueva' if nuevo else 'usada'}_{categoria}"
    if clave in CATEGORIAS:
        return clave
    return "nueva_buen_precio" if nuevo else "usada_resto"


@dataclass
class Aviso:
    html: str            # para Telegram
    texto: str           # para WhatsApp / consola
    imagen: str | None = None


class Telegram:
    INTERVALO_GRUPO = 3.2      # Telegram admite unos 20 mensajes por minuto en un grupo
    INTERVALO_PRIVADO = 0.4

    def __init__(self, token: str, chat_id: str | None):
        self.url = f"https://api.telegram.org/bot{token}/"
        self.chat_id = str(chat_id) if chat_id else None
        self.s = sesion_simple()
        self._ultimo: dict[str, float] = {}

    def _llamar(self, metodo: str, datos: dict, chat_id: str | None = None) -> dict:
        cid = str(chat_id) if chat_id else ""
        if cid:
            intervalo = self.INTERVALO_GRUPO if cid.startswith("-") else self.INTERVALO_PRIVADO
            espera = intervalo - (time.time() - self._ultimo.get(cid, 0))
            if espera > 0:
                time.sleep(espera)
        j: dict = {}
        for intento in range(3):
            r = self.s.post(self.url + metodo, json=datos, timeout=25)
            if cid:
                self._ultimo[cid] = time.time()
            try:
                j = r.json()
            except ValueError:
                j = {"ok": False, "error_code": r.status_code, "description": r.text[:200]}
            if j.get("error_code") == 429 and intento < 2:
                time.sleep(min(int((j.get("parameters") or {}).get("retry_after", 5)) + 1, 60))
                continue
            break
        return j

    def enviar(self, aviso: Aviso, chat_id: str | None = None, thread_id: int | None = None,
               silencioso: bool = False, sin_vista_previa: bool = False) -> dict | None:
        """Envía y devuelve {'chat_id', 'message_id', 'con_foto'} (o None si falla)."""
        cid = str(chat_id or self.chat_id)
        base: dict = {"chat_id": cid, "parse_mode": "HTML"}
        if thread_id:
            base["message_thread_id"] = int(thread_id)
        if silencioso:
            base["disable_notification"] = True
        if aviso.imagen and len(aviso.html) <= 1024:
            j = self._llamar("sendPhoto", {**base, "photo": aviso.imagen, "caption": aviso.html}, cid)
            if j.get("ok"):
                return {"chat_id": cid, "message_id": j["result"]["message_id"], "con_foto": True}
            log.debug("sendPhoto falló (%s), mando solo texto", j.get("description"))
        j = self._llamar("sendMessage", {**base, "text": aviso.html,
                                         "link_preview_options": {"is_disabled": sin_vista_previa}}, cid)
        if j.get("ok"):
            return {"chat_id": cid, "message_id": j["result"]["message_id"], "con_foto": False}
        log.error("Telegram no ha enviado el mensaje: %s", j.get("description"))
        return None

    def editar(self, chat_id: str, message_id: int, html_nuevo: str, con_foto: bool,
               sin_vista_previa: bool = False) -> bool | None:
        """True = editado (o sin cambios); False = el mensaje ya no existe; None = otro error."""
        datos = {"chat_id": chat_id, "message_id": int(message_id), "parse_mode": "HTML"}
        if con_foto:
            j = self._llamar("editMessageCaption", {**datos, "caption": html_nuevo}, chat_id)
        else:
            j = self._llamar("editMessageText", {**datos, "text": html_nuevo,
                                                 "link_preview_options": {"is_disabled": sin_vista_previa}},
                             chat_id)
        if j.get("ok"):
            return True
        desc = (j.get("description") or "").lower()
        if "not modified" in desc:
            return True
        if "not found" in desc or "can't be edited" in desc:
            return False
        log.warning("Telegram no ha editado el mensaje: %s", j.get("description"))
        return None

    def renombrar_tema(self, chat_id: str, thread_id: int, nombre: str) -> bool:
        j = self._llamar("editForumTopic", {"chat_id": chat_id, "message_thread_id": int(thread_id),
                                            "name": nombre}, chat_id)
        desc = (j.get("description") or "").lower()
        if j.get("ok") or "not modified" in desc:
            return True
        log.warning("No he podido renombrar el tema %s: %s", thread_id, j.get("description"))
        return False

    def crear_tema(self, chat_id: str, nombre: str, color: int) -> int | None:
        j = self._llamar("createForumTopic", {"chat_id": chat_id, "name": nombre, "icon_color": color}, chat_id)
        if j.get("ok"):
            return int(j["result"]["message_thread_id"])
        log.error("No he podido crear el tema %s: %s", nombre, j.get("description"))
        return None

    def fijar(self, chat_id: str, message_id: int) -> bool:
        j = self._llamar("pinChatMessage", {"chat_id": chat_id, "message_id": int(message_id),
                                            "disable_notification": True}, chat_id)
        if not j.get("ok"):
            log.warning("No he podido fijar el índice: %s", j.get("description"))
        return bool(j.get("ok"))

    def chats(self) -> list[dict]:
        """Chats y grupos en los que ha estado el bot (para sacar los ids)."""
        r = self.s.get(self.url + "getUpdates", timeout=20)
        r.raise_for_status()
        vistos: dict[str, dict] = {}
        for u in r.json().get("result", []):
            for clave in ("message", "channel_post", "my_chat_member", "chat_member", "edited_message"):
                chat = (u.get(clave) or {}).get("chat") or {}
                if "id" in chat:
                    nombre = chat.get("title") or " ".join(
                        x for x in (chat.get("first_name"), chat.get("last_name")) if x) or chat.get("username", "")
                    vistos[str(chat["id"])] = {"id": str(chat["id"]), "nombre": nombre,
                                               "tipo": chat.get("type"), "foro": bool(chat.get("is_forum"))}
        return list(vistos.values())


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
        foto = f"\n🖼️ {aviso.imagen}" if aviso.imagen else "\n🖼️ (sin foto)"
        print("\n" + "─" * 60 + "\n" + aviso.texto + foto + "\n" + "─" * 60, flush=True)
        return True


class Avisador:
    """Mensajes del sistema por todos los canales; ofertas al grupo (por temas) o al chat."""

    def __init__(self, canales: list, telegram: Telegram | None = None, grupo_id: str | None = None,
                 estado=None, temas: dict | None = None):
        self.canales = canales                    # para mensajes del sistema
        self.telegram = telegram
        self.grupo_id = str(grupo_id) if grupo_id else None
        self.estado = estado
        self.temas_cfg = {k: int(v) for k, v in (temas or {}).items() if v}
        self.otros = [c for c in canales if not isinstance(c, _CanalTelegram)]

    @property
    def con_grupo(self) -> bool:
        return bool(self.telegram and self.grupo_id)

    def enviar(self, aviso: Aviso) -> bool:
        ok = False
        for c in self.canales:
            try:
                ok = c.enviar(aviso) or ok
            except Exception as e:  # un canal caído no debe tumbar el bot
                log.error("Error enviando por %s: %s", type(c).__name__, e)
        return ok

    def enviar_oferta(self, aviso: Aviso, categoria: str) -> dict | None:
        """Devuelve la referencia del mensaje de Telegram ({} si solo salió por otro canal)
        o None si no se pudo enviar por ningún sitio."""
        ref, ok = None, False
        if self.telegram and (self.con_grupo or self.telegram.chat_id):
            try:
                if self.con_grupo:
                    ref = self.telegram.enviar(aviso, chat_id=self.grupo_id, thread_id=self.tema(categoria))
                else:
                    ref = self.telegram.enviar(aviso)
                ok = ref is not None
            except Exception as e:
                log.error("Error enviando a Telegram: %s", e)
        for c in self.otros:
            try:
                ok = c.enviar(aviso) or ok
            except Exception as e:
                log.error("Error enviando por %s: %s", type(c).__name__, e)
        if not ok:
            return None
        return ref or {}

    def editar(self, ref: dict | None, html_nuevo: str) -> bool | None:
        if not (self.telegram and ref and ref.get("message_id") and ref.get("chat_id")):
            return None
        try:
            return self.telegram.editar(ref["chat_id"], ref["message_id"], html_nuevo, bool(ref.get("con_foto")))
        except Exception as e:
            log.error("Error editando en Telegram: %s", e)
            return None

    def tema(self, categoria: str) -> int | None:
        if not self.con_grupo:
            return None
        if categoria in self.temas_cfg:
            return self.temas_cfg[categoria]
        clave = f"tema:{self.grupo_id}:{categoria}"
        guardado = self.estado.leer(clave) if self.estado else None
        if guardado:
            return int(guardado)
        nombre, color = CATEGORIAS.get(categoria, CATEGORIAS["usada_resto"])
        tid = self.telegram.crear_tema(self.grupo_id, nombre, color)
        if tid and self.estado:
            self.estado.guardar(clave, tid)
            self.estado.guardar(f"tema_nombre:{self.grupo_id}:{categoria}", nombre)
            log.info("Tema creado en el grupo: %s (id %s)", nombre, tid)
        return tid

    def preparar_temas(self) -> None:
        """Crea los temas que falten y pone a cada uno su nombre actual (una vez)."""
        if not (self.con_grupo and self.estado):
            return
        for sec, (nombre, _) in CATEGORIAS.items():
            tid = self.tema(sec)
            clave = f"tema_nombre:{self.grupo_id}:{sec}"
            if tid and self.estado.leer(clave) != nombre:
                if self.telegram.renombrar_tema(self.grupo_id, tid, nombre):
                    self.estado.guardar(clave, nombre)

    def indice(self, categoria: str, html_indice: str) -> None:
        """Mensaje fijado en cada tema con las ofertas de los últimos días (lo más nuevo arriba)."""
        if not (self.con_grupo and self.estado):
            return
        clave = f"indice:{self.grupo_id}:{categoria}"
        clave_hash = f"indice_hash:{self.grupo_id}:{categoria}"
        huella = hashlib.sha1(html_indice.encode()).hexdigest()
        if self.estado.leer(clave_hash) == huella:
            return
        mid = self.estado.leer(clave)
        if mid:
            r = self.telegram.editar(self.grupo_id, int(mid), html_indice, False, sin_vista_previa=True)
            if r is None:
                return                         # error pasajero: se reintenta en la próxima pasada
            if r:
                self.estado.guardar(clave_hash, huella)
                return
        ref = self.telegram.enviar(Aviso(html_indice, ""), chat_id=self.grupo_id,
                                   thread_id=self.tema(categoria), silencioso=True, sin_vista_previa=True)
        if ref:
            self.estado.guardar(clave, ref["message_id"])
            self.estado.guardar(clave_hash, huella)
            self.telegram.fijar(self.grupo_id, ref["message_id"])


class _CanalTelegram:
    """Adapta el cliente de Telegram a la interfaz de canal simple (mensajes del sistema)."""

    def __init__(self, telegram: Telegram):
        self.telegram = telegram

    def enviar(self, aviso: Aviso) -> bool:
        return self.telegram.enviar(aviso) is not None


def crear_avisador(cfg, solo_consola: bool = False, estado=None) -> Avisador:
    canales: list = []
    telegram = None
    if not solo_consola:
        if cfg.telegram_token and (cfg.telegram_chat_id or cfg.telegram_grupo_id):
            telegram = Telegram(cfg.telegram_token, cfg.telegram_chat_id)
            if cfg.telegram_chat_id:
                canales.append(_CanalTelegram(telegram))
        if cfg.callmebot_telefono and cfg.callmebot_apikey:
            canales.append(WhatsApp(cfg.callmebot_telefono, cfg.callmebot_apikey))
        if not canales and not telegram:
            log.warning("No hay Telegram ni WhatsApp configurados: los avisos salen solo por consola")
    if solo_consola or (not canales and not telegram):
        canales.append(Consola())
    return Avisador(canales, telegram=telegram, grupo_id=None if solo_consola else cfg.telegram_grupo_id,
                    estado=estado, temas=cfg.telegram_temas)


# --- formato de los mensajes -------------------------------------------------

CABECERAS = {
    "oferton": ("🔥🔥 <b>OFERTÓN</b> 🔥🔥", "🔥🔥 OFERTÓN 🔥🔥"),
    "buen_precio": ("💰 <b>BUEN PRECIO</b>", "💰 BUEN PRECIO"),
}


def formatear(a, producto: str, motivo: str, mediana: float | None = None, muestras: int = 0,
              distancia: float | None = None, sospechoso: bool = False,
              categoria: str = "resto") -> Aviso:
    e = html.escape
    fuente = ETIQUETA_FUENTE.get(a.fuente, a.fuente)
    tipo = "nueva" if a.nuevo else "segunda mano"
    h, t = [], []
    if categoria in CABECERAS:
        h.append(CABECERAS[categoria][0])
        t.append(CABECERAS[categoria][1])
    icono = "🎮" if categoria in CABECERAS else "🏷️"
    h.append(f"{icono} <b>{e(producto)}</b> · {e(fuente)} · {tipo}")
    t.append(f"{icono} {producto} · {fuente} · {tipo}")
    h.append(f"💶 <b>{euros(a.precio)}</b> — {e(a.titulo[:150])}")
    t.append(f"💶 {euros(a.precio)} — {a.titulo[:150]}")

    if a.tienda and a.fuente in ("chollometro", "tienda"):
        h.append(f"🏬 {e(a.tienda)}")
        t.append(f"🏬 {a.tienda}")
    lugar = []
    if a.ciudad:
        lugar.append(f"📍 {a.ciudad}" + (f" ({distancia:.0f} km)" if distancia is not None else ""))
    if a.envio and a.fuente == "wallapop":
        lugar.append("📦 con envío")
    if lugar:
        h.append(e(" · ".join(lugar)))
        t.append(" · ".join(lugar))
    if a.publicado:
        h.append(f"🕐 Publicado {hora_local(a.publicado)}")
        t.append(f"🕐 Publicado {hora_local(a.publicado)}")
    if a.estado:
        h.append(f"✨ Estado: {e(a.estado)}")
        t.append(f"✨ Estado: {a.estado}")
    if a.precio_total and a.precio and a.precio_total > a.precio + 0.01:
        h.append(f"💳 Total con protección al comprador: {euros(a.precio_total)}")
        t.append(f"💳 Total con protección: {euros(a.precio_total)}")
    if mediana and a.precio is not None:
        dif = (a.precio / mediana - 1) * 100
        linea = f"📊 Mediana de segunda mano: {euros(mediana)} ({dif:+.0f}%, {muestras} anuncios)"
        h.append(e(linea))
        t.append(linea)
    if motivo:
        icono_motivo = "✅" if categoria == "oferton" else "ℹ️"
        h.append(f"{icono_motivo} {e(motivo)}")
        t.append(f"{icono_motivo} {motivo}")
    if sospechoso:
        aviso = "⚠️ Muy por debajo del mercado: puede ser estafa. Paga solo dentro de la plataforma."
        h.append(e(aviso))
        t.append(aviso)
    destino = a.tienda if a.fuente == "tienda" and a.tienda else fuente
    h.append(f'👉 <a href="{e(a.url, quote=True)}"><b>Ver en {e(destino)}</b></a>')
    t.append(f"👉 {a.url}")
    return Aviso(html="\n".join(h), texto="\n".join(t), imagen=a.imagen)


def con_estado(original: str, prefijo: str, con_foto: bool) -> str:
    """Añade una línea de estado arriba del mensaje original sin pasarse del límite."""
    nuevo = f"{prefijo}\n{original}" if prefijo else original
    limite = 1024 if con_foto else 4096
    if len(nuevo) <= limite:
        return nuevo
    lineas = original.split("\n")
    return f"{prefijo}\n{lineas[0]}\n{lineas[-1]}"[:limite]


def prefijo_estado(estado: str, precio_nuevo: float | None = None,
                   precio_antes: float | None = None) -> str:
    partes = []
    if estado == "vendida":
        partes.append("❌ <b>YA NO ESTÁ DISPONIBLE</b> (vendida o retirada)")
    elif estado == "reservada":
        partes.append("🟡 <b>RESERVADA</b>")
    elif estado == "rebajada":
        partes.append(f"⬇️ <b>Ha bajado a {euros(precio_nuevo)}</b>: te la he vuelto a mandar")
    if estado in ("disponible", "reservada") and precio_nuevo is not None and precio_antes is not None \
            and abs(precio_nuevo - precio_antes) >= 1:
        partes.append(f"💶 <b>Precio actualizado: {euros(precio_nuevo)}</b> (antes {euros(precio_antes)})")
    return "\n".join(partes)


def construir_indice(categoria: str, filas: list[dict], dias: float, max_disponibles: int = 20,
                     max_vendidas: int = 8) -> str:
    """Índice del tema: disponibles (lo más nuevo arriba) y las que ya no están."""
    e = html.escape
    nombre = CATEGORIAS.get(categoria, CATEGORIAS["usada_resto"])[0]
    cab = [f"📌 <b>{nombre}</b> · lo más nuevo arriba",
           f"<i>Actualizado {hora_local(time.time())} · últimos {dias:g} días</i>", ""]
    disponibles = [f for f in filas if f["estado"] != "vendida"]
    vendidas = [f for f in filas if f["estado"] == "vendida"]
    cuerpo = []
    for f in disponibles[:max_disponibles]:
        marca = "🟡" if f["estado"] == "reservada" else "✅"
        lugar = f" · {e(f['ciudad'])}" if f.get("ciudad") else ""
        cuerpo.append(f"{marca} <b>{euros(f['precio'])}</b> · {e(f['producto'])} · "
                      f'<a href="{e(f["url"], quote=True)}">{e((f["titulo"] or "")[:45])}</a>'
                      f"{lugar} · 🕐 {hora_local(f['publicado'])}")
    if not cuerpo:
        cuerpo.append("Ahora mismo no hay ninguna disponible.")
    if vendidas:
        cuerpo += ["", "❌ <b>Ya no disponibles</b>"]
        for f in vendidas[:max_vendidas]:
            cuerpo.append(f"<s>{euros(f['precio'])} · {e((f['titulo'] or '')[:45])}</s>")
    texto = "\n".join(cab + cuerpo)
    while len(texto) > 4000 and cuerpo:
        cuerpo.pop()
        texto = "\n".join(cab + cuerpo)
    return texto
