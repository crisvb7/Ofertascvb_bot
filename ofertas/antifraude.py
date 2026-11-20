"""Filtro de anuncios falsos de segunda mano (Wallapop y Vinted).

Descarta un anuncio si:
- el vendedor no tiene ninguna valoración (Wallapop),
- su cuenta se creó poco antes de publicar el anuncio (Wallapop),
- la foto principal ya salió en otro anuncio anterior de otro vendedor (foto robada o de internet),
- pide contacto o pago fuera de la plataforma (WhatsApp, teléfono, "solo Bizum"...).

Vinted no deja ver el perfil del vendedor al bot, así que ahí solo se miran las fotos y las frases.
"""
from __future__ import annotations

import importlib.util
import io
import logging
import random
import re
import time
from dataclasses import dataclass

from .fuentes import wallapop
from .modelos import Anuncio
from .red import ERRORES_RED, Bloqueado
from .utiles import euros

log = logging.getLogger(__name__)

SEGUNDA_MANO = ("wallapop", "vinted")
_64 = (1 << 64) - 1
PARECIDO_MAX = 4          # bits distintos (de 64) para considerar que es la misma foto
_NEGADO = re.compile(r"\b(no|ni|nada de|sin|nunca|jam[aá]s)\b[^.!?\n]*$", re.I)
MESES = ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic")


def huella(datos: bytes) -> int | None:
    """Huella de la imagen (dHash de 64 bits): cambia poco aunque la recompriman o la redimensionen."""
    try:
        from PIL import Image
    except ImportError:
        return None
    try:
        im = Image.open(io.BytesIO(datos)).convert("L").resize((9, 8), Image.LANCZOS)
    except Exception:
        return None
    px = im.tobytes()                       # un byte por píxel (escala de grises)
    h = 0
    for y in range(8):
        for x in range(8):
            h = (h << 1) | (px[y * 9 + x] > px[y * 9 + x + 1])
    return h - (1 << 64) if h >= 1 << 63 else h      # SQLite guarda enteros con signo


def distancia(a: int, b: int) -> int:
    return ((a ^ b) & _64).bit_count()


@dataclass
class Revision:
    motivo: str | None = None     # por qué parece falso (None = parece real)
    vendedor: str = ""            # línea con los datos del vendedor para el mensaje


