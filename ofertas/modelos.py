from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Anuncio:
    """Un anuncio de segunda mano, un chollo o una ficha de tienda, normalizado."""

    fuente: str                 # wallapop | vinted | chollometro | tienda
    id: str
    titulo: str
    precio: float | None
    url: str
    nuevo: bool = False         # True = producto nuevo (chollo o tienda)
    descripcion: str = ""
    imagen: str | None = None
    ciudad: str | None = None
    lat: float | None = None
    lon: float | None = None
    envio: bool | None = None   # el vendedor permite envío
    reservado: bool = False
    tienda: str | None = None
    en_stock: bool | None = None
    estado: str | None = None   # estado de conservación (Vinted)
    precio_total: float | None = None  # precio con la protección al comprador (Vinted)
    publicado: float | None = None     # epoch (segundos) en que se publicó
    vendedor: str | None = None        # id del vendedor (Wallapop)

    @property
    def clave(self) -> str:
        return f"{self.fuente}:{self.id}"
