
import ccxt
import numpy as np
import pandas as pd
from datetime import datetime, timezone

EXCHANGES = ["kucoin", "mexc"]
QUOTE = "USDT"

# Primera pasada rápida: universo amplio
PRESELECT_PER_EXCHANGE = 60
MIN_QUOTE_VOLUME = 750_000

# Segunda pasada: análisis técnico completo
TIMEFRAMES = ["15m", "1h"]
CANDLE_LIMIT = 220

# Estados
WATCH_SCORE = 65
ALERT_SCORE = 84
PRIORITY_SCORE = 90

MIN_REL_VOLUME_ALERT = 1.50
MAX_RSI_ALERT = 70.0
MIN_RR_ALERT = 2.0

ATR_STOP_MULT = 1.5
TP1_R = 1.5
TP2_R = 2.5

EXCLUDED_BASES = {
    "USDC", "FDUSD", "TUSD", "DAI", "USDP", "PYUSD", "EUR", "EURC",
    "USD1", "USDE", "USDD", "USTC"
}


def ema(s, n):
    return s.ewm(span=n, adjust=False).mean()


def rsi(s, n=14):
    delta = s.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1/n, adjust=False, min_periods=n).mean()
    avg_loss = loss.ewm(alpha=1/n, adjust=False, min_periods=n).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    out = 100 - (100 / (1 + rs))
    return out.fillna(50)


def atr(df, n=14):
    prev_close = df["close"].shift(1)
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - prev_close).abs(),
        (df["low"] - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1/n, adjust=False, min_periods=n).mean()


def add_indicators(df):
    df = df.copy()
    df["ema9"] = ema(df["close"], 9)
    df["ema21"] = ema(df["close"], 21)
    df["ema50"] = ema(df["close"], 50)
    df["ema200"] = ema(df["close"], 200)

    df["rsi14"] = rsi(df["close"], 14)
    df["atr14"] = atr(df, 14)

    df["vol_ma20"] = df["volume"].rolling(20).mean()
    df["rel_volume"] = df["volume"] / df["vol_ma20"].replace(0, np.nan)

    df["prev_high20"] = df["high"].shift(1).rolling(20).max()
    df["roc_5"] = df["close"].pct_change(5) * 100

    typical = (df["high"] + df["low"] + df["close"]) / 3
    pv = typical * df["volume"]
    df["vwap20"] = pv.rolling(20).sum() / df["volume"].rolling(20).sum().replace(0, np.nan)

    df["dist_ema9_pct"] = (df["close"] / df["ema9"] - 1) * 100
    df["dist_vwap_pct"] = (df["close"] / df["vwap20"] - 1) * 100

    return df


def make_exchange(exchange_id):
    cls = getattr(ccxt, exchange_id)
    return cls({"enableRateLimit": True, "timeout": 20000})


def fast_preselect(ex):
    markets = ex.load_markets()
    tickers = ex.fetch_tickers()

    rows = []

    for symbol, market in markets.items():
        try:
            if market.get("spot") is not True:
                continue
            if market.get("active") is False:
                continue
            if market.get("quote") != QUOTE:
                continue

            base = market.get("base", "")
            if base in EXCLUDED_BASES:
                continue

            ticker = tickers.get(symbol, {})
            last = ticker.get("last")
            qv = ticker.get("quoteVolume")
            pct = ticker.get("percentage")
            bid = ticker.get("bid")
            ask = ticker.get("ask")

            if qv is None:
                bv = ticker.get("baseVolume")
                if bv is not None and last is not None:
                    qv = bv * last

            if not last or not qv:
                continue

            qv = float(qv)
            if qv < MIN_QUOTE_VOLUME:
                continue

            spread = np.nan
            if bid and ask and float(bid) > 0:
                spread = (float(ask) - float(bid)) / float(bid) * 100

            pct = float(pct) if pct is not None else 0.0

            # Score rápido: favorece volumen + movimiento razonable + bajo spread
            vol_score = min(40, max(0, np.log10(max(qv, 1)) - 5) * 10)
            move_score = min(35, abs(pct) * 2.5)
            spread_penalty = 0
            if np.isfinite(spread):
                if spread > 0.50:
                    spread_penalty = 20
                elif spread > 0.25:
                    spread_penalty = 10
                elif spread > 0.12:
                    spread_penalty = 5

            fast_score = vol_score + move_score - spread_penalty

            rows.append({
                "symbol": symbol,
                "base": base,
                "last": float(last),
                "quote_volume": qv,
                "spread_pct": spread,
                "change_24h_pct": pct,
                "fast_score": fast_score,
            })
        except Exception:
            continue

    if not rows:
        return pd.DataFrame()

    return (
        pd.DataFrame(rows)
        .sort_values(["fast_score", "quote_volume"], ascending=[False, False])
        .head(PRESELECT_PER_EXCHANGE)
        .reset_index(drop=True)
    )


