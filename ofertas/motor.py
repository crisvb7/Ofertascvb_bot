"""Bucle principal: consulta cada fuente a su ritmo, decide qué es buena oferta y avisa."""
from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass

from . import avisos
from .config import Config, Producto
from .estado import Estado
from .fuentes import cashconverters, carrefour, cex, chollometro, elcorteingles, game, tiendas, wallapop
from .fuentes.vinted import Vinted
from .modelos import Anuncio
from .red import ERRORES_RED, Bloqueado, sesion_navegador
from .utiles import distancia_km, euros

log = logging.getLogger(__name__)
FUENTES = ("wallapop", "vinted", "cex", "cashconverters", "carrefour", "game", "elcorteingles",
           "chollometro", "tiendas")
# fuentes que solo necesitan (sesión, búsqueda); True = buscar "consola <producto>" una vez
SIMPLES = {
    "cex": (cex, False),
    "cashconverters": (cashconverters, False),
    "carrefour": (carrefour, True),
    "game": (game, True),
    "elcorteingles": (elcorteingles, True),
}
FALLOS_PARA_AVISAR = 6


@dataclass
class Veredicto:
    avisar: bool
    motivo: str = ""
    mediana: float | None = None
    muestras: int = 0
    sospechoso: bool = False
    oferton: bool = False
    categoria: str = "resto"          # oferton | buen_precio | resto


