
import os
import sys
from datetime import datetime, timezone
import requests
from scanner import scan_market

ALERT_SCORE = float(os.getenv("ALERT_SCORE", "84"))
PRIORITY_SCORE = float(os.getenv("PRIORITY_SCORE", "90"))
MAX_RSI = float(os.getenv("MAX_RSI", "70"))
MIN_REL_VOLUME = float(os.getenv("MIN_REL_VOLUME", "1.5"))
MIN_RR = float(os.getenv("MIN_RR", "2.0"))

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

def fmt_price(x):
    x = float(x)
    if x >= 100:
        return f"{x:.2f}"
    if x >= 1:
        return f"{x:.5f}"
    if x >= 0.01:
        return f"{x:.6f}"
    return f"{x:.8f}"

def send_telegram(text):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        raise RuntimeError("Faltan TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID")
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    r = requests.post(url, data={
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }, timeout=20)
    r.raise_for_status()

def classify_alert(r):
    if float(r["rsi_15m"]) > MAX_RSI:
        return None
    valid = (
        float(r["score"]) >= ALERT_SCORE
        and float(r["rel_volume_15m"]) >= MIN_REL_VOLUME
        and float(r["rr_tp2"]) >= MIN_RR
    )
    if not valid:
        return None
    return "PRIORITARIA" if float(r["score"]) >= PRIORITY_SCORE else "FUERTE"

def alert_message(r, level):
    cross = "✅ Confirmación KuCoin + MEXC" if bool(r.get("cross_exchange", False)) else "⚠️ Sin confirmación cross-exchange"
    icon = "🚨🚨" if level == "PRIORITARIA" else "🚨"
    return f"""{icon} <b>OPORTUNIDAD {level}</b>

<b>{r['symbol']} · {r['exchange']}</b>
Score: <b>{float(r['score']):.1f}/100</b>

💰 Precio: <b>{fmt_price(r['price'])}</b>
🎯 Entrada: <b>{fmt_price(r['entry_low'])} – {fmt_price(r['entry_high'])}</b>
🛑 Stop: <b>{fmt_price(r['stop'])}</b>
✅ TP1: <b>{fmt_price(r['tp1'])}</b>
✅ TP2: <b>{fmt_price(r['tp2'])}</b>

📊 R/R: {float(r['rr_tp2']):.2f}
📈 RSI 15m: {float(r['rsi_15m']):.1f}
🔥 Volumen relativo: {float(r['rel_volume_15m']):.2f}x
💧 Spread: {float(r['spread_pct']):.3f}%
📅 24h: {float(r['change_24h_pct']):+.2f}%

{cross}

<i>Señal algorítmica experimental. No garantiza rentabilidad.</i>"""

def main():
    print("CRYPTO MONITOR ALERT WORKER", datetime.now(timezone.utc).isoformat())
    df = scan_market()
    if df is None or df.empty:
        print("No se obtuvieron datos.")
        return 0
    df = df[df["best_exchange"] == True].copy().sort_values("score", ascending=False)
    candidates = []
    for _, r in df.iterrows():
        level = classify_alert(r)
        if level:
            candidates.append((r, level))
    if not candidates:
        print("Sin oportunidades que justifiquen alerta.")
        return 0
    for r, level in candidates[:3]:
        send_telegram(alert_message(r, level))
        print(f"Alerta enviada: {r['symbol']} {r['exchange']} score={float(r['score']):.1f}")
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print("ERROR:", repr(exc))
        sys.exit(1)
