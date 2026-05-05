import os
import time
import hmac
import hashlib
import requests
from datetime import datetime

# ── Configuración ──────────────────────────────────────────────
BINANCE_API_KEY    = os.environ["BINANCE_API_KEY"]
BINANCE_API_SECRET = os.environ["BINANCE_API_SECRET"]
ANTHROPIC_API_KEY  = os.environ["ANTHROPIC_API_KEY"]

SYMBOL       = "BTCUSDT"
TRADE_USDT   = float(os.environ.get("TRADE_AMOUNT_USDT", "50"))
INTERVAL_MIN = int(os.environ.get("INTERVAL_MINUTES", "60"))

BINANCE_BASE = "https://api1.binance.com"

# ── Binance helpers ────────────────────────────────────────────
def get_server_time_offset():
    try:
        r = requests.get(BINANCE_BASE + "/api/v3/time", timeout=5)
        server_time = r.json()["serverTime"]
        return server_time - int(time.time() * 1000)
    except:
        return 0

def sign(params: dict) -> str:
    query = "&".join(f"{k}={v}" for k, v in params.items())
    return hmac.new(BINANCE_API_SECRET.encode(), query.encode(), hashlib.sha256).hexdigest()

def binance_get(path, params=None, signed=False):
    params = params or {}
    if signed:
        offset = get_server_time_offset()
        params["timestamp"] = int(time.time() * 1000) + offset
        params["recvWindow"] = 10000
        params["signature"] = sign(params)
    headers = {"X-MBX-APIKEY": BINANCE_API_KEY}
    r = requests.get(BINANCE_BASE + path, params=params, headers=headers, timeout=10)
    r.raise_for_status()
    return r.json()

def binance_post(path, params):
    offset = get_server_time_offset()
    params["timestamp"] = int(time.time() * 1000) + offset
    params["recvWindow"] = 10000
    params["signature"] = sign(params)
    headers = {"X-MBX-APIKEY": BINANCE_API_KEY}
    r = requests.post(BINANCE_BASE + path, params=params, headers=headers, timeout=10)
    r.raise_for_status()
    return r.json()

def get_price():
    data = binance_get("/api/v3/ticker/24hr", {"symbol": SYMBOL})
    return float(data["lastPrice"]), float(data["priceChangePercent"]), float(data["quoteVolume"])

def get_klines(limit=50):
    data = binance_get("/api/v3/klines", {"symbol": SYMBOL, "interval": "1h", "limit": limit})
    return [float(k[4]) for k in data]

def get_balances():
    data = binance_get("/api/v3/account", signed=True)
    balances = {b["asset"]: float(b["free"]) for b in data["balances"]}
    return balances.get("USDT", 0.0), balances.get("BTC", 0.0)

def place_order(side, usdt_amount=None, btc_amount=None):
    info = binance_get("/api/v3/exchangeInfo", {"symbol": SYMBOL})
    filters = {f["filterType"]: f for f in info["symbols"][0]["filters"]}
    step = float(filters["LOT_SIZE"]["stepSize"])
    min_qty = float(filters["LOT_SIZE"]["minQty"])
    min_notional = float(filters.get("MIN_NOTIONAL", {}).get("minNotional", 10))

    price, _, _ = get_price()

    if side == "BUY":
        qty = usdt_amount / price
    else:
        qty = btc_amount

    decimals = len(str(step).rstrip("0").split(".")[-1])
    qty = round(qty - (qty % step), decimals)

    if qty < min_qty or qty * price < min_notional:
        log(f"⚠️  Cantidad demasiado pequeña ({qty} BTC). Aumenta TRADE_AMOUNT_USDT.")
        return None

    order = binance_post("/api/v3/order", {
        "symbol": SYMBOL,
        "side": side,
        "type": "MARKET",
        "quantity": qty,
    })
    log(f"✅ Orden ejecutada: {side} {qty} BTC a ~${price:.0f}")
    return order

# ── Indicadores ────────────────────────────────────────────────
def calc_rsi(closes, period=14):
    if len(closes) < period + 1:
        return None
    gains = losses = 0
    for i in range(len(closes) - period, len(closes)):
        diff = closes[i] - closes[i - 1]
        if diff > 0:
            gains += diff
        else:
            losses -= diff
    rs = (gains / period) / (losses / period + 1e-9)
    return 100 - 100 / (1 + rs)