def fetch_ohlcv_df(ex, symbol, timeframe):
    raw = ex.fetch_ohlcv(symbol, timeframe=timeframe, limit=CANDLE_LIMIT)
    df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
    return add_indicators(df)


def score_timeframe(df):
    x = df.iloc[-1]
    prev = df.iloc[-2]

    score = 0
    reasons = []
    warnings = []

    if x["ema9"] > x["ema21"] > x["ema50"]:
        score += 22
        reasons.append("Tendencia EMA alcista")
    elif x["ema9"] > x["ema21"]:
        score += 11
        reasons.append("EMA9 > EMA21")

    if pd.notna(x["ema200"]) and x["close"] > x["ema200"]:
        score += 8
        reasons.append("Precio > EMA200")

    r = float(x["rsi14"])
    if 52 <= r <= 64:
        score += 18
        reasons.append(f"RSI ideal {r:.1f}")
    elif 64 < r <= 68:
        score += 12
        reasons.append(f"RSI fuerte {r:.1f}")
    elif 68 < r <= 72:
        score += 3
        warnings.append(f"RSI elevado {r:.1f}")
    elif r > 72:
        score -= 14
        warnings.append(f"RSI demasiado alto {r:.1f}")
    elif 45 <= r < 52:
        score += 7

    rv = float(x["rel_volume"]) if pd.notna(x["rel_volume"]) else 0.0
    if rv >= 2:
        score += 22
        reasons.append(f"Volumen {rv:.1f}x")
    elif rv >= 1.5:
        score += 16
        reasons.append(f"Volumen {rv:.1f}x")
    elif rv >= 1.2:
        score += 8
    elif rv < 0.65:
        score -= 5

    if pd.notna(x["prev_high20"]) and x["close"] > x["prev_high20"]:
        score += 18
        reasons.append("Breakout 20 velas")
    elif pd.notna(prev["prev_high20"]) and prev["close"] > prev["prev_high20"]:
        score += 9
        reasons.append("Breakout reciente")

    roc = float(x["roc_5"]) if pd.notna(x["roc_5"]) else 0.0
    if 0.3 <= roc <= 3.5:
        score += 10
        reasons.append(f"Momentum {roc:.2f}%")
    elif 3.5 < roc <= 5.5:
        score += 4
        warnings.append(f"Momentum extendido {roc:.2f}%")
    elif roc > 5.5:
        score -= 10
        warnings.append(f"Muy extendido {roc:.2f}%")

    if pd.notna(x["vwap20"]) and x["close"] > x["vwap20"]:
        score += 8
        reasons.append("Precio > VWAP")
    else:
        score -= 5

    d9 = float(x["dist_ema9_pct"]) if pd.notna(x["dist_ema9_pct"]) else 0.0
    dvwap = float(x["dist_vwap_pct"]) if pd.notna(x["dist_vwap_pct"]) else 0.0

    if d9 > 3:
        score -= 10
        warnings.append("Muy lejos de EMA9")
    elif d9 > 2:
        score -= 5

    if dvwap > 5:
        score -= 8
        warnings.append("Muy lejos de VWAP")
    elif dvwap > 3:
        score -= 4

    return {
        "score": score,
        "reasons": reasons,
        "warnings": warnings,
        "close": float(x["close"]),
        "atr": float(x["atr14"]) if pd.notna(x["atr14"]) else np.nan,
        "rsi": r,
        "rel_volume": rv,
        "dist_ema9_pct": d9,
        "dist_vwap_pct": dvwap,
    }


