from __future__ import annotations

import math
import re
import unicodedata

_NUM = re.compile(r"\d[\d.,]*")
_PRECIO_EN_TEXTO = re.compile(r"(\d[\d.,]*)\s*(?:€|eur\b|euros?\b)", re.I)


def quitar_tildes(texto: str | None) -> str:
    return unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()


def normalizar(texto: str | None) -> str:
    """Minúsculas, sin tildes y con espacios simples (para comparar títulos)."""
    return re.sub(r"\s+", " ", quitar_tildes(texto).lower()).strip()


def parsear_precio(valor) -> float | None:
    """Convierte '1.299,99€', '549€', '400.0', 549, 'GRATIS'... en float."""
    if valor is None or isinstance(valor, bool):
        return None
    if isinstance(valor, (int, float)):
        return float(valor)
    t = str(valor).strip().lower()
    if not t:
        return None
    if "grat" in t or "free" in t:
        return 0.0
    m = _NUM.search(t)
    if not m:
        return None
    n = m.group(0).rstrip(".,")
    if "," in n and "." in n:
        if n.rfind(",") > n.rfind("."):      # 1.299,99
            n = n.replace(".", "").replace(",", ".")
        else:                                 # 1,299.99
            n = n.replace(",", "")
    elif "," in n:
        entero, dec = n.rsplit(",", 1)
        n = f"{entero.replace(',', '')}.{dec}" if len(dec) in (1, 2) else n.replace(",", "")
    elif "." in n:
        entero, dec = n.rsplit(".", 1)
        if len(dec) == 3:                     # 1.299 -> miles
            n = n.replace(".", "")
        else:
            n = f"{entero.replace('.', '')}.{dec}"
    try:
        return float(n)
    except ValueError:
        return None


def precio_en_texto(texto: str | None) -> float | None:
    """Busca un precio tipo '549€' o '549,90 euros' dentro de un texto."""
    m = _PRECIO_EN_TEXTO.search(texto or "")
    return parsear_precio(m.group(1)) if m else None


def numero(valor) -> float | None:
    try:
        return float(valor)
    except (TypeError, ValueError):
        return None


def distancia_km(lat1, lon1, lat2, lon2) -> float:
    """Distancia en línea recta (haversine)."""
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def hora_local(ts: float | None, ahora: float | None = None) -> str:
    """'hoy 08:23', 'ayer 21:10' o '18/11 10:00' en hora de Madrid."""
    if not ts:
        return "¿?"
    import time as _time
    from datetime import datetime, timedelta, timezone
    try:
        from zoneinfo import ZoneInfo
        zona = ZoneInfo("Europe/Madrid")
    except Exception:  # pragma: no cover
        zona = timezone.utc
    t = datetime.fromtimestamp(ts, zona)
    hoy = datetime.fromtimestamp(ahora or _time.time(), zona).date()
    if t.date() == hoy:
        return f"hoy {t:%H:%M}"
    if t.date() == hoy - timedelta(days=1):
        return f"ayer {t:%H:%M}"
    return f"{t:%d/%m %H:%M}"


def euros(valor: float | None) -> str:
    """549.0 -> '549 €'; 1299.9 -> '1.299,90 €'."""
    if valor is None:
        return "¿? €"
    if abs(valor - round(valor)) < 0.005:
        txt = f"{round(valor):,}".replace(",", ".")
    else:
        txt = f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{txt} €"