def calc_ema(closes, period):
    if len(closes) < period:
        return None
    k = 2 / (period + 1)
    ema = sum(closes[:period]) / period
    for c in closes[period:]:
        ema = c * k + ema * (1 - k)
    return ema

# ── Claude ─────────────────────────────────────────────────────
def ask_claude(price, change24h, volume24h, rsi, ema9, ema21, closes, usdt_balance, btc_balance):
    prompt = f"""Eres un trader experto en criptomonedas. Analiza BTC/USDT y decide.

MERCADO:
- Precio: ${price:.2f}
- Cambio 24h: {change24h:.2f}%
- Volumen 24h: ${volume24h/1e6:.1f}M
- RSI(14): {f'{rsi:.1f}' if rsi else 'N/A'}
- EMA9: ${f'{ema9:.2f}' if ema9 else 'N/A'}
- EMA21: ${f'{ema21:.2f}' if ema21 else 'N/A'}
- Últimos 5 cierres: {[f'${c:.0f}' for c in closes[-5:]]}

CARTERA:
- USDT libre: ${usdt_balance:.2f}
- BTC libre: {btc_balance:.6f}

Responde SOLO con JSON, sin markdown:
{{"signal":"BUY|SELL|HOLD","confidence":0-100,"reasoning":"máx 100 chars en español"}}"""

    headers = {
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    body = {
        "model": "claude-sonnet-4-20250514",
        "max_tokens": 200,
        "messages": [{"role": "user", "content": prompt}],
    }
    r = requests.post("https://api.anthropic.com/v1/messages", json=body, headers=headers, timeout=30)
    r.raise_for_status()
    import json
    text = r.json()["content"][0]["text"].strip()
    return json.loads(text)

# ── Log ────────────────────────────────────────────────────────
def log(msg):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)

# ── Ciclo principal ────────────────────────────────────────────
def run_cycle():
    log("─" * 50)
    log("Obteniendo datos de mercado...")

    closes = get_klines()
    price, change24h, volume24h = get_price()
    rsi   = calc_rsi(closes)
    ema9  = calc_ema(closes, 9)
    ema21 = calc_ema(closes, 21)
    usdt_bal, btc_bal = get_balances()

    log(f"BTC: ${price:.2f} | RSI: {f'{rsi:.1f}' if rsi else '—'} | USDT: ${usdt_bal:.2f} | BTC: {btc_bal:.6f}")
    log("Consultando a Claude...")

    result     = ask_claude(price, change24h, volume24h, rsi, ema9, ema21, closes, usdt_bal, btc_bal)
    signal     = result["signal"]
    confidence = result["confidence"]
    reason     = result["reasoning"]

    log(f"Claude → {signal} ({confidence}%) | {reason}")

    if signal == "BUY" and confidence >= 65:
        if usdt_bal >= TRADE_USDT:
            log(f"Ejecutando COMPRA de ${TRADE_USDT} en BTC...")
            place_order("BUY", usdt_amount=TRADE_USDT)
        else:
            log(f"⚠️  Saldo insuficiente (${usdt_bal:.2f} USDT disponibles, necesitas ${TRADE_USDT})")
    elif signal == "SELL" and confidence >= 65:
        if btc_bal > 0.00001:
            log(f"Ejecutando VENTA de {btc_bal:.6f} BTC...")
            place_order("SELL", btc_amount=btc_bal)
        else:
            log("⚠️  Sin BTC que vender")
    else:
        log("Sin acción (HOLD o confianza baja)")

def main():
    log(f"🤖 Bot iniciado | Par: BTCUSDT | Intervalo: {INTERVAL_MIN} min | Trade: ${TRADE_USDT}")
    while True:
        try:
            run_cycle()
        except Exception as e:
            log(f"❌ Error: {e}")
        log(f"Esperando {INTERVAL_MIN} minutos...")
        time.sleep(INTERVAL_MIN * 60)

if __name__ == "__main__":
    main()