class Antifraude:
    def __init__(self, cfg, estado, sesion, pausa: tuple[float, float] | None = (0.5, 1.2)):
        self.cfg = cfg.antifraude
        self.estado = estado
        self.sesion = sesion
        self.pausa = pausa
        self._sin_pillow = False

    @property
    def activo(self) -> bool:
        return bool(self.cfg and self.cfg.activo)

    # --- fotos ----------------------------------------------------------
    def registrar_foto(self, a: Anuncio) -> None:
        """Guarda la huella de la foto principal (una vez por anuncio)."""
        if not (self.activo and self.cfg.fotos_repetidas and a.fuente in SEGUNDA_MANO and a.imagen):
            return
        if self._sin_pillow or self.estado.foto(a.clave):
            return
        datos = self._descargar(a.imagen)
        if datos is None:
            return
        h = huella(datos)
        if h is None:
            if importlib.util.find_spec("PIL") is None:
                self._sin_pillow = True
                log.warning("Falta Pillow: no puedo comparar fotos (pip install pillow)")
            return
        self.estado.guardar_foto(a, h)

    def _descargar(self, url: str) -> bytes | None:
        if "wallapop.com" in url and "pictureSize=" in url:
            url = url.split("pictureSize=")[0] + "pictureSize=W320"
        try:
            r = self.sesion.get(url, timeout=15)
            return r.content if r.status_code == 200 and r.content else None
        except ERRORES_RED:
            return None

    def _foto_repetida(self, a: Anuncio) -> str | None:
        foto = self.estado.foto(a.clave)
        if not foto:
            return None
        for otra in self.estado.fotos_anteriores(foto):
            if distancia(foto["huella"], otra["huella"]) > PARECIDO_MAX:
                continue
            if foto["vendedor"] and otra["vendedor"]:
                if foto["vendedor"] == otra["vendedor"]:
                    continue                    # el mismo vendedor volviendo a subirlo
            elif _precio_parecido(foto["precio"], otra["precio"]):
                continue                        # sin saber el vendedor: seguramente el mismo, en otra web
            donde = {"wallapop": "Wallapop", "vinted": "Vinted"}.get(otra["fuente"], otra["fuente"])
            return f"su foto ya salió en otro anuncio de {donde} de otro vendedor (a {euros(otra['precio'])})"
        return None

    # --- vendedor --------------------------------------------------------
    def _perfil(self, a: Anuncio) -> dict | None:
        """Datos del vendedor de Wallapop (con caché). None = no se ha podido mirar."""
        guardado = self.estado.vendedor(a.vendedor)
        if guardado:
            return guardado
        try:
            datos = wallapop.vendedor(self.sesion, a.vendedor)
        except (Bloqueado, *ERRORES_RED) as e:
            log.info("No he podido mirar el vendedor de %s: %s", a.clave, str(e)[:120])
            return None
        finally:
            if self.pausa:
                time.sleep(random.uniform(*self.pausa))     # sin prisas con Wallapop
        if datos is None:
            datos = {"valoraciones": 0, "alta": None, "nombre": None, "nota": None, "ventas": 0,
                     "borrado": True}
        self.estado.guardar_vendedor(a.vendedor, a.fuente, datos)
        return datos

    def _vendedor(self, a: Anuncio) -> Revision:
        p = self._perfil(a)
        if p is None:
            return Revision(vendedor="👤 Vendedor sin comprobar (Wallapop no respondió)")
        valoraciones = int(p.get("valoraciones") or 0)
        if self.cfg.sin_valoraciones and valoraciones == 0:
            return Revision("el vendedor no tiene ninguna valoración")
        alta = p.get("alta")
        if alta and self.cfg.dias_cuenta_min:
            dias = ((a.publicado or time.time()) - alta) / 86400
            if dias < self.cfg.dias_cuenta_min:
                cuando = "el mismo día" if dias < 1 else f"{dias:.0f} días antes"
                return Revision(f"su cuenta se creó {cuando} de publicar el anuncio")
        partes = [f"{valoraciones} " + ("valoración" if valoraciones == 1 else "valoraciones")]
        if p.get("nota"):
            partes[0] += f" ({p['nota']:.1f}★)".replace(".", ",")
        if alta:
            t = time.localtime(alta)
            partes.append(f"en Wallapop desde {MESES[t.tm_mon - 1]} {t.tm_year}")
        return Revision(vendedor="👤 " + " · ".join(partes))

    # --- todo junto -----------------------------------------------------
    def frase(self, texto: str) -> str | None:
        for patron in (self.cfg.frases if self.activo else []):
            for m in patron.finditer(texto):
                if _NEGADO.search(texto[max(0, m.start() - 25):m.start()]):
                    continue                    # "no contesto por WhatsApp", "nada de Bizum"
                return f"pide tratar fuera de la plataforma («{m.group(0).strip()}»)"
        return None

    def revisar(self, a: Anuncio) -> Revision:
        if not self.activo or a.fuente not in SEGUNDA_MANO:
            return Revision()
        motivo = self.frase(f"{a.titulo}\n{a.descripcion or ''}")
        if motivo:
            return Revision(motivo)
        if self.cfg.fotos_repetidas:
            motivo = self._foto_repetida(a)
            if motivo:
                return Revision(motivo)
        if a.fuente == "wallapop" and a.vendedor:
            return self._vendedor(a)
        if a.fuente == "vinted":
            return Revision(vendedor="👤 Vendedor sin comprobar (Vinted no deja ver su perfil)")
        return Revision()


def _precio_parecido(p1: float | None, p2: float | None) -> bool:
    if not p1 or not p2:
        return False
    return abs(p1 - p2) <= 0.10 * max(p1, p2)
