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
CREATE TABLE IF NOT EXISTS vendedores (
    id TEXT PRIMARY KEY, fuente TEXT, nombre TEXT, alta REAL,
    valoraciones INTEGER, nota REAL, ventas INTEGER, leido REAL
);
CREATE TABLE IF NOT EXISTS fotos (
    clave TEXT PRIMARY KEY, huella INTEGER, fuente TEXT, vendedor TEXT,
    precio REAL, orden REAL, visto REAL
);
CREATE TABLE IF NOT EXISTS mensajes (
    clave TEXT PRIMARY KEY,
    fuente TEXT, item_id TEXT, producto TEXT, categoria TEXT,
    chat_id TEXT, message_id INTEGER, con_foto INTEGER, html TEXT,
    precio REAL, titulo TEXT, url TEXT, ciudad TEXT,
    publicado REAL, enviado REAL, comprobado REAL,
    estado TEXT DEFAULT 'disponible'
);
CREATE INDEX IF NOT EXISTS idx_mensajes ON mensajes(categoria, enviado);
"""


class Estado:
    def __init__(self, ruta: str = "datos/ofertas.db"):
        if ruta != ":memory:":
            Path(ruta).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(ruta)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(_ESQUEMA)
        self._migrar_secciones()
        self.purgar()

    def _migrar_secciones(self) -> None:
        """v1 tenía 3 categorías; ahora hay secciones nueva_* / usada_*."""
        if self.leer("migracion:secciones"):
            return
        viejas = ("oferton", "buen_precio", "resto")
        self.db.execute(
            "UPDATE mensajes SET categoria = (CASE WHEN fuente IN "
            "('chollometro','carrefour','game','elcorteingles','tienda') THEN 'nueva_' ELSE 'usada_' END) "
            "|| categoria WHERE categoria IN ('oferton','buen_precio','resto')")
        self.db.execute("UPDATE mensajes SET categoria='nueva_buen_precio' WHERE categoria='nueva_resto'")
        for (k,) in self.db.execute("SELECT k FROM meta").fetchall():
            partes = k.split(":")
            if len(partes) == 3 and partes[0] in ("tema", "indice", "indice_hash") and partes[2] in viejas:
                self.db.execute("UPDATE meta SET k=? WHERE k=?", (f"{partes[0]}:{partes[1]}:usada_{partes[2]}", k))
        self.guardar("migracion:secciones", "1")

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
            "AND visto_ultima>=? AND fuente IN ('wallapop','vinted')", (producto, desde))]
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

    # --- mensajes enviados (para actualizarlos) --------------------------
    def mensaje(self, clave: str) -> dict | None:
        fila = self.db.execute("SELECT * FROM mensajes WHERE clave=?", (clave,)).fetchone()
        return dict(fila) if fila else None

    def guardar_mensaje(self, a, item_id: str, producto: str, categoria: str, ref: dict | None,
                        html: str) -> None:
        ref = ref or {}
        ahora = time.time()
        self.db.execute(
            "INSERT OR REPLACE INTO mensajes VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'disponible')",
            (a.clave, a.fuente, item_id, producto, categoria, ref.get("chat_id"), ref.get("message_id"),
             int(bool(ref.get("con_foto"))), html, a.precio, a.titulo, a.url, a.ciudad,
             a.publicado or ahora, ahora, ahora))
        self.db.commit()

    def actualizar_mensaje(self, clave: str, **campos) -> None:
        if not campos:
            return
        sets = ", ".join(f"{k}=?" for k in campos)
        self.db.execute(f"UPDATE mensajes SET {sets} WHERE clave=?", (*campos.values(), clave))
        self.db.commit()

    def mensajes_a_comprobar(self, fuente: str, dias: float, cada_min: float, limite: int) -> list[dict]:
        ahora = time.time()
        filas = self.db.execute(
            "SELECT * FROM mensajes WHERE fuente=? AND estado NOT IN ('vendida','descartada','borrada') AND enviado>=? "
            "AND comprobado<=? ORDER BY comprobado LIMIT ?",
            (fuente, ahora - dias * 86400, ahora - cada_min * 60, limite)).fetchall()
        return [dict(f) for f in filas]

    def mensajes_recientes(self, dias: float, con_descartadas: bool = False) -> list[dict]:
        filtro = "" if con_descartadas else " AND estado!='descartada'"
        filas = self.db.execute("SELECT * FROM mensajes WHERE enviado>=?" + filtro + " AND estado!='borrada'",
                                (time.time() - dias * 86400,)).fetchall()
        return [dict(f) for f in filas]

    def mensajes_categoria(self, categoria: str, dias: float) -> list[dict]:
        filas = self.db.execute(
            "SELECT * FROM mensajes WHERE categoria=? AND enviado>=? AND estado!='borrada' ORDER BY publicado DESC",
            (categoria, time.time() - dias * 86400)).fetchall()
        return [dict(f) for f in filas]

    def olvidar_avisos(self, productos: list[str] | None = None) -> None:
        """Hace que los anuncios vuelvan a enviarse (p. ej. al estrenar el grupo); solo los de
        `productos` si se dan."""
        if productos is None:
            self.db.execute("UPDATE anuncios SET avisado_precio=NULL")
        elif productos:
            marcas = ",".join("?" * len(productos))
            self.db.execute(f"UPDATE anuncios SET avisado_precio=NULL WHERE producto IN ({marcas})", productos)
        self.db.commit()

    def minimo_nuevo(self, producto: str, dias: float = 3) -> float | None:
        """El precio más bajo al que se ha visto el producto nuevo en los últimos `dias`."""
        fila = self.db.execute(
            "SELECT MIN(precio) FROM anuncios WHERE producto=? AND nuevo=1 AND precio IS NOT NULL "
            "AND visto_ultima>=?", (producto, time.time() - dias * 86400)).fetchone()
        return fila[0] if fila and fila[0] is not None else None

    # --- antifraude -----------------------------------------------------
    def vendedor(self, id_: str, max_horas: float = 12) -> dict | None:
        fila = self.db.execute("SELECT * FROM vendedores WHERE id=? AND leido>=?",
                               (id_, time.time() - max_horas * 3600)).fetchone()
        return dict(fila) if fila else None

    def guardar_vendedor(self, id_: str, fuente: str, datos: dict) -> None:
        self.db.execute("INSERT OR REPLACE INTO vendedores VALUES (?,?,?,?,?,?,?,?)",
                        (id_, fuente, datos.get("nombre"), datos.get("alta"), datos.get("valoraciones"),
                         datos.get("nota"), datos.get("ventas"), time.time()))
        self.db.commit()

    def foto(self, clave: str) -> dict | None:
        fila = self.db.execute("SELECT rowid AS fila, * FROM fotos WHERE clave=?", (clave,)).fetchone()
        return dict(fila) if fila else None

    def guardar_foto(self, a: Anuncio, huella: int) -> None:
        ahora = time.time()
        self.db.execute("INSERT OR IGNORE INTO fotos VALUES (?,?,?,?,?,?,?)",
                        (a.clave, huella, a.fuente, a.vendedor, a.precio, a.publicado or ahora, ahora))
        self.db.commit()

    def fotos_anteriores(self, foto: dict) -> list[dict]:
        """Las fotos de otros anuncios publicados antes que este (las candidatas a ser el original)."""
        filas = self.db.execute(
            "SELECT rowid AS fila, * FROM fotos WHERE clave!=? AND (orden<? OR (orden=? AND rowid<?))",
            (foto["clave"], foto["orden"], foto["orden"], foto["fila"])).fetchall()
        return [dict(f) for f in filas]

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
        limite = time.time() - dias * 86400
        self.db.execute("DELETE FROM anuncios WHERE visto_ultima < ?", (limite,))
        self.db.execute("DELETE FROM mensajes WHERE enviado < ?", (limite,))
        self.db.execute("DELETE FROM fotos WHERE visto < ?", (limite,))
        self.db.execute("DELETE FROM vendedores WHERE leido < ?", (limite,))
        self.db.commit()
