"""Memoria del bot en SQLite: qué ha visto, de qué ha avisado y precios del mercado."""
from __future__ import annotations

import sqlite3
import statistics
import time
from pathlib import Path

from .modelos import Anuncio

_ESQUEMA = """
CREATE TABLE IF NOT EXISTS anuncios (
    clave TEXT PRIMARY KEY,
    fuente TEXT, producto TEXT, titulo TEXT, url TEXT,
    precio REAL, nuevo INTEGER,
    visto_primera REAL, visto_ultima REAL,
    avisado_precio REAL
);
CREATE INDEX IF NOT EXISTS idx_mercado ON anuncios(producto, nuevo, visto_ultima);
CREATE TABLE IF NOT EXISTS stock (
    url TEXT PRIMARY KEY,
    en_stock INTEGER, precio REAL, actualizado REAL, avisado_precio REAL
);
CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT);
"""


class Estado:
    def __init__(self, ruta: str = "datos/ofertas.db"):
        if ruta != ":memory:":
            Path(ruta).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(ruta)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(_ESQUEMA)
        self.purgar()

    # --- anuncios -------------------------------------------------------
    def registrar(self, a: Anuncio, producto: str) -> dict | None:
        """Guarda/actualiza el anuncio. Devuelve cómo estaba antes (o None si es nuevo)."""
        ahora = time.time()
        fila = self.db.execute("SELECT * FROM anuncios WHERE clave=?", (a.clave,)).fetchone()
        if fila is None:
            self.db.execute(
                "INSERT INTO anuncios VALUES (?,?,?,?,?,?,?,?,?,NULL)",
                (a.clave, a.fuente, producto, a.titulo, a.url, a.precio, int(a.nuevo), ahora, ahora))
        else:
            self.db.execute(
                "UPDATE anuncios SET precio=?, titulo=?, visto_ultima=? WHERE clave=?",
                (a.precio, a.titulo, ahora, a.clave))
        self.db.commit()
        return dict(fila) if fila else None

    def marcar_avisado(self, clave: str, precio: float | None) -> None:
        self.db.execute("UPDATE anuncios SET avisado_precio=? WHERE clave=?", (precio, clave))
        self.db.commit()

    def mediana(self, producto: str, dias: int = 14) -> tuple[float | None, int]:
        """Mediana del precio de segunda mano (Wallapop + Vinted) de los últimos `dias`."""
        desde = time.time() - dias * 86400
        precios = [r[0] for r in self.db.execute(
            "SELECT precio FROM anuncios WHERE producto=? AND nuevo=0 AND precio IS NOT NULL "
            "AND visto_ultima>=?", (producto, desde))]
        if not precios:
            return None, 0
        return statistics.median(precios), len(precios)

    def resumen_mercado(self, dias: int = 14) -> list[dict]:
        desde = time.time() - dias * 86400
        filas = self.db.execute(
            "SELECT producto, fuente, precio FROM anuncios WHERE nuevo=0 AND precio IS NOT NULL "
            "AND visto_ultima>=? ORDER BY producto, fuente", (desde,)).fetchall()
        grupos: dict[tuple, list[float]] = {}
        for f in filas:
            grupos.setdefault((f["producto"], f["fuente"]), []).append(f["precio"])
        res = []
        for (prod, fuente), precios in grupos.items():
            precios.sort()
            q = statistics.quantiles(precios, n=4) if len(precios) >= 4 else [precios[0], statistics.median(precios), precios[-1]]
            res.append({"producto": prod, "fuente": fuente, "n": len(precios), "min": precios[0],
                        "p25": q[0], "mediana": statistics.median(precios), "max": precios[-1]})
        return res

    # --- tiendas --------------------------------------------------------
    def stock(self, url: str) -> dict | None:
        fila = self.db.execute("SELECT * FROM stock WHERE url=?", (url,)).fetchone()
        return dict(fila) if fila else None

    def guardar_stock(self, url: str, en_stock: bool | None, precio: float | None,
                      avisado_precio: float | None) -> None:
        self.db.execute(
            "INSERT INTO stock VALUES (?,?,?,?,?) ON CONFLICT(url) DO UPDATE SET "
            "en_stock=excluded.en_stock, precio=excluded.precio, actualizado=excluded.actualizado, "
            "avisado_precio=excluded.avisado_precio",
            (url, None if en_stock is None else int(en_stock), precio, time.time(), avisado_precio))
        self.db.commit()

    # --- varios ---------------------------------------------------------
    def leer(self, clave: str, defecto: str | None = None) -> str | None:
        fila = self.db.execute("SELECT v FROM meta WHERE k=?", (clave,)).fetchone()
        return fila[0] if fila else defecto

    def guardar(self, clave: str, valor) -> None:
        self.db.execute("INSERT OR REPLACE INTO meta VALUES (?, ?)", (clave, str(valor)))
        self.db.commit()

    def calentado(self, clave: str) -> bool:
        return self.db.execute("SELECT 1 FROM meta WHERE k=?", (f"calentado:{clave}",)).fetchone() is not None

    def marcar_calentado(self, clave: str) -> None:
        self.db.execute("INSERT OR REPLACE INTO meta VALUES (?, '1')", (f"calentado:{clave}",))
        self.db.commit()

    def purgar(self, dias: int = 60) -> None:
        self.db.execute("DELETE FROM anuncios WHERE visto_ultima < ?", (time.time() - dias * 86400,))
        self.db.commit()
