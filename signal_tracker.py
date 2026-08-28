
import os, sys, requests, ccxt, pandas as pd
from datetime import datetime, timezone
from supabase_store import list_active_signals, update_signal, add_event

TOKEN=os.getenv("TELEGRAM_BOT_TOKEN","").strip()
CHAT=os.getenv("TELEGRAM_CHAT_ID","").strip()

def send(msg):
    if not TOKEN or not CHAT: return
    requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage",
        data={"chat_id":CHAT,"text":msg,"parse_mode":"HTML"},timeout=20).raise_for_status()

def exobj(name):
    return getattr(ccxt,name.lower())({"enableRateLimit":True,"timeout":20000})

def fmt(x):
    x=float(x)
    return f"{x:.2f}" if x>=100 else f"{x:.5f}" if x>=1 else f"{x:.6f}" if x>=0.01 else f"{x:.8f}"

def process(sig):
    ex=exobj(sig["exchange"])
    since=None
    if sig.get("last_checked_at"):
        dt=datetime.fromisoformat(sig["last_checked_at"].replace("Z","+00:00"))
        since=int(dt.timestamp()*1000)-60000
    raw=ex.fetch_ohlcv(sig["symbol"],timeframe="1m",since=since,limit=30)
    df=pd.DataFrame(raw,columns=["timestamp","open","high","low","close","volume"])
    if df.empty:return

    entry=float(sig["entry_price"]); stop=float(sig["stop_price"]); tp1=float(sig["tp1"]); tp2=float(sig["tp2"])
    tp1_hit=bool(sig.get("tp1_hit")); tp2_hit=bool(sig.get("tp2_hit"))
    maxp=max(float(sig.get("max_price") or entry),float(df["high"].max()))
    minp=min(float(sig.get("min_price") or entry),float(df["low"].min()))
    status="ACTIVE"; closed=False
    now=datetime.now(timezone.utc).isoformat()

    for _,c in df.sort_values("timestamp").iterrows():
        hi=float(c["high"]); lo=float(c["low"]); close=float(c["close"])

        if not tp1_hit and hi>=tp1 and lo<=stop:
            status="AMBIGUOUS"; closed=True
            add_event(sig["id"],"AMBIGUOUS",close,"TP1 y STOP en la misma vela.")
            send(f"⚠️ <b>SEÑAL AMBIGUA</b>\n{sig['symbol']} · {sig['exchange']} · #{sig['id']}")
            break

        if not tp1_hit and lo<=stop:
            status="STOP"; closed=True
            add_event(sig["id"],"STOP_HIT",stop)
            send(f"🛑 <b>STOP</b>\n{sig['symbol']} · {sig['exchange']} · #{sig['id']}\nPrecio {fmt(stop)}")
            break

        if not tp1_hit and hi>=tp1:
            tp1_hit=True
            add_event(sig["id"],"TP1_HIT",tp1)
            send(f"🎯 <b>TP1 ALCANZADO</b>\n{sig['symbol']} · {sig['exchange']} · #{sig['id']}\nTP1 {fmt(tp1)}")

        if tp1_hit and not tp2_hit:
            if hi>=tp2:
                tp2_hit=True; status="TP2"; closed=True
                add_event(sig["id"],"TP2_HIT",tp2)
                send(f"🏆 <b>TP2 ALCANZADO</b>\n{sig['symbol']} · {sig['exchange']} · #{sig['id']}\nTP2 {fmt(tp2)}")
                break
            if lo<=entry:
                status="TP1_BE"; closed=True
                add_event(sig["id"],"BREAK_EVEN_AFTER_TP1",entry)
                send(f"🔒 <b>BREAK-EVEN DESPUÉS DE TP1</b>\n{sig['symbol']} · {sig['exchange']} · #{sig['id']}")
                break

    if not closed and sig.get("expires_at"):
        exp=datetime.fromisoformat(sig["expires_at"].replace("Z","+00:00"))
        if datetime.now(timezone.utc)>=exp:
            status="EXPIRED"; closed=True
            last=float(df.iloc[-1]["close"])
            add_event(sig["id"],"EXPIRED",last)
            send(f"⌛ <b>SEÑAL EXPIRADA</b>\n{sig['symbol']} · {sig['exchange']} · #{sig['id']}")

    fields={
        "tp1_hit":tp1_hit,"tp2_hit":tp2_hit,"stop_hit":status=="STOP",
        "max_price":maxp,"min_price":minp,
        "max_return_pct":(maxp/entry-1)*100,
        "max_drawdown_pct":(minp/entry-1)*100,
        "last_checked_at":now
    }
    if tp1_hit and not sig.get("tp1_hit"): fields["tp1_hit_at"]=now
    if tp2_hit and not sig.get("tp2_hit"): fields["tp2_hit_at"]=now
    if status=="STOP": fields["stop_hit_at"]=now
    if closed:
        fields["status"]=status; fields["closed_at"]=now
    update_signal(sig["id"],fields)

def main():
    sigs=list_active_signals()
    print("Señales activas:",len(sigs))
    for s in sigs:
        try: process(s); print("Procesada",s["id"],s["symbol"])
        except Exception as e: print("ERROR",s["id"],repr(e))
    return 0

if __name__=="__main__": sys.exit(main())
