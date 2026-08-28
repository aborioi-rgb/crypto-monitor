
import os, requests
from datetime import datetime, timezone, timedelta

SUPABASE_URL = os.getenv("SUPABASE_URL","").rstrip("/")
SUPABASE_SECRET_KEY = os.getenv("SUPABASE_SECRET_KEY","").strip()

def headers(prefer=None):
    if not SUPABASE_URL or not SUPABASE_SECRET_KEY:
        raise RuntimeError("Faltan SUPABASE_URL o SUPABASE_SECRET_KEY")
    h={"apikey":SUPABASE_SECRET_KEY,"Authorization":f"Bearer {SUPABASE_SECRET_KEY}","Content-Type":"application/json"}
    if prefer: h["Prefer"]=prefer
    return h

def url(table): return f"{SUPABASE_URL}/rest/v1/{table}"

def get_active_signal(symbol, exchange):
    p={"select":"*","symbol":f"eq.{symbol}","exchange":f"eq.{exchange}","status":"eq.ACTIVE","order":"created_at.desc","limit":"1"}
    r=requests.get(url("signals"),headers=headers(),params=p,timeout=20); r.raise_for_status()
    x=r.json(); return x[0] if x else None

def create_signal(row, expires_hours=12):
    now=datetime.now(timezone.utc)
    payload={
        "symbol":row["symbol"],"exchange":row["exchange"],"score":float(row["score"]),
        "entry_price":float(row["price"]),"entry_low":float(row["entry_low"]),"entry_high":float(row["entry_high"]),
        "stop_price":float(row["stop"]),"tp1":float(row["tp1"]),"tp2":float(row["tp2"]),
        "rsi_15m":float(row["rsi_15m"]),"relative_volume":float(row["rel_volume_15m"]),
        "spread_pct":float(row["spread_pct"]),"cross_confirmed":bool(row.get("cross_exchange",False)),
        "status":"ACTIVE","tp1_hit":False,"tp2_hit":False,"stop_hit":False,
        "max_price":float(row["price"]),"min_price":float(row["price"]),
        "max_return_pct":0.0,"max_drawdown_pct":0.0,
        "last_checked_at":now.isoformat(),"expires_at":(now+timedelta(hours=expires_hours)).isoformat()
    }
    r=requests.post(url("signals"),headers=headers("return=representation"),json=payload,timeout=20); r.raise_for_status()
    return r.json()[0]

def add_event(signal_id,event_type,price=None,notes=None):
    payload={"signal_id":signal_id,"event_type":event_type,"price":float(price) if price is not None else None,"notes":notes}
    r=requests.post(url("signal_events"),headers=headers("return=minimal"),json=payload,timeout=20); r.raise_for_status()

def list_active_signals():
    p={"select":"*","status":"eq.ACTIVE","order":"created_at.asc"}
    r=requests.get(url("signals"),headers=headers(),params=p,timeout=20); r.raise_for_status()
    return r.json()

def update_signal(signal_id,fields):
    r=requests.patch(url("signals"),headers=headers("return=minimal"),params={"id":f"eq.{signal_id}"},json=fields,timeout=20)
    r.raise_for_status()
