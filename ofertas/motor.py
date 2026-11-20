"""Bucle principal: consulta cada fuente a su ritmo, decide qué es buena oferta y avisa."""
from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass

from . import avisos
from .config import Config, Producto
from .estado import Estado
from .fuentes import chollometro, tiendas, wallapop
from .fuentes.vinted import Vinted
from .modelos import Anuncio
from .red import ERRORES_RED, Bloqueado, sesion_navegador
from .utiles import distancia_km, euros

log = logging.getLogger(__name__)
FUENTES = ("wallapop", "vinted", "chollometro", "tiendas")
FALLOS_PARA_AVISAR = 6


@dataclass
class Veredicto:
    avisar: bool
    motivo: str = ""
    mediana: float | None = None
    muestras: int = 0
    sospechoso: bool = False


class Motor:
    def __init__(self, cfg: Config, estado: Estado, avisador: avisos.Avisador,
                 sin_calentamiento: bool = False, pausa: tuple[float, float] = (2.0, 5.0)):
        self.cfg = cfg
        self.estado = estado
        self.avisador = avisador
        self.sin_calentamiento = sin_calentamiento
        self.pausa = pausa
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
        for fuente in FUENTES:
            if not self.cfg.activa(fuente) or (fuente == "tiendas" and not self.cfg.tiendas):
                continue
            if not forzar and time.time() < self.proxima[fuente] - margen:
                continue
            fallo = None
            try:
                getattr(self, f"_ciclo_{fuente}")()
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
        return self.avisos_enviados - antes

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
        clave_cal = f"{fuente}:{prod.nombre}"
        calentando = not self.sin_calentamiento and not self.estado.calentado(clave_cal)
        vistos: set[str] = set()
        candidatos: list[tuple[Anuncio, Veredicto, float | None]] = []

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
                candidatos.append((a, v, dist))

        if calentando:
            self.estado.marcar_calentado(clave_cal)
            for a, _, _ in candidatos:
                self.estado.marcar_avisado(a.clave, a.precio)
            log.info("%s · %s: primera pasada, %d anuncios válidos, %d ya cumplen filtros",
                     fuente, prod.nombre, len(vistos), len(candidatos))
            if candidatos:
                self._mandar(avisos.formatear_resumen(
                    prod.nombre, fuente, [(a, v) for a, v, _ in candidatos], total=8))
            return

        for a, v, dist in candidatos:
            aviso = avisos.formatear(a, prod.nombre, v.motivo, v.mediana, v.muestras, dist, v.sospechoso)
            if self._mandar(aviso):
                self.estado.marcar_avisado(a.clave, a.precio)
        log.info("%s · %s: %d anuncios válidos, %d avisos", fuente, prod.nombre,
                 len(vistos), len(candidatos))

    def evaluar(self, a: Anuncio, prod: Producto, previo: dict | None) -> Veredicto:
        _, pmax = prod.limites(a.nuevo)
        mediana, n = (None, 0) if a.nuevo else self.estado.mediana(prod.nombre, self.cfg.dias_mercado)
        fiable = mediana is not None and n >= self.cfg.muestras_minimas

        motivo = ""
        if pmax is not None and a.precio <= pmax:
            motivo = f"Por debajo de tu máximo ({euros(pmax)})"
        elif fiable and a.precio <= mediana * (1 - self.cfg.descuento_minimo):
            motivo = f"Un {round((1 - a.precio / mediana) * 100)}% más barato que la mediana del mercado"
        if not motivo:
            return Veredicto(False)

        avisado = previo.get("avisado_precio") if previo else None
        if avisado is not None:
            if a.precio > avisado - self.cfg.bajada_minima:
                return Veredicto(False)    # ya te avisé y no ha bajado lo suficiente
            motivo = f"Ha bajado de {euros(avisado)} a {euros(a.precio)}. {motivo}"

        return Veredicto(True, motivo, mediana if fiable else None, n,
                         sospechoso=bool(fiable and a.precio < mediana * 0.5))

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
            self._mandar(avisos.formatear(a, prod.nombre, motivo))

    def _mandar(self, aviso: avisos.Aviso) -> bool:
        ok = self.avisador.enviar(aviso)
        if ok:
            self.avisos_enviados += 1
        return ok
