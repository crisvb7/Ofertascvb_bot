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
    tope: float | None = None           # por encima de esto no avisa nunca
    accesorios: list[re.Pattern] = field(default_factory=list)
    pistas_consola: list[re.Pattern] = field(default_factory=list)
    dudas: list[re.Pattern] = field(default_factory=list)
    otros_productos: list[re.Pattern] = field(default_factory=list)   # "incluir" del resto de productos
    tipo: str = "consola"               # consola | componente (pieza de PC)

    @property
    def es_componente(self) -> bool:
        return self.tipo == "componente"

    def clasificar(self, a: Anuncio) -> tuple[str | None, str]:
        """('consola', '') si es este producto; ('dudosa', motivo) si no está claro; (None, '') si no.

        Ante la duda se manda (marcada para revisar) en vez de saltársela. En los componentes
        solo cuenta el accesorio con el que EMPIEZA el título ("Disipador para Ryzen 7 5700X3D");
        uno mencionado en medio ("Ryzen 7 5700X3D con disipador") no los hace dudosos."""
        t = normalizar(a.titulo)
        propias = [m.start() for p in self.incluir for m in [p.search(t)] if m]
        if not propias:
            return None, ""
        if any(p.search(t) for p in self.excluir):
            return None, ""
        # "PS5 FAT con lector + cambio Xbox Series X" es una PS5, no una Xbox
        otras = [m.start() for p in self.otros_productos for m in [p.search(t)] if m]
        if otras and min(otras) < min(propias):
            return None, ""
        if self.excluir_descripcion and a.descripcion:
            d = normalizar(a.descripcion)
            if any(p.search(d) for p in self.excluir_descripcion):
                return None, ""

        pista = next((m for p in self.pistas_consola for m in [p.search(t)] if m), None)
        sin_simbolos = re.sub(r"^[^a-z0-9]+", "", t)
        empieza_acc = next((m for p in self.accesorios for m in [p.match(sin_simbolos)] if m), None)
        acc = empieza_acc or next((m for p in self.accesorios for m in [p.search(t)] if m), None)
        duda = next((m for p in self.dudas for m in [p.search(t)] if m), None)

        if empieza_acc:
            # "Mando DualSense PS5", "Volant ps5", "Juego GTA PS5": un accesorio o un juego
            if pista:
                return "dudosa", f"empieza por «{empieza_acc.group(0).strip()}» aunque dice «{pista.group(0).strip()}»"
            return None, ""
        if duda:
            return "dudosa", f"pone «{duda.group(0).strip()}»"
        if acc and not pista and not self.es_componente:
            return "dudosa", f"habla de «{acc.group(0).strip()}» y no dice claramente que sea la consola"
        return "consola", ""

    def coincide(self, a: Anuncio) -> bool:
        return self.clasificar(a)[0] is not None

    def limites(self, nuevo: bool) -> tuple[float | None, float | None]:
        return (self.nuevo_min, self.nuevo_max) if nuevo else (self.usado_min, self.usado_max)


@dataclass
class Tienda:
    producto: str
    nombre: str
    url: str
    avisar_stock: bool = True


