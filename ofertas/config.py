"""Carga config.yaml (qué vigilar) y .env (tokens)."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .modelos import Anuncio
from .utiles import normalizar, quitar_tildes


@dataclass
class Producto:
    nombre: str
    busquedas: list[str]
    incluir: list[re.Pattern]
    excluir: list[re.Pattern]
    excluir_descripcion: list[re.Pattern]
    usado_min: float | None = None
    usado_max: float | None = None
    nuevo_min: float | None = None
    nuevo_max: float | None = None

    def coincide(self, a: Anuncio) -> bool:
        """¿El anuncio es de verdad esta consola (y no un mando, un juego, una funda...)?"""
        t = normalizar(a.titulo)
        if not any(p.search(t) for p in self.incluir):
            return False
        if any(p.search(t) for p in self.excluir):
            return False
        if self.excluir_descripcion and a.descripcion:
            d = normalizar(a.descripcion)
            if any(p.search(d) for p in self.excluir_descripcion):
                return False
        return True

    def limites(self, nuevo: bool) -> tuple[float | None, float | None]:
        return (self.nuevo_min, self.nuevo_max) if nuevo else (self.usado_min, self.usado_max)


@dataclass
class Tienda:
    producto: str
    nombre: str
    url: str
    avisar_stock: bool = True


@dataclass
class Config:
    productos: list[Producto]
    tiendas: list[Tienda] = field(default_factory=list)
    lat: float = 43.3614
    lon: float = -5.8494
    radio_km: float | None = 120
    aceptar_envio: bool = True
    dias_mercado: int = 14
    muestras_minimas: int = 12
    descuento_minimo: float = 0.20
    bajada_minima: float = 10
    intervalos: dict = field(default_factory=dict)
    fuentes: dict = field(default_factory=dict)
    feeds_chollometro: list[str] = field(default_factory=list)
    paginas_wallapop: int = 1
    dominio_vinted: str = "www.vinted.es"
    # secretos (.env)
    telegram_token: str | None = None
    telegram_chat_id: str | None = None
    callmebot_telefono: str | None = None
    callmebot_apikey: str | None = None
    ruta_bd: str = "datos/ofertas.db"

    def activa(self, fuente: str) -> bool:
        return bool(self.fuentes.get(fuente, True))

    def producto(self, nombre: str) -> Producto | None:
        return next((p for p in self.productos if p.nombre == nombre), None)


def cargar_env(ruta: str | Path = ".env") -> None:
    """Lector mínimo de .env (no pisa variables que ya existan)."""
    p = Path(ruta)
    if not p.exists():
        return
    for linea in p.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        k, v = linea.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip("'\""))


def _regex(lista) -> list[re.Pattern]:
    # quitamos tildes del patrón igual que del texto, sin tocar mayúsculas (\S, \W... importan)
    return [re.compile(quitar_tildes(str(x).strip()), re.I) for x in (lista or [])]


def cargar(ruta: str | Path = "config.yaml") -> Config:
    datos = yaml.safe_load(Path(ruta).read_text(encoding="utf-8")) or {}
    exc_comun = datos.get("excluir_comun") or []
    exc_desc = datos.get("excluir_descripcion_comun") or []

    productos = []
    for p in datos.get("productos") or []:
        usado = p.get("segunda_mano") or {}
        nuevo = p.get("nuevo") or {}
        productos.append(Producto(
            nombre=p["nombre"],
            busquedas=p.get("busquedas") or [p["nombre"]],
            incluir=_regex(p.get("incluir") or [re.escape(normalizar(p["nombre"]))]),
            excluir=_regex(exc_comun + (p.get("excluir") or [])),
            excluir_descripcion=_regex(exc_desc + (p.get("excluir_descripcion") or [])),
            usado_min=usado.get("min"), usado_max=usado.get("max"),
            nuevo_min=nuevo.get("min"), nuevo_max=nuevo.get("max"),
        ))
    if not productos:
        raise ValueError("config.yaml no tiene ningún producto en 'productos'")

    nombres = {p.nombre for p in productos}
    tiendas = []
    for t in datos.get("tiendas") or []:
        if t.get("producto") not in nombres:
            raise ValueError(f"La tienda {t.get('nombre')} apunta a un producto que no existe: {t.get('producto')}")
        tiendas.append(Tienda(producto=t["producto"], nombre=t.get("nombre") or "Tienda",
                              url=t["url"], avisar_stock=t.get("avisar_stock", True)))

    ubic = datos.get("ubicacion") or {}
    merc = datos.get("mercado") or {}
    env = os.environ.get
    return Config(
        productos=productos,
        tiendas=tiendas,
        lat=float(ubic.get("lat", 43.3614)),
        lon=float(ubic.get("lon", -5.8494)),
        radio_km=ubic.get("radio_km", 120),
        aceptar_envio=bool(ubic.get("aceptar_envio", True)),
        dias_mercado=int(merc.get("dias", 14)),
        muestras_minimas=int(merc.get("muestras_minimas", 12)),
        descuento_minimo=float(merc.get("descuento_minimo", 0.20)),
        bajada_minima=float(merc.get("bajada_minima_euros", 10)),
        intervalos={"wallapop": 5, "vinted": 10, "chollometro": 10, "tiendas": 30,
                    **(datos.get("intervalos_min") or {})},
        fuentes=datos.get("fuentes") or {},
        feeds_chollometro=datos.get("chollometro_feeds") or ["https://www.chollometro.com/rss/nuevos"],
        paginas_wallapop=int(datos.get("paginas_wallapop", 1)),
        dominio_vinted=datos.get("dominio_vinted", "www.vinted.es"),
        telegram_token=env("TELEGRAM_TOKEN") or None,
        telegram_chat_id=env("TELEGRAM_CHAT_ID") or None,
        callmebot_telefono=env("CALLMEBOT_TELEFONO") or None,
        callmebot_apikey=env("CALLMEBOT_APIKEY") or None,
        ruta_bd=env("RUTA_BD") or "datos/ofertas.db",
    )
