# Bot de ofertas de consolas 🎮

Vigila **Wallapop**, **Vinted**, **Chollometro** (chollos de tiendas oficiales: Amazon, MediaMarkt,
PcComponentes, El Corte Inglés, PlayStation Direct, Carrefour, Game, AliExpress…) y, si quieres,
**fichas concretas de tiendas** (precio y stock). Te avisa por **Telegram** y/o **WhatsApp** cuando
aparece una PS5 o una Xbox Series X a buen precio.

**Cómo avisa**

Cada consola que encuentra te llega **en su propio mensaje, con foto y enlace**, de la más barata a la
más cara:

- **🔥 OFERTÓN**: por debajo de **tu máximo** (`config.yaml`), o un **20 % más barata que la mediana**
  de lo que se pide en segunda mano en las últimas 2 semanas (el bot la calcula solo).
- **🏷️ Normal**: el resto, hasta el **tope** de cada consola (lo que cuesta nueva). Te dice cuánto se pasa
  de tu máximo. Si solo quieres ofertones, pon `avisos.todas: false`.
- Si un anuncio del que ya te avisó **baja de precio** otros 10 € o más, te lo vuelve a mandar.
- Si una tienda que vigilas **vuelve a tener stock** (útil para la Xbox Series X, que va escasa).
- Como mucho 25 mensajes por pasada (`avisos.max_por_pasada`); si hay más, siguen en la siguiente.

Descarta mandos, juegos, fundas, cajas vacías, "busco PS5", PS5 Pro, PS Portal, Series S, consolas
averiadas, anuncios reservados y los de fuera de tu radio sin envío. Si algo está sospechosamente barato
(menos de la mitad de la mediana) te lo marca como posible estafa.

---

## Opción A · Gratis en GitHub, sin servidor (recomendada)

GitHub ejecuta el bot cada 10 minutos en sus máquinas. No necesitas tarjeta ni tener nada encendido.

### 1. Crea tu bot de Telegram

1. En Telegram abre **@BotFather** → `/newbot` → ponle nombre y un usuario acabado en `bot`.
   Te da un **token** (tipo `123456789:ABC-...`).
2. Abre tu bot nuevo, pulsa **Iniciar** y escríbele cualquier cosa.
3. En el navegador abre `https://api.telegram.org/bot<TU_TOKEN>/getUpdates` (con tu token).
   Busca `"chat":{"id":` → ese número es tu **chat id**.

### 2. Sube el proyecto a un repositorio nuevo

Crea un repositorio en GitHub (sin README). **Público** = se ejecuta cada 10 min gratis e ilimitado.
**Privado** = tienes 2.000 minutos al mes: edita `.github/workflows/bot.yml` y pon `*/30` en el cron.
Los tokens no se ven aunque sea público (van en *Secrets*, paso 3).

```bash
cd bot-ofertas-consolas
git init -b main
git add .
git commit -m "Bot de ofertas"
git remote add origin https://github.com/TU_USUARIO/bot-ofertas.git
git push -u origin main
```

(Sin git: en el repo, *Add file → Upload files* y arrastra **todo el contenido** de la carpeta,
incluida la carpeta `.github`.)

### 3. Guarda los tokens como secretos

En el repo: **Settings → Secrets and variables → Actions → New repository secret**:

| Nombre | Valor |
|---|---|
| `TELEGRAM_TOKEN` | el token de BotFather |
| `TELEGRAM_CHAT_ID` | tu chat id |
| `CALLMEBOT_TELEFONO` / `CALLMEBOT_APIKEY` | solo si quieres WhatsApp (ver más abajo) |

### 4. Arráncalo

1. Pestaña **Actions** → si lo pide, *I understand my workflows, go ahead and enable them*.
2. **Bot de ofertas → Run workflow → acción `prueba`** → te tiene que llegar un mensaje a Telegram.
3. **Run workflow → `diagnostico`** → te llega por Telegram un informe con lo que ve en cada plataforma
   (anuncios recibidos, válidos y el más barato) o qué plataforma falla.
4. **Muy importante**: GitHub solo lanza las tareas programadas si **la última persona que editó la línea
   `cron`** tiene permiso de escritura en el repo. Si los archivos los subió otra persona o una app,
   abre `.github/workflows/bot.yml` en GitHub (icono del lápiz), cambia `*/10 * * * *` por
   `3-59/10 * * * *` y pulsa **Commit changes**. Así la tarea queda a tu nombre (y además evita el minuto
   :00, cuando GitHub va más saturado).
5. Listo: a partir de ahí se ejecuta solo cada 10 minutos. La primera pasada te manda lo que ya hay
   publicado (hasta 25 mensajes) y luego solo lo nuevo.
   Si en una hora no ves ejecuciones *scheduled* en la pestaña Actions, repasa el paso 4.

Para cambiar precios o productos, edita `config.yaml` en GitHub (icono del lápiz) y guarda: la siguiente
ejecución ya lo usa.

**Lo que tienes que saber de esta opción**

- **Ritmo**: cada 10 minutos como mucho, y GitHub a veces retrasa las ejecuciones programadas unos minutos
  en horas de mucha carga.
- **Vinted** puede bloquear los servidores de GitHub (bloquea mucho las IPs de centros de datos). Si pasa,
  el bot te avisa por Telegram tras varios fallos seguidos; entonces pon `vinted: false` en `config.yaml`.
  Wallapop y Chollometro deberían ir bien.
- **Condiciones de GitHub**: Actions está pensado para tareas de desarrollo de software; usarlo como tarea
  programada de este tipo es una zona gris. Lo peor que suele pasar es que desactiven Actions en ese repo.
