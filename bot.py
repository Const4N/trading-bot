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

SYMBOL       = "SOLUSDC"
TRADE_USDC   = float(os.environ.get("TRADE_AMOUNT_USDT", "17"))
INTERVAL_MIN = int(os.environ.get("INTERVAL_MINUTES", "15"))

BINANCE_BASE = "https://api1.binance.com"

# ── Binance helpers ────────────────────────────────────────────
def get_server_time_offset():
    try:
        r = requests.get(BINANCE_BASE + "/api/v3/time", timeout=5)
        return r.json()["serverTime"] - int(time.time() * 1000)
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

def get_open_orders():
    try:
        data = binance_get("/api/v3/openOrders", {"symbol": SYMBOL}, signed=True)
        return data
    except Exception as e:
        log(f"⚠️ No se pudieron obtener órdenes: {e}")
        return []

def place_order(side, usdc_amount=None, sol_amount=None):
    info = binance_get("/api/v3/exchangeInfo", {"symbol": SYMBOL})
    filters = {f["filterType"]: f for f in info["symbols"][0]["filters"]}
    step = float(filters["LOT_SIZE"]["stepSize"])
    min_qty = float(filters["LOT_SIZE"]["minQty"])

    # Soporte para filtros MIN_NOTIONAL y NOTIONAL (Binance usa ambos según el par)
    min_notional = 0.0
    if "MIN_NOTIONAL" in filters:
        min_notional = float(filters["MIN_NOTIONAL"].get("minNotional", 0))
    elif "NOTIONAL" in filters:
        min_notional = float(filters["NOTIONAL"].get("minNotional", 0))

    price, _, _ = get_price()

    if side == "BUY":
        qty = usdc_amount / price
    else:
        qty = sol_amount

    decimals = len(str(step).rstrip("0").split(".")[-1]) if "." in str(step) else 0
    qty = round(qty - (qty % step), decimals)

    # Si después de redondear queda por debajo del mínimo notional, sumar un step
    if min_notional > 0 and qty * price < min_notional:
        qty = round(qty + step, decimals)

    if qty < min_qty:
        log(f"⚠️ Cantidad demasiado pequeña ({qty} SOL).")
        return None

    if min_notional > 0 and qty * price < min_notional:
        log(f"⚠️ Notional insuficiente ({qty * price:.2f} USDC < {min_notional} mínimo).")
        return None

    log(f"Enviando orden {side} {qty} SOL a ~${price:.2f}...")
    order = binance_post("/api/v3/order", {
        "symbol": SYMBOL,
        "side": side,
        "type": "MARKET",
        "quantity": qty,
    })
    log(f"✅ Orden ejecutada: {side} {qty} SOL a ~${price:.2f}")
    return order

# ── Indicadores ────────────────────────────────────────────────
def calc_rsi(closes, period=14):
    if len(closes) < period + 1:
        return None
    gains = losses = 0
    for i in range(len(closes) - period, len(closes)):
        diff = closes[i] - closes[i - 1]
        if diff > 0: gains += diff
        else: losses -= diff
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
def ask_claude(price, change24h, volume24h, rsi, ema9, ema21, closes):
    prompt = f"""Eres un trader experto en criptomonedas. Analiza SOL/USDC y decide.

MERCADO:
- Precio SOL: ${price:.2f}
- Cambio 24h: {change24h:.2f}%
- Volumen 24h: ${volume24h/1e6:.1f}M
- RSI(14): {f'{rsi:.1f}' if rsi else 'N/A'}
- EMA9: ${f'{ema9:.2f}' if ema9 else 'N/A'}
- EMA21: ${f'{ema21:.2f}' if ema21 else 'N/A'}
- Últimos 5 cierres: {[f'${c:.2f}' for c in closes[-5:]]}

Responde SOLO con JSON sin markdown:
{{"signal":"BUY|SELL|HOLD","confidence":0-100,"reasoning":"máx 100 chars en español"}}"""

    headers = {
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    body = {
        "model": "claude-sonnet-4-6",
        "max_tokens": 200,
        "messages": [{"role": "user", "content": prompt}],
    }
    r = requests.post("https://api.anthropic.com/v1/messages", json=body, headers=headers, timeout=30)
    r.raise_for_status()
    import json
    text = r.json()["content"][0]["text"].strip()
    return json.loads(text)

# ── Estado local ───────────────────────────────────────────────
state = {"holding_sol": False, "sol_amount": 0.0}

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

    log(f"SOL: ${price:.2f} | RSI: {f'{rsi:.1f}' if rsi else '—'} | Holding SOL: {state['holding_sol']}")
    log("Consultando a Claude...")

    result     = ask_claude(price, change24h, volume24h, rsi, ema9, ema21, closes)
    signal     = result["signal"]
    confidence = result["confidence"]
    reason     = result["reasoning"]

    log(f"Claude → {signal} ({confidence}%) | {reason}")

    if signal == "BUY" and confidence >= 65 and not state["holding_sol"]:
        log(f"Ejecutando COMPRA de ${TRADE_USDC} USDC en SOL...")
        order = place_order("BUY", usdc_amount=TRADE_USDC)
        if order:
            sol_qty = float(order.get("executedQty", TRADE_USDC / price))
            state["holding_sol"] = True
            state["sol_amount"] = sol_qty
            log(f"✅ Compramos {sol_qty:.4f} SOL")

    elif signal == "SELL" and confidence >= 65 and state["holding_sol"]:
        log(f"Ejecutando VENTA de {state['sol_amount']:.4f} SOL...")
        order = place_order("SELL", sol_amount=state["sol_amount"])
        if order:
            state["holding_sol"] = False
            state["sol_amount"] = 0.0
            log(f"✅ SOL vendido")

    else:
        log(f"Sin acción (HOLD o confianza baja)")

def main():
    log(f"🤖 Bot iniciado | Par: SOLUSDC | Intervalo: {INTERVAL_MIN} min | Trade: ${TRADE_USDC}")
    while True:
        try:
            run_cycle()
        except Exception as e:
            log(f"❌ Error: {e}")
        log(f"Esperando {INTERVAL_MIN} minutos...")
        time.sleep(INTERVAL_MIN * 60)

if __name__ == "__main__":
    main()
