#!/usr/bin/env python3
"""Bot de ofertas de consolas: Wallapop, Vinted, Chollometro y tiendas → Telegram/WhatsApp.

Uso:
  python bot.py                 # funciona sin parar (lo normal)
  python bot.py --chat-id       # te dice tu TELEGRAM_CHAT_ID (escríbele antes al bot)
  python bot.py --prueba        # manda un aviso de prueba
  python bot.py --simular       # una pasada mostrando en pantalla lo que avisaría, sin enviar
  python bot.py --una-vez       # una pasada y termina (cron, GitHub Actions)
  python bot.py --mercado       # precios de segunda mano que ha ido viendo
  python bot.py --diagnostico   # comprueba cada plataforma y te manda un informe
"""
from __future__ import annotations

import argparse
import logging
import signal
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
sys.path.insert(0, str(RAIZ))

from ofertas import __version__, avisos, config  # noqa: E402
from ofertas.estado import Estado  # noqa: E402
from ofertas.motor import Motor  # noqa: E402
from ofertas.red import MOTOR  # noqa: E402
from ofertas.utiles import euros  # noqa: E402

log = logging.getLogger("bot")


def main() -> int:
    ap = argparse.ArgumentParser(description="Bot de ofertas de consolas")
    ap.add_argument("--config", default=str(RAIZ / "config.yaml"))
    ap.add_argument("--env", default=str(RAIZ / ".env"))
    ap.add_argument("--una-vez", action="store_true", help="una pasada (respetando el ritmo de cada fuente) y salir")
    ap.add_argument("--simular", action="store_true", help="una pasada sin enviar ni guardar nada")
    ap.add_argument("--prueba", action="store_true", help="enviar un aviso de prueba")
    ap.add_argument("--chat-id", action="store_true", help="mostrar los chats que han escrito al bot")
    ap.add_argument("--mercado", action="store_true", help="resumen de precios vistos")
    ap.add_argument("--diagnostico", action="store_true",
                    help="comprueba cada plataforma y manda un informe por Telegram")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(message)s", datefmt="%d/%m %H:%M:%S")
    config.cargar_env(args.env)
    cfg = config.cargar(args.config)
    ruta_bd = cfg.ruta_bd if Path(cfg.ruta_bd).is_absolute() else str(RAIZ / cfg.ruta_bd)

    if args.chat_id:
        if not cfg.telegram_token:
            print("Falta TELEGRAM_TOKEN en .env")
            return 1
        chats = avisos.Telegram(cfg.telegram_token, "").chats()
        if not chats:
            print("No veo mensajes. Abre tu bot en Telegram, pulsa Iniciar / escribe algo y repite.")
        for c in chats:
            extra = " · grupo con temas" if c["foro"] else ""
            print(f"{c['id']}   ({c['nombre']}, {c['tipo']}{extra})")
        return 0

    if args.prueba:
        ok = avisos.crear_avisador(cfg).enviar(avisos.Aviso(
            html="✅ <b>Bot de ofertas</b>: los avisos llegan bien.",
            texto="✅ Bot de ofertas: los avisos llegan bien."))
        print("Enviado" if ok else "No se pudo enviar (mira el error de arriba)")
        return 0 if ok else 1

    if args.diagnostico:
        from ofertas import diagnostico
        lineas = diagnostico.ejecutar(cfg, avisos.crear_avisador(cfg))
        return 0 if not any(linea.startswith("❌") for linea in lineas) else 1

    if args.mercado:
        filas = Estado(ruta_bd).resumen_mercado(cfg.dias_mercado)
        if not filas:
            print("Aún no hay datos: deja el bot funcionando un rato.")
        for f in filas:
            print(f"{f['producto']:<16} {f['fuente']:<9} n={f['n']:<4} mín {euros(f['min']):>9}  "
                  f"p25 {euros(f['p25']):>9}  mediana {euros(f['mediana']):>9}  máx {euros(f['max']):>9}")
        return 0

    estado = Estado(":memory:" if args.simular else ruta_bd)
    avisador = avisos.crear_avisador(cfg, solo_consola=args.simular, estado=estado)
    pausa = (1.0, 2.5) if args.una_vez else (2.0, 5.0)    # en GitHub Actions, cuanto más corto mejor
    motor = Motor(cfg, estado, avisador, pausa=(0, 0) if args.simular else pausa)
    log.info("Bot de ofertas %s (HTTP: %s) · productos: %s", __version__, MOTOR,
             ", ".join(p.nombre for p in cfg.productos))
    if MOTOR != "curl_cffi":
        log.warning("curl_cffi no está instalado: Vinted y algunas tiendas bloquean más")

    if args.simular:
        from ofertas import diagnostico
        diagnostico.sonda_plataformas()       # temporal: probar nuevas plataformas
        n = motor.ciclo(forzar=True)
        log.info("Simulación terminada: %d avisos (no se ha enviado nada)", n)
        return 0
    if args.una_vez:
        # respeta el ritmo de cada fuente (y el freno si alguna nos bloquea), con 3 min de margen
        n = motor.ciclo(margen=180)
        log.info("Pasada terminada: %d avisos", n)
        return 0

    def salir(*_):
        log.info("Parando el bot")
        sys.exit(0)

    signal.signal(signal.SIGTERM, salir)
    activas = [f for f in ("wallapop", "vinted", "chollometro", "tiendas")
               if cfg.activa(f) and (f != "tiendas" or cfg.tiendas)]
    avisador.enviar(avisos.Aviso(
        html=f"🤖 Bot arrancado. Vigilo <b>{', '.join(p.nombre for p in cfg.productos)}</b> "
             f"en {', '.join(activas)}.",
        texto=f"🤖 Bot arrancado. Vigilo {', '.join(p.nombre for p in cfg.productos)} en {', '.join(activas)}."))
    try:
        while True:
            motor.ciclo()
            time.sleep(20)
    except KeyboardInterrupt:
        log.info("Parando el bot")
    return 0


if __name__ == "__main__":
    sys.exit(main())