def classify_state(score, rsi15, rv15, rr, d9, dvwap):
    too_extended = (rsi15 > MAX_RSI_ALERT or d9 > 2.5 or dvwap > 4.0)

    if score >= ALERT_SCORE and not too_extended and rv15 >= MIN_REL_VOLUME_ALERT and rr >= MIN_RR_ALERT:
        return "ENTRAR AHORA"

    if score >= ALERT_SCORE and too_extended:
        return "ESPERAR PULLBACK"

    if score >= WATCH_SCORE:
        return "CERCA"

    return "SIN SEÑAL"


def analyze_symbol(ex, exchange_name, row):
    tf = {}

    for timeframe in TIMEFRAMES:
        df = fetch_ohlcv_df(ex, row["symbol"], timeframe)
        if len(df) < 60:
            return None
        tf[timeframe] = score_timeframe(df)

    score = 0.65 * tf["15m"]["score"] + 0.35 * tf["1h"]["score"]

    spread = row["spread_pct"]
    if pd.notna(spread):
        if spread > 0.50:
            score -= 20
        elif spread > 0.25:
            score -= 10
        elif spread > 0.12:
            score -= 4

    score = max(0, min(100, score))

    price = tf["15m"]["close"]
    atr15 = tf["15m"]["atr"]
    if not np.isfinite(atr15) or atr15 <= 0:
        return None

    stop = price - ATR_STOP_MULT * atr15
    risk = price - stop
    tp1 = price + TP1_R * risk
    tp2 = price + TP2_R * risk
    rr = (tp2 - price) / risk if risk > 0 else np.nan

    rsi15 = tf["15m"]["rsi"]
    rv15 = tf["15m"]["rel_volume"]
    d9 = tf["15m"]["dist_ema9_pct"]
    dvwap = tf["15m"]["dist_vwap_pct"]

    state = classify_state(score, rsi15, rv15, rr, d9, dvwap)

    return {
        "exchange": exchange_name.upper(),
        "symbol": row["symbol"],
        "base": row["base"],
        "score": round(score, 1),
        "state": state,
        "price": price,
        "entry_low": price - 0.35 * atr15,
        "entry_high": price + 0.10 * atr15,
        "stop": stop,
        "tp1": tp1,
        "tp2": tp2,
        "rr_tp2": rr,
        "risk_pct": (risk / price) * 100,
        "spread_pct": spread,
        "volume_24h": row["quote_volume"],
        "change_24h_pct": row["change_24h_pct"],
        "rsi_15m": rsi15,
        "rel_volume_15m": rv15,
        "cross_exchange": False,
        "best_exchange": False,
        "reasons": tf["15m"]["reasons"] + tf["1h"]["reasons"],
        "warnings": tf["15m"]["warnings"] + tf["1h"]["warnings"],
    }


def scan_market():
    results = []

    for exchange_id in EXCHANGES:
        ex = make_exchange(exchange_id)
        try:
            candidates = fast_preselect(ex)
        except Exception:
            continue

        for _, row in candidates.iterrows():
            try:
                r = analyze_symbol(ex, exchange_id, row)
                if r:
                    results.append(r)
            except Exception:
                continue

    by_base = {}
    for r in results:
        by_base.setdefault(r["base"], []).append(r)

    for base, group in by_base.items():
        strong = [x for x in group if x["score"] >= WATCH_SCORE]
        if len({x["exchange"] for x in strong}) >= 2:
            for r in group:
                if r["score"] >= WATCH_SCORE:
                    r["cross_exchange"] = True
                    r["score"] = min(100, round(r["score"] + 5, 1))

        def key(x):
            spread = x["spread_pct"]
            spread_component = -spread if pd.notna(spread) else -999
            return (x["score"], spread_component, x["volume_24h"])

        best = max(group, key=key)
        best["best_exchange"] = True

    df = pd.DataFrame(results)
    if not df.empty:
        df["scan_time_utc"] = datetime.now(timezone.utc).isoformat()
    return df
