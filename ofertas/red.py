"""Sesiones HTTP.

Si está instalado curl_cffi, las peticiones imitan la huella TLS de un Chrome real,
que es lo que más ayuda a no ser bloqueado por los antibots (Datadome, Cloudflare).
Si no, se usa requests normal.
"""
from __future__ import annotations

import requests as _requests

try:  # opcional, pero muy recomendable
    from curl_cffi import requests as _cffi
except Exception:  # pragma: no cover - depende de la plataforma
    _cffi = None

MOTOR = "curl_cffi" if _cffi is not None else "requests"

# Errores de red "normales" (sin conexión, timeout, DNS...): se registran en una línea.
ERRORES_RED: tuple = (_requests.RequestException, OSError)
if _cffi is not None:
    ERRORES_RED += (_cffi.exceptions.RequestException,)

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
IDIOMA = "es-ES,es;q=0.9,en;q=0.8"


class Bloqueado(Exception):
    """La plataforma ha rechazado la petición (403, 429, captcha...)."""


def sesion_navegador():
    """Sesión que se hace pasar por un navegador (para Wallapop, Vinted, tiendas)."""
    if _cffi is not None:
        s = _cffi.Session(impersonate="chrome")
    else:
        s = _requests.Session()
        s.headers["User-Agent"] = UA
    s.headers["Accept-Language"] = IDIOMA
    return s


def sesion_simple():
    """Sesión normal (para Telegram y CallMeBot)."""
    s = _requests.Session()
    s.headers["User-Agent"] = "bot-ofertas-consolas"
    return s
