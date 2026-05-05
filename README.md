# 🤖 Claude Trading Bot — BTC/USDT

Bot de trading automático que usa Claude (IA) para analizar el mercado
y ejecutar órdenes reales en Binance.

---

## ⚡ Instalación en Railway (paso a paso)

### PASO 1 — Crea tu API Key en Binance
1. Ve a binance.com → inicia sesión
2. Arriba a la derecha: tu icono → **Gestión de API**
3. Pulsa **Crear API** → elige "API generada por el sistema"
4. Ponle un nombre: "trading-bot"
5. En permisos, activa solo: ✅ **Lectura** y ✅ **Trading spot**
6. ⚠️ NO actives retiros
7. Guarda la **API Key** y el **Secret Key** (solo se muestran una vez)

### PASO 2 — Consigue tu API Key de Anthropic
1. Ve a console.anthropic.com
2. Inicia sesión o crea cuenta
3. Ve a **API Keys** → **Create Key**
4. Guarda la clave (empieza por `sk-ant-...`)

### PASO 3 — Sube el bot a GitHub
1. Ve a github.com → crea cuenta si no tienes
2. Pulsa **New repository** → nombre: `trading-bot` → público → Create
3. Sube los 3 archivos: `bot.py`, `requirements.txt`, `railway.toml`
   (botón "uploading an existing file" en GitHub)

### PASO 4 — Despliega en Railway
1. Ve a railway.app → **Login with GitHub**
2. Pulsa **New Project** → **Deploy from GitHub repo**
3. Selecciona tu repo `trading-bot`
4. Railway lo detecta automáticamente y empieza a construir

### PASO 5 — Añade tus claves secretas
En Railway, dentro de tu proyecto:
1. Ve a la pestaña **Variables**
2. Añade estas variables una por una:

| Variable | Valor |
|---|---|
| `BINANCE_API_KEY` | tu API key de Binance |
| `BINANCE_API_SECRET` | tu Secret key de Binance |
| `ANTHROPIC_API_KEY` | tu clave de Anthropic |
| `TRADE_AMOUNT_USDT` | cantidad por trade, ej: `50` |
| `INTERVAL_MINUTES` | cada cuántos minutos, ej: `60` |

3. Pulsa **Deploy** — el bot arranca solo

### PASO 6 — Verifica que funciona
- Ve a la pestaña **Logs** en Railway
- Deberías ver algo como:
  ```
  [2026-05-05 10:00:00] 🤖 Bot iniciado | Par: BTCUSDT
  [2026-05-05 10:00:01] Obteniendo datos de mercado...
  [2026-05-05 10:00:02] BTC: $95,420 | RSI: 52.3 | USDT: $50.00
  [2026-05-05 10:00:04] Claude → HOLD (58%) | Mercado lateral, esperar confirmación
  ```

---

## ⚙️ Configuración

| Variable | Por defecto | Descripción |
|---|---|---|
| `TRADE_AMOUNT_USDT` | 50 | Cuántos USDT usar por compra |
| `INTERVAL_MINUTES` | 60 | Frecuencia de análisis |

## 🛡️ Seguridad importante

- El bot **NUNCA pide tus contraseñas**, solo API keys
- La API key de Binance **no permite retirar fondos** (si la configuraste bien)
- Empieza con cantidades pequeñas (50-100 USDT)
- Railway cifra tus variables de entorno

## 🔴 El bot actúa cuando:
- Claude dice **BUY** con ≥65% de confianza → compra `TRADE_AMOUNT_USDT` de BTC
- Claude dice **SELL** con ≥65% de confianza → vende todo el BTC disponible
- Debajo del 65% → no hace nada (HOLD)

## 💰 Costes aproximados
- Railway: **gratis** (plan hobby cubre esto)
- Anthropic API: ~$0.01 por análisis = ~$7/mes con análisis cada hora
- Binance: 0.1% por trade (estándar)