@dataclass
class FiltroFalsos:
    activo: bool = True
    sin_valoraciones: bool = True       # quita vendedores sin ninguna valoración
    dias_cuenta_min: float = 30         # quita cuentas creadas menos de N días antes del anuncio
    fotos_repetidas: bool = True        # quita anuncios con la foto de otro anuncio de otro vendedor
    frases: list[re.Pattern] = field(default_factory=list)   # contacto/pago fuera de la plataforma


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
    avisar_todas: bool = True           # False = solo ofertones
    max_por_pasada: int | None = 25     # mensajes como mucho por pasada
    comprobar_estado: bool = True       # revisar si los anuncios avisados siguen disponibles
    dias_seguimiento: float = 3         # cuántos días se siguen e indexan los avisos
    telegram_grupo_id: str | None = None
    telegram_temas: dict = field(default_factory=dict)
    telegram_nombre_grupo: str | None = None
    intervalos: dict = field(default_factory=dict)
    fuentes: dict = field(default_factory=dict)
    feeds_chollometro: list[str] = field(default_factory=list)
    paginas_wallapop: int = 1
    dominio_vinted: str = "www.vinted.es"
    antifraude: FiltroFalsos = field(default_factory=FiltroFalsos)
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
    # Cada tipo de producto tiene sus propias reglas para decidir si el anuncio es "la cosa":
    # las consolas usan los bloques de arriba de config.yaml; las piezas de PC, el bloque "componentes".
    comp = datos.get("componentes") or {}
    reglas = {
        "consola": dict(excluir=[], excluir_descripcion=[],
                        accesorios=_regex(datos.get("accesorios") or []),
                        pistas=_regex(datos.get("pistas_consola") or []),
                        dudas=_regex(datos.get("dudas") or [])),
        "componente": dict(excluir=comp.get("excluir") or [],
                           excluir_descripcion=comp.get("excluir_descripcion") or [],
                           accesorios=_regex(comp.get("accesorios") or []),
                           pistas=_regex(comp.get("pistas") or []),
                           dudas=_regex(comp.get("dudas") or [])),
    }

    productos = []
    for p in datos.get("productos") or []:
        usado = p.get("segunda_mano") or {}
        nuevo = p.get("nuevo") or {}
        tipo = str(p.get("tipo") or "consola").strip().lower()
        if tipo not in reglas:
            raise ValueError(f"El producto {p['nombre']} tiene un tipo que no existe: {tipo} "
                             "(usa «consola» o «componente»)")
        r = reglas[tipo]
        productos.append(Producto(
            nombre=p["nombre"],
            busquedas=p.get("busquedas") or [p["nombre"]],
            incluir=_regex(p.get("incluir") or [re.escape(normalizar(p["nombre"]))]),
            excluir=_regex(exc_comun + r["excluir"] + (p.get("excluir") or [])),
            excluir_descripcion=_regex(exc_desc + r["excluir_descripcion"] + (p.get("excluir_descripcion") or [])),
            usado_min=usado.get("min"), usado_max=usado.get("max"),
            nuevo_min=nuevo.get("min"), nuevo_max=nuevo.get("max"),
            tope=p.get("tope"),
            accesorios=r["accesorios"],
            pistas_consola=r["pistas"],
            dudas=r["dudas"],
            tipo=tipo,
        ))
    if not productos:
        raise ValueError("config.yaml no tiene ningún producto en 'productos'")
    for p in productos:
        p.otros_productos = [patron for q in productos if q is not p for patron in q.incluir]

    nombres = {p.nombre for p in productos}
    tiendas = []
    for t in datos.get("tiendas") or []:
        if t.get("producto") not in nombres:
            raise ValueError(f"La tienda {t.get('nombre')} apunta a un producto que no existe: {t.get('producto')}")
        tiendas.append(Tienda(producto=t["producto"], nombre=t.get("nombre") or "Tienda",
                              url=t["url"], avisar_stock=t.get("avisar_stock", True)))

    ubic = datos.get("ubicacion") or {}
    merc = datos.get("mercado") or {}
    av = datos.get("avisos") or {}
    tg = datos.get("telegram") or {}
    af = datos.get("antifraude") or {}
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
        avisar_todas=bool(av.get("todas", True)),
        max_por_pasada=av.get("max_por_pasada", 25) or None,
        comprobar_estado=bool(av.get("comprobar_estado", True)),
        dias_seguimiento=float(av.get("dias_seguimiento", 3)),
        telegram_grupo_id=str(env("TELEGRAM_GRUPO_ID") or tg.get("grupo_id") or "") or None,
        telegram_temas={k: v for k, v in (tg.get("temas") or {}).items() if v},
        telegram_nombre_grupo=str(tg.get("nombre") or "").strip() or None,
        intervalos={"wallapop": 5, "vinted": 10, "cex": 30, "cashconverters": 30, "carrefour": 15,
                    "game": 15, "elcorteingles": 15, "chollometro": 10, "tiendas": 30,
                    **(datos.get("intervalos_min") or {})},
        fuentes=datos.get("fuentes") or {},
        feeds_chollometro=datos.get("chollometro_feeds") or ["https://www.chollometro.com/rss/nuevos"],
        paginas_wallapop=int(datos.get("paginas_wallapop", 1)),
        dominio_vinted=datos.get("dominio_vinted", "www.vinted.es"),
        antifraude=FiltroFalsos(
            activo=bool(af.get("activo", True)),
            sin_valoraciones=bool(af.get("sin_valoraciones", True)),
            dias_cuenta_min=float(af.get("dias_cuenta_min", 30) or 0),
            fotos_repetidas=bool(af.get("fotos_repetidas", True)),
            frases=[re.compile(f, re.I) for f in af.get("frases") or []],
        ),
        telegram_token=env("TELEGRAM_TOKEN") or None,
        telegram_chat_id=env("TELEGRAM_CHAT_ID") or None,
        callmebot_telefono=env("CALLMEBOT_TELEFONO") or None,
        callmebot_apikey=env("CALLMEBOT_APIKEY") or None,
        ruta_bd=env("RUTA_BD") or "datos/ofertas.db",
    )
