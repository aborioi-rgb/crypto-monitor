
import os, sys, requests
from datetime import datetime, timezone
from scanner import scan_market
from supabase_store import get_active_signal, create_signal, add_event

ALERT_SCORE=float(os.getenv("ALERT_SCORE","84"))
PRIORITY_SCORE=float(os.getenv("PRIORITY_SCORE","90"))
MAX_RSI=float(os.getenv("MAX_RSI","70"))
MIN_REL_VOLUME=float(os.getenv("MIN_REL_VOLUME","1.5"))
MIN_RR=float(os.getenv("MIN_RR","2.0"))
EXPIRY=int(os.getenv("SIGNAL_EXPIRY_HOURS","12"))
TOKEN=os.getenv("TELEGRAM_BOT_TOKEN","").strip()
CHAT=os.getenv("TELEGRAM_CHAT_ID","").strip()

def send(msg):
    if not TOKEN or not CHAT: raise RuntimeError("Faltan secrets de Telegram")
    r=requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage",
        data={"chat_id":CHAT,"text":msg,"parse_mode":"HTML"},timeout=20); r.raise_for_status()

def fmt(x):
    x=float(x)
    return f"{x:.2f}" if x>=100 else f"{x:.5f}" if x>=1 else f"{x:.6f}" if x>=0.01 else f"{x:.8f}"

def valid(r):
    if float(r["rsi_15m"])>MAX_RSI: return None
    if float(r["score"])<ALERT_SCORE: return None
    if float(r["rel_volume_15m"])<MIN_REL_VOLUME: return None
    if float(r["rr_tp2"])<MIN_RR: return None
    return "PRIORITARIA" if float(r["score"])>=PRIORITY_SCORE else "FUERTE"

def message(r,level,sid):
    cross="✅ Confirmación KuCoin + MEXC" if bool(r.get("cross_exchange",False)) else "⚠️ Sin confirmación cross-exchange"
    return f"""🚨 <b>OPORTUNIDAD {level}</b>

<b>{r['symbol']} · {r['exchange']}</b>
Score: <b>{float(r['score']):.1f}/100</b>
Señal #{sid}

💰 Precio: {fmt(r['price'])}
🎯 Entrada: {fmt(r['entry_low'])} – {fmt(r['entry_high'])}
🛑 Stop: {fmt(r['stop'])}
✅ TP1: {fmt(r['tp1'])}
✅ TP2: {fmt(r['tp2'])}

RSI: {float(r['rsi_15m']):.1f}
Volumen: {float(r['rel_volume_15m']):.2f}x
R/R: {float(r['rr_tp2']):.2f}

{cross}"""

def main():
    print("ALERT WORKER",datetime.now(timezone.utc).isoformat())
    df=scan_market()
    if df is None or df.empty: return 0
    df=df[df["best_exchange"]==True].sort_values("score",ascending=False)
    made=0
    for _,r in df.iterrows():
        level=valid(r)
        if not level: continue
        old=get_active_signal(r["symbol"],r["exchange"])
        if old:
            print("Duplicado evitado",r["symbol"],old["id"]); continue
        sig=create_signal(r,EXPIRY)
        add_event(sig["id"],"SIGNAL_CREATED",r["price"],f"Score {float(r['score']):.1f}")
        send(message(r,level,sig["id"]))
        print("Señal creada",sig["id"],r["symbol"])
        made+=1
        if made>=3: break
    if made==0: print("Sin nuevas oportunidades.")
    return 0

if __name__=="__main__":
    sys.exit(main())