- GitHub pausa las tareas programadas de un repo público tras 60 días sin actividad; el
  propio workflow hace un commit de "latido" el día 1 de cada mes para evitarlo.
- La "memoria" del bot (qué ha visto) se guarda en la caché de Actions. Si algún día se pierde, te volverá
  a mandar los anuncios que sigan publicados.

---

## Opción B · Gratis 24/7 en Oracle Cloud (Always Free)

Si quieres que mire cada 5 minutos y sin las limitaciones de GitHub: Oracle da una máquina virtual gratis
para siempre (pide tarjeta para verificar la cuenta, no cobra si te quedas en lo gratuito).

1. Crea la cuenta en Oracle Cloud y una instancia **Always Free** (Ubuntu; vale la `VM.Standard.E2.1.Micro`
   o una Ampere A1 pequeña). Si sale "out of capacity", prueba otro dominio de disponibilidad o más tarde.
2. Entra por SSH, instala Docker y:
   ```bash
   git clone https://github.com/TU_USUARIO/bot-ofertas.git && cd bot-ofertas
   cp .env.example .env && nano .env          # tus tokens
   docker compose up -d --build
   docker compose logs -f
   ```
3. **Importante**: Oracle puede recuperar instancias gratuitas que considera inactivas (CPU muy baja
   durante 7 días), y este bot apenas usa CPU. Para evitarlo, pasa la cuenta a **Pay As You Go**: sigue
   siendo gratis mientras no salgas de los recursos Always Free.

Mismo aviso que con GitHub: Vinted puede bloquear las IPs de centros de datos.

---

## Opción C · En tu propio ordenador

Útil para probar, o si algún día tienes un mini PC o una Raspberry encendidos en casa (la IP de casa es la
que menos bloqueos tiene).

```bash
cd bot-ofertas-consolas
python3 -m venv .venv && source .venv/bin/activate      # en Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                     # pon TELEGRAM_TOKEN en .env
python bot.py --chat-id                                  # te da TELEGRAM_CHAT_ID → pégalo en .env
python bot.py --prueba                                   # debería llegarte un mensaje
python bot.py --simular                                  # una pasada en pantalla, sin enviar nada
python bot.py                                            # funciona sin parar
```

O con Docker: `cp .env.example .env`, rellénalo y `docker compose up -d --build`.

---

## WhatsApp (opcional)

WhatsApp no tiene API gratuita oficial para esto, así que se usa **CallMeBot** (gratis, uso personal,
solo texto y algo más lento que Telegram):

1. Sigue https://www.callmebot.com/blog/free-api-whatsapp-messages/ : añade su número a tus contactos
   y mándale por WhatsApp `I allow callmebot to send me messages`.
2. Te responde con tu **apikey**. Ponla junto a tu teléfono (`+34...`) en los secretos de GitHub
   (`CALLMEBOT_TELEFONO`, `CALLMEBOT_APIKEY`) o en `.env`.

Puedes tener Telegram y WhatsApp a la vez.

---

## Ajustar qué es "buena oferta"

Todo está en `config.yaml`, con comentarios:

| Qué | Dónde | Por defecto |
|---|---|---|
| Máximo PS5 segunda mano / nueva | `productos → PS5` | 420 € / 529 € |
| Máximo Xbox Series X segunda mano / nueva | `productos → Xbox Series X` | 420 € / 699 € |
| Descuento frente a la mediana | `mercado.descuento_minimo` | 20 % |
| Radio en Wallapop (desde Oviedo) | `ubicacion.radio_km` | 120 km (o cualquier distancia con envío) |
| Frecuencia (opción B y C) | `intervalos_min` | Wallapop 5 min, Vinted y Chollometro 10, tiendas 30 |

En la opción A la frecuencia máxima la marca el cron de `.github/workflows/bot.yml`.

Para calibrar los máximos, mira cómo está el mercado tras un día funcionando (opciones B y C):

```bash
python bot.py --mercado
# (salida de ejemplo, no son datos reales)
# PS5    wallapop  n=212  mín 180 €  p25 390 €  mediana 430 €  máx 650 €
```

¿También te vale la **PS5 Pro**? Hay un bloque comentado en `config.yaml`: quita los `#`.
Puedes añadir cualquier otro producto copiando un bloque (nombre, búsquedas, palabras, precios).

### Vigilar fichas de tiendas concretas

En `tiendas:` pega la URL de la ficha del producto (MediaMarkt, El Corte Inglés, Game, Carrefour,
PcComponentes…). El bot lee el precio y el stock de los datos que la tienda publica para Google.
Con `avisar_stock: true` te avisa cuando una consola agotada vuelve a estar disponible.
Amazon bloquea casi siempre este método: para Amazon usa Keepa o CamelCamelCamel.

---

## Cosas a saber

- Wallapop y Vinted **no tienen API pública**: el bot usa la misma que usa su web. Funciona, pero si
  cambian algo puede dejar de ir. Si una fuente falla 6 veces seguidas, **el bot te avisa por Telegram**
  (y otra vez cuando se arregla). Si te bloquean, baja solo el ritmo.
- Úsalo para ti y no subas la frecuencia: consultas moderadas son lo que hace que no te bloqueen.
- Ante una ganga sospechosa: paga siempre **dentro de la plataforma** (Wallapop Envíos / Vinted), nunca
  por Bizum o transferencia, y desconfía de quien quiera sacarte a WhatsApp.
- En Vinted el precio que ves no incluye la protección al comprador; el aviso te muestra el total.

## Tests

```bash
pip install pytest && python -m pytest -q
```