class Motor:
    def __init__(self, cfg: Config, estado: Estado, avisador: avisos.Avisador,
                 pausa: tuple[float, float] = (2.0, 5.0)):
        self.cfg = cfg
        self.estado = estado
        self.avisador = avisador
        self.pausa = pausa
        self.pendientes: list[tuple[Anuncio, Veredicto, float | None, str]] = []
        self.sesion = sesion_navegador()
        self.vinted = Vinted(sesion_navegador(), cfg.dominio_vinted)
        # El ritmo de cada fuente se guarda en la BD: así sobrevive a reinicios y funciona
        # también cuando el bot se ejecuta a ratos (GitHub Actions, cron).
        self.proxima = {f: float(estado.leer(f"proxima:{f}", "0")) for f in FUENTES}
        self.castigo = {f: int(estado.leer(f"castigo:{f}", "1")) for f in FUENTES}
        self.fallos = {f: int(estado.leer(f"fallos:{f}", "0")) for f in FUENTES}
        self.avisos_enviados = 0

    # --- planificación ----------------------------------------------------
    def ciclo(self, forzar: bool = False, margen: float = 0) -> int:
        """Ejecuta las fuentes a las que les toca. Devuelve cuántos avisos ha mandado.

        `margen` (segundos) adelanta las fuentes a las que les falta poco: útil cuando el bot
        se lanza cada X minutos desde fuera y no puede esperar al momento exacto."""
        antes = self.avisos_enviados
        self.pendientes = []
        self._estrenar_grupo()
        for fuente in FUENTES:
            if not self.cfg.activa(fuente) or (fuente == "tiendas" and not self.cfg.tiendas):
                continue
            if not forzar and time.time() < self.proxima[fuente] - margen:
                continue
            fallo = None
            try:
                metodo = getattr(self, f"_ciclo_{fuente}", None)
                metodo() if metodo else self._ciclo_simple(fuente)
                self.castigo[fuente] = 1
            except Bloqueado as e:
                self.castigo[fuente] = min(self.castigo[fuente] * 2, 12)
                fallo = str(e)
                log.warning("%s: %s. Bajo el ritmo (x%d).", fuente, e, self.castigo[fuente])
            except ERRORES_RED as e:
                self.castigo[fuente] = min(self.castigo[fuente] * 2, 4)
                fallo = "error de red"
                log.warning("%s: error de red (%s). Reintento más tarde.", fuente, str(e)[:160])
            except Exception as e:
                fallo = f"error inesperado ({type(e).__name__})"
                log.exception("Error inesperado en %s", fuente)
            self._vigilar_salud(fuente, fallo)
            minutos = float(self.cfg.intervalos.get(fuente, 10)) * self.castigo[fuente]
            self.proxima[fuente] = time.time() + minutos * 60 * random.uniform(0.85, 1.15)
            self.estado.guardar(f"proxima:{fuente}", self.proxima[fuente])
            self.estado.guardar(f"castigo:{fuente}", self.castigo[fuente])
            self.estado.guardar(f"fallos:{fuente}", self.fallos[fuente])
        self._enviar_pendientes()
        for paso in (self._comprobar_estados, self._actualizar_indices):
            try:
                paso()
            except Exception:
                log.exception("Error en %s", paso.__name__)
        return self.avisos_enviados - antes

    def _enviar_pendientes(self) -> None:
        """Manda las ofertas de esta pasada una a una, de la más barata a la más cara."""
        if not self.pendientes:
            return
        orden = sorted(self.pendientes, key=lambda p: p[0].precio)
        tope = self.cfg.max_por_pasada
        enviar, resto = (orden[:tope], orden[tope:]) if tope else (orden, [])
        for a, v, dist, producto in enviar:
            aviso = avisos.formatear(a, producto, v.motivo, v.mediana, v.muestras, dist,
                                     v.sospechoso, categoria=v.categoria)
            anterior = self.estado.mensaje(a.clave)
            ref = self.avisador.enviar_oferta(aviso, v.categoria)
            if ref is None:
                continue
            self.avisos_enviados += 1
            self.estado.marcar_avisado(a.clave, a.precio)
            if anterior and anterior.get("message_id"):   # el aviso viejo: "ha bajado, mira el nuevo"
                self.avisador.editar(anterior, avisos.con_estado(
                    anterior["html"], avisos.prefijo_estado("rebajada", a.precio), bool(anterior["con_foto"])))
            self.estado.guardar_mensaje(a, a.id, producto, v.categoria, ref, aviso.html)
        if resto:
            log.info("%d ofertas más caras quedan para la próxima pasada", len(resto))
        self.pendientes = []

    def _comprobar_estados(self) -> None:
        """Mira si los anuncios avisados siguen publicados y actualiza sus mensajes."""
        if not (self.cfg.comprobar_estado and self.cfg.activa("wallapop")):
            return
        filas = self.estado.mensajes_a_comprobar("wallapop", self.cfg.dias_seguimiento,
                                                 cada_min=25, limite=15)
        cambios = 0
        for f in filas:
            try:
                estado, precio = wallapop.estado(self.sesion, f["item_id"])
            except (Bloqueado, *ERRORES_RED) as e:
                log.warning("No he podido comprobar un anuncio: %s", str(e)[:120])
                break
            campos = {"comprobado": time.time()}
            precio_cambia = precio is not None and f["precio"] is not None and abs(precio - f["precio"]) >= 1
            if estado != f["estado"] or precio_cambia:
                prefijo = avisos.prefijo_estado(estado, precio, f["precio"] if precio_cambia else None)
                html_nuevo = avisos.con_estado(f["html"], prefijo, bool(f["con_foto"]))
                if f.get("message_id"):
                    self.avisador.editar(f, html_nuevo)
                campos["estado"] = estado
                if precio_cambia:
                    campos["precio"] = precio
                cambios += 1
            self.estado.actualizar_mensaje(f["clave"], **campos)
            self._dormir_corto()
        if filas:
            log.info("Seguimiento: %d anuncios comprobados, %d cambios", len(filas), cambios)

    def _actualizar_indices(self) -> None:
        if not self.avisador.con_grupo:
            return
        for categoria in avisos.CATEGORIAS:
            filas = self.estado.mensajes_categoria(categoria, self.cfg.dias_seguimiento)
            if filas or self.estado.leer(f"indice:{self.avisador.grupo_id}:{categoria}"):
                self.avisador.indice(categoria, avisos.construir_indice(
                    categoria, filas, self.cfg.dias_seguimiento))

    def _estrenar_grupo(self) -> None:
        """La primera vez que se usa un grupo, vuelve a mandar lo que sigue publicado."""
        if not self.avisador.con_grupo:
            return
        clave = f"grupo_estrenado:{self.avisador.grupo_id}"
        if not self.estado.leer(clave):
            self.estado.olvidar_avisos()
            self.estado.guardar(clave, "1")
            log.info("Grupo nuevo: reenvío las ofertas que siguen publicadas")

    def _vigilar_salud(self, fuente: str, fallo: str | None) -> None:
        """Si una fuente lleva muchos fallos seguidos te lo dice (una vez), y cuando vuelve."""
        if fallo is None:
            if self.fallos[fuente] >= FALLOS_PARA_AVISAR:
                self._mandar(avisos.Aviso(html=f"✅ {fuente} vuelve a funcionar.",
                                          texto=f"✅ {fuente} vuelve a funcionar."))
            self.fallos[fuente] = 0
            return
        self.fallos[fuente] += 1
        if self.fallos[fuente] == FALLOS_PARA_AVISAR:
            txt = (f"⚠️ {fuente} lleva {FALLOS_PARA_AVISAR} intentos seguidos fallando ({fallo}). "
                   "Puede que hayan cambiado su web o te estén bloqueando; sigo reintentando.")
            self._mandar(avisos.Aviso(html=txt, texto=txt))

    def _dormir_corto(self) -> None:
        if self.pausa[1] > 0:
            time.sleep(random.uniform(0.8, 1.6))

    def _dormir(self) -> None:
        if self.pausa[1] > 0:
            time.sleep(random.uniform(*self.pausa))

    # --- fuentes ----------------------------------------------------------
    def _ciclo_wallapop(self) -> None:
        for prod in self.cfg.productos:
            encontrados: list[Anuncio] = []
            for q in prod.busquedas:
                encontrados += wallapop.buscar(self.sesion, q, self.cfg.lat, self.cfg.lon,
                                               prod.usado_min, self.cfg.paginas_wallapop)
                self._dormir()
            self.procesar(encontrados, prod, "wallapop")

    def _ciclo_vinted(self) -> None:
        for prod in self.cfg.productos:
            encontrados: list[Anuncio] = []
            for q in prod.busquedas:
                encontrados += self.vinted.buscar(q, prod.usado_min)
                self._dormir()
            self.procesar(encontrados, prod, "vinted")

    def _ciclo_simple(self, fuente: str) -> None:
        modulo, de_tienda = SIMPLES[fuente]
        for prod in self.cfg.productos:
            consultas = [f"consola {prod.busquedas[0]}"] if de_tienda else prod.busquedas
            encontrados: list[Anuncio] = []
            for q in consultas:
                encontrados += modulo.buscar(self.sesion, q)
                self._dormir()
            self.procesar(encontrados, prod, fuente)

    def _ciclo_chollometro(self) -> None:
        chollos: list[Anuncio] = []
        for url in self.cfg.feeds_chollometro:
            chollos += chollometro.leer(self.sesion, url)
        for prod in self.cfg.productos:
            self.procesar(chollos, prod, "chollometro")

    def _ciclo_tiendas(self) -> None:
        for t in self.cfg.tiendas:
            prod = self.cfg.producto(t.producto)
            try:
                info = tiendas.consultar(self.sesion, t.url)
            except (Bloqueado, *ERRORES_RED) as e:
                log.warning("%s: %s", t.nombre, str(e)[:160])
                continue
            self.procesar_tienda(t, prod, info)
            self._dormir()

    # --- lógica de ofertas --------------------------------------------------
    def procesar(self, anuncios: list[Anuncio], prod: Producto, fuente: str) -> None:
        """Filtra y evalúa; las ofertas se mandan al final de la pasada, ordenadas por precio."""
        vistos: set[str] = set()
        n_ofertas = 0
        for a in anuncios:
            if a.precio is None or a.reservado or not prod.coincide(a):
                continue
            if a.clave in vistos:          # la misma consola sale en varias búsquedas
                continue
            vistos.add(a.clave)
            pmin, _ = prod.limites(a.nuevo)
            if pmin is not None and a.precio < pmin:
                continue                   # accesorio, juego, caja vacía, cuota mensual...
            previo = self.estado.registrar(a, prod.nombre)

            dist = None
            if a.lat is not None and a.lon is not None:
                dist = distancia_km(self.cfg.lat, self.cfg.lon, a.lat, a.lon)
                if (self.cfg.radio_km and dist > self.cfg.radio_km
                        and not (self.cfg.aceptar_envio and a.envio)):
                    continue

            v = self.evaluar(a, prod, previo)
            if v.avisar:
                self.pendientes.append((a, v, dist, prod.nombre))
                n_ofertas += 1
        log.info("%s · %s: %d anuncios válidos, %d para avisar", fuente, prod.nombre,
                 len(vistos), n_ofertas)

    def evaluar(self, a: Anuncio, prod: Producto, previo: dict | None) -> Veredicto:
        _, pmax = prod.limites(a.nuevo)
        if prod.tope is not None and a.precio > prod.tope:
            return Veredicto(False)        # más caro que nueva: no interesa
        mediana, n = (None, 0) if a.nuevo else self.estado.mediana(prod.nombre, self.cfg.dias_mercado)
        fiable = mediana is not None and n >= self.cfg.muestras_minimas

        oferton = False
        if pmax is not None and a.precio <= pmax:
            oferton, motivo = True, f"Por debajo de tu máximo ({euros(pmax)})"
        elif fiable and a.precio <= mediana * (1 - self.cfg.descuento_minimo):
            oferton = True
            motivo = f"Un {round((1 - a.precio / mediana) * 100)}% más barato que la mediana del mercado"
        elif pmax is not None:
            motivo = f"{euros(a.precio - pmax)} por encima de tu máximo ({euros(pmax)})"
        else:
            motivo = ""
        if not oferton and not self.cfg.avisar_todas:
            return Veredicto(False)
        if oferton:
            categoria = "oferton"
        elif a.nuevo:
            categoria = "buen_precio"          # chollo de tienda por debajo del PVP
        elif fiable:
            categoria = "buen_precio" if a.precio <= mediana else "resto"
        else:
            categoria = "buen_precio" if pmax is not None and a.precio <= pmax * 1.15 else "resto"

        avisado = previo.get("avisado_precio") if previo else None
        if avisado is not None:
            if a.precio > avisado - self.cfg.bajada_minima:
                return Veredicto(False)    # ya te avisé y no ha bajado lo suficiente
            motivo = f"Ha bajado de {euros(avisado)} a {euros(a.precio)}. {motivo}"

        return Veredicto(True, motivo, mediana if fiable else None, n,
                         sospechoso=bool(fiable and a.precio < mediana * 0.5), oferton=oferton,
                         categoria=categoria)

    def procesar_tienda(self, t, prod: Producto, info: dict) -> None:
        precio, en_stock = info.get("precio"), info.get("en_stock")
        anterior = self.estado.stock(t.url)
        avisado = anterior.get("avisado_precio") if anterior else None
        _, pmax = prod.limites(True)
        a = Anuncio(fuente="tienda", id=t.url, titulo=info.get("nombre") or f"{prod.nombre} en {t.nombre}",
                    precio=precio, url=t.url, nuevo=True, imagen=info.get("imagen"),
                    tienda=t.nombre, en_stock=en_stock)

        motivo = None
        buen_precio = precio is not None and pmax is not None and precio <= pmax and en_stock is not False
        if buen_precio and (avisado is None or precio <= avisado - self.cfg.bajada_minima):
            motivo = f"Por debajo de tu máximo ({euros(pmax)})" + ("" if en_stock is None else " y con stock")
            avisado = precio
        elif (t.avisar_stock and anterior is not None and anterior.get("en_stock") == 0
              and en_stock is True):
            motivo = "¡Vuelve a haber stock!"
        if not buen_precio:
            avisado = None                 # si vuelve a bajar más adelante, se avisa otra vez

        self.estado.guardar_stock(t.url, en_stock, precio, avisado)
        log.info("%s · %s: %s, stock=%s", t.nombre, prod.nombre, euros(precio), en_stock)
        if motivo:
            aviso = avisos.formatear(a, prod.nombre, motivo, categoria="oferton" if buen_precio else "resto")
            if self.avisador.enviar_oferta(aviso, "oferton" if buen_precio else "resto") is not None:
                self.avisos_enviados += 1

    def _mandar(self, aviso: avisos.Aviso) -> bool:
        ok = self.avisador.enviar(aviso)
        if ok:
            self.avisos_enviados += 1
        return ok
