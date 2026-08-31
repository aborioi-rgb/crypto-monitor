
import json
import os
from pathlib import Path
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import streamlit as st
from streamlit_autorefresh import st_autorefresh

from scanner import scan_market
from supabase_store import list_signals, list_signal_events

st.set_page_config(
    page_title="Crypto Monitor",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

CONFIG_FILE = Path("user_config.json")
HISTORY_FILE = Path("score_history.csv")

DEFAULTS = {
    "min_score": 50,
    "watch_score": 65,
    "alert_score": 84,
    "priority_score": 90,
    "max_rsi": 70.0,
    "min_rel_volume": 1.50,
    "min_rr": 2.0,
    "refresh_minutes": 3,
    "only_best": True,
    "only_cross": False,
}

def load_config():
    if CONFIG_FILE.exists():
        try:
            x = DEFAULTS.copy()
            x.update(json.loads(CONFIG_FILE.read_text(encoding="utf-8")))
            return x
        except Exception:
            pass
    return DEFAULTS.copy()

def save_config(x):
    CONFIG_FILE.write_text(json.dumps(x, indent=2), encoding="utf-8")

cfg = load_config()

st.markdown("""
<style>
.stApp {background:#07111d;}
.block-container {padding-top:1rem; max-width:1650px;}
section[data-testid="stSidebar"] {background:#071827; border-right:1px solid #183044;}
h1,h2,h3 {letter-spacing:-.02em;}
div[data-testid="stMetric"] {
 background:linear-gradient(180deg,#0b1825,#09131e);
 border:1px solid #203244; border-radius:12px; padding:12px 14px;
}
.fin-card {
 background:linear-gradient(180deg,#0b1825,#09131e);
 border:1px solid #203244; border-radius:14px; padding:16px 18px; margin-bottom:12px;
}
.market-good {border-left:4px solid #38d66b;}
.market-watch {border-left:4px solid #f4c430;}
.market-cold {border-left:4px solid #8796a8;}
.small {opacity:.72;font-size:.86rem}
.kicker {opacity:.62;font-size:.72rem;text-transform:uppercase;letter-spacing:.08em}
.profit {color:#55e77c;font-weight:700;}
.loss {color:#ff6767;font-weight:700;}
.neutral {color:#b9c5d2;}
</style>
""", unsafe_allow_html=True)

with st.sidebar:
    st.markdown("## 📈 CRYPTO MONITOR")
    st.caption("SCANNER + SIGNAL TRACKER")
    page = st.radio(
        "Navegación",
        [
            "Dashboard",
            "Oportunidades",
            "Señales activas",
            "Historial y performance",
            "Radar de mercado",
            "Evolución de scores",
            "Alertas",
            "Configuración",
        ],
        label_visibility="collapsed",
    )
    st.divider()
    st.caption("SISTEMA")
    st.success("● Sistema activo")
    st.write("KuCoin + MEXC")
    st.caption("Spot USDT · GitHub Actions + Supabase")

st_autorefresh(interval=int(cfg["refresh_minutes"] * 60_000), key="auto_refresh")

@st.cache_data(ttl=max(50, int(cfg["refresh_minutes"] * 60) - 10), show_spinner=False)
def get_market():
    return scan_market()

@st.cache_data(ttl=55, show_spinner=False)
def get_signal_data():
    try:
        signals = pd.DataFrame(list_signals(500))
        events = pd.DataFrame(list_signal_events(1000))
        return signals, events, None
    except Exception as exc:
        return pd.DataFrame(), pd.DataFrame(), str(exc)

def append_history(df):
    if df.empty:
        return
    h = df[df["best_exchange"]][
        ["base","exchange","score","state","price","rsi_15m","rel_volume_15m"]
    ].copy()
    h["timestamp"] = datetime.now(timezone.utc).isoformat()
    h.to_csv(HISTORY_FILE, mode="a", header=not HISTORY_FILE.exists(), index=False)

def load_history():
    if not HISTORY_FILE.exists():
        return pd.DataFrame()
    try:
        h = pd.read_csv(HISTORY_FILE)
        h["timestamp"] = pd.to_datetime(h["timestamp"], utc=True)
        cutoff = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=7)
        return h[h["timestamp"] >= cutoff].copy()
    except Exception:
        return pd.DataFrame()

def state_cfg(r):
    extended = r["rsi_15m"] > cfg["max_rsi"]
    if (
        r["score"] >= cfg["alert_score"]
        and not extended
        and r["rel_volume_15m"] >= cfg["min_rel_volume"]
        and r["rr_tp2"] >= cfg["min_rr"]
    ):
        return "ENTRAR AHORA"
    if r["score"] >= cfg["alert_score"] and extended:
        return "ESPERAR PULLBACK"
    if r["score"] >= cfg["watch_score"]:
        return "CERCA"
    return "SIN SEÑAL"

def parse_signals(signals):
    if signals.empty:
        return signals
    x = signals.copy()
    for col in ["created_at","closed_at","expires_at","tp1_hit_at","tp2_hit_at","stop_hit_at"]:
        if col in x.columns:
            x[col] = pd.to_datetime(x[col], utc=True, errors="coerce")
    numeric = [
        "score","entry_price","entry_low","entry_high","stop_price","tp1","tp2",
        "rsi_15m","relative_volume","spread_pct","max_return_pct","max_drawdown_pct"
    ]
    for col in numeric:
        if col in x.columns:
            x[col] = pd.to_numeric(x[col], errors="coerce")
    return x

def performance_metrics(signals):
    if signals.empty:
        return {
            "total":0,"active":0,"closed":0,"tp1":0,"tp2":0,"stops":0,
            "partial":0,"profitable":0,"resolved":0,"win_rate":0.0,
            "r_total":0.0,"profit_factor":None
        }

    s = signals.copy()
    status = s["status"].fillna("")
    active = int((status == "ACTIVE").sum())
    closed = int((status != "ACTIVE").sum())
    tp1 = int(s.get("tp1_hit", pd.Series(False, index=s.index)).fillna(False).astype(bool).sum())
    tp2 = int((status == "TP2").sum())
    partial = int((status == "TP1_BE").sum())
    stops = int((status == "STOP").sum())

    # Ganancia confirmada según la gestión simulada definida:
    # TP2 = +2R; TP1_BE = +0.75R.
    profitable = tp2 + partial
    resolved = profitable + stops
    win_rate = (profitable / resolved * 100) if resolved else 0.0

    r_total = tp2 * 2.0 + partial * 0.75 - stops * 1.0
    gross_profit = tp2 * 2.0 + partial * 0.75
    gross_loss = stops * 1.0
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else (None if gross_profit == 0 else np.inf)

    return {
        "total":len(s),"active":active,"closed":closed,"tp1":tp1,"tp2":tp2,
        "stops":stops,"partial":partial,"profitable":profitable,
        "resolved":resolved,"win_rate":win_rate,"r_total":r_total,
        "profit_factor":profit_factor
    }

def status_label(s):
    return {
        "ACTIVE":"🟦 ACTIVA",
        "TP2":"🏆 TP2",
        "TP1_BE":"✅ TP1 + BE",
        "STOP":"🛑 STOP",
        "EXPIRED":"⌛ EXPIRADA",
        "AMBIGUOUS":"⚠️ AMBIGUA",
    }.get(str(s), str(s))

def signal_table(data, height=430):
    if data.empty:
        st.info("Todavía no hay señales registradas.")
        return
    x = data.copy()
    x["Estado"] = x["status"].map(status_label)
    x["Fecha"] = x["created_at"].dt.strftime("%d/%m %H:%M") if "created_at" in x else ""
    x["TP1?"] = x["tp1_hit"].fillna(False).map({True:"✅",False:"—"})
    x["TP2?"] = x["tp2_hit"].fillna(False).map({True:"✅",False:"—"})
    x["Cross"] = x["cross_confirmed"].fillna(False).map({True:"✅",False:"—"})
    cols = [
        "id","Fecha","Estado","symbol","exchange","score","entry_price",
        "tp1","tp2","stop_price","TP1?","TP2?","max_return_pct",
        "max_drawdown_pct","Cross"
    ]
    cols = [c for c in cols if c in x.columns]
    y = x[cols].rename(columns={
        "id":"ID","symbol":"Token","exchange":"Exchange","score":"Score",
        "entry_price":"Entrada","tp1":"TP1","tp2":"TP2","stop_price":"Stop",
        "max_return_pct":"Máx. retorno %","max_drawdown_pct":"Máx. DD %"
    })
    st.dataframe(y, use_container_width=True, hide_index=True, height=height)

with st.spinner("Actualizando mercados..."):
    df = get_market()

if df.empty:
    st.error("No fue posible obtener datos de mercado.")
    st.stop()

df["state"] = df.apply(state_cfg, axis=1)
append_history(df)
history = load_history()
df = df.sort_values(["score","volume_24h"], ascending=[False,False])
best = df.iloc[0]
opps = df[df["state"]=="ENTRAR AHORA"]
watch = df[df["state"].isin(["CERCA","ESPERAR PULLBACK"])]

signals_raw, events, supabase_error = get_signal_data()
signals = parse_signals(signals_raw)
perf = performance_metrics(signals)

def header():
    now = datetime.now(timezone.utc)
    c1,c2,c3,c4 = st.columns([1.4,1,1,1])
    c1.markdown('<div class="kicker">Última actualización</div>',unsafe_allow_html=True)
    c1.markdown(f"**{now.strftime('%d/%m/%Y %H:%M:%S UTC')}**")
    c2.markdown('<div class="kicker">Scanner dashboard</div>',unsafe_allow_html=True)
    c2.markdown(f"**~{cfg['refresh_minutes']} min**")
    c3.markdown('<div class="kicker">Tracker</div>',unsafe_allow_html=True)
    c3.markdown("**GitHub Actions ~5 min**")
    c4.success("● SISTEMA ACTIVO")

def market_banner():
    score=float(best["score"])
    if len(opps):
        title="🚨 OPORTUNIDAD ACTIVA"; cls="market-good"
    elif score>=cfg["watch_score"]:
        title="🟡 EN OBSERVACIÓN"; cls="market-watch"
    else:
        title="⚪ SIN SEÑAL CLARA"; cls="market-cold"
    st.markdown(f"""
    <div class="fin-card {cls}">
      <div class="kicker">Estado del mercado</div>
      <div style="font-size:1.35rem;font-weight:800;margin:4px 0 10px">{title}</div>
      <div style="display:flex;gap:44px;flex-wrap:wrap">
       <div><span class="small">Mejor candidato</span><br><b style="font-size:1.2rem">{best['symbol']}</b> · {best['exchange']}</div>
       <div><span class="small">Score</span><br><b>{best['score']:.1f}</b></div>
       <div><span class="small">Precio</span><br><b>{best['price']:.8g}</b></div>
       <div><span class="small">RSI 15m</span><br><b>{best['rsi_15m']:.1f}</b></div>
       <div><span class="small">Volumen rel.</span><br><b>{best['rel_volume_15m']:.2f}x</b></div>
      </div>
    </div>""", unsafe_allow_html=True)

def performance_cards():
    a,b,c,d,e = st.columns(5)
    a.metric("Señales registradas", perf["total"])
    b.metric("Señales activas", perf["active"])
    c.metric("✅ Con ganancia", perf["profitable"])
    d.metric("🛑 Stops", perf["stops"])
    dlt = f"{perf['r_total']:+.2f}R"
    e.metric("Resultado simulado", dlt)

    a,b,c,d = st.columns(4)
    a.metric("🎯 Tocaron TP1", perf["tp1"])
    b.metric("🏆 Llegaron TP2", perf["tp2"])
    c.metric("TP1 + break-even", perf["partial"])
    cval = f"{perf['win_rate']:.1f}%" if perf["resolved"] else "—"
    d.metric("Tasa de acierto resueltas", cval)

def radar_table(data, height=420):
    x=data.copy()
    labels={"ENTRAR AHORA":"🚨 ENTRAR","ESPERAR PULLBACK":"🟠 ESPERAR",
            "CERCA":"🟡 CERCA","SIN SEÑAL":"⚪ SIN SEÑAL"}
    x["Estado"]=x["state"].map(labels)
    x["Cross"]=x["cross_exchange"].map({True:"✅",False:"—"})
    out=x[["Estado","symbol","exchange","score","price","rsi_15m",
           "rel_volume_15m","change_24h_pct","rr_tp2","spread_pct","Cross"]].rename(columns={
        "symbol":"Token","exchange":"Exchange","score":"Score","price":"Precio",
        "rsi_15m":"RSI 15m","rel_volume_15m":"Vol. rel.","change_24h_pct":"24h %",
        "rr_tp2":"R/R","spread_pct":"Spread %"})
    st.dataframe(out,use_container_width=True,hide_index=True,height=height)

def score_chart():
    if history.empty:
        st.info("El historial de score se irá formando con cada escaneo.")
        return
    bases=df[df["best_exchange"]].head(6)["base"].tolist()
    hp=history[history["base"].isin(bases)]
    if hp.empty:
        st.info("Todavía no hay historial suficiente.")
        return
    pivot=hp.pivot_table(index="timestamp",columns="base",values="score",aggfunc="last").sort_index()
    st.line_chart(pivot,use_container_width=True,height=300)

header()

if supabase_error:
    st.warning("El dashboard de mercado funciona, pero falta conectar Supabase en Render para ver historial/performance.")

if page == "Dashboard":
    market_banner()
    st.markdown("### 📊 Performance del monitor")
    performance_cards()

    left,right=st.columns([1.45,1])
    with left:
        st.markdown("### 📡 Radar de mercado")
        radar_table(df[df["best_exchange"]].head(12),390)
    with right:
        st.markdown("### 📈 Evolución del score")
        score_chart()

    st.markdown("### 🧾 Últimas señales")
    signal_table(signals.head(10), 340)

elif page == "Oportunidades":
    st.markdown("## 🚨 Oportunidades actuales")
    if opps.empty:
        st.info("No hay entradas de alta calidad en este momento.")
    else:
        for _,r in opps.iterrows():
            st.markdown(f"""<div class="fin-card market-good">
            <b style="font-size:1.2rem">{r['symbol']} · {r['exchange']} · Score {r['score']:.1f}</b><br>
            <span class="small">Entrada {r['entry_low']:.8g}–{r['entry_high']:.8g} · Stop {r['stop']:.8g} ·
            TP1 {r['tp1']:.8g} · TP2 {r['tp2']:.8g} · R/R {r['rr_tp2']:.2f}</span>
            </div>""",unsafe_allow_html=True)

elif page == "Señales activas":
    st.markdown("## 🟦 Señales activas")
    active = signals[signals["status"]=="ACTIVE"] if not signals.empty else signals
    signal_table(active, 600)
    st.caption("Estas señales continúan siendo seguidas por GitHub Actions hasta TP2, STOP, break-even o expiración.")

elif page == "Historial y performance":
    st.markdown("## 📊 Historial y performance")
    performance_cards()

    if not signals.empty:
        resolved = signals[signals["status"].isin(["TP2","TP1_BE","STOP"])]
        st.markdown("### Resultado por señal resuelta")
        if resolved.empty:
            st.info("Todavía no hay señales resueltas suficientes.")
        else:
            chart = resolved.copy()
            chart["R"] = chart["status"].map({"TP2":2.0,"TP1_BE":0.75,"STOP":-1.0})
            chart["Acumulado R"] = chart.sort_values("created_at")["R"].cumsum()
            st.line_chart(
                chart.sort_values("created_at").set_index("created_at")[["Acumulado R"]],
                height=280,
            )

        st.markdown("### Historial completo")
        status_filter = st.multiselect(
            "Filtrar estado",
            ["ACTIVE","TP2","TP1_BE","STOP","EXPIRED","AMBIGUOUS"],
            default=["ACTIVE","TP2","TP1_BE","STOP","EXPIRED","AMBIGUOUS"]
        )
        signal_table(signals[signals["status"].isin(status_filter)], 620)
    else:
        st.info("Todavía no hay señales registradas.")

elif page == "Radar de mercado":
    st.markdown("## 📡 Radar de mercado")
    min_score=st.slider("Score mínimo visible",0,100,int(cfg["min_score"]))
    data=df[df["score"]>=min_score]
    if cfg["only_best"]: data=data[data["best_exchange"]]
    if cfg["only_cross"]: data=data[data["cross_exchange"]]
    radar_table(data,650)

elif page == "Evolución de scores":
    st.markdown("## 📈 Evolución de scores")
    score_chart()

elif page == "Alertas":
    st.markdown("## 🔔 Alertas y eventos")
    if events.empty:
        st.info("Todavía no hay eventos registrados.")
    else:
        e = events.copy()
        if "created_at" in e:
            e["created_at"] = pd.to_datetime(e["created_at"], utc=True, errors="coerce")
            e["Fecha"] = e["created_at"].dt.strftime("%d/%m %H:%M")
        cols=[c for c in ["Fecha","signal_id","event_type","price","notes"] if c in e.columns]
        st.dataframe(e[cols].head(100),use_container_width=True,hide_index=True,height=580)

elif page == "Configuración":
    st.markdown("## ⚙️ Configuración del dashboard")
    st.caption("Los parámetros guardados aquí afectan la clasificación visual del dashboard. El worker usa los valores definidos en GitHub Actions.")
    with st.form("config"):
        c1,c2=st.columns(2)
        with c1:
            min_score=st.slider("Score mínimo del radar",0,100,int(cfg["min_score"]))
            watch_score=st.slider("Score para CERCA",0,100,int(cfg["watch_score"]))
            alert_score=st.slider("Score mínimo ENTRAR",0,100,int(cfg["alert_score"]))
            priority_score=st.slider("Score prioritario",0,100,int(cfg["priority_score"]))
        with c2:
            max_rsi=st.number_input("RSI máximo para entrada",40.0,90.0,float(cfg["max_rsi"]),0.5)
            min_rel=st.number_input("Volumen relativo mínimo",0.1,10.0,float(cfg["min_rel_volume"]),0.1)
            min_rr=st.number_input("R/R mínimo",0.5,10.0,float(cfg["min_rr"]),0.1)
            refresh=st.selectbox("Intervalo dashboard (min)",[1,2,3,5,10],
                index=[1,2,3,5,10].index(int(cfg["refresh_minutes"])) if int(cfg["refresh_minutes"]) in [1,2,3,5,10] else 2)
        only_best=st.checkbox("Solo mejor exchange por token",value=bool(cfg["only_best"]))
        only_cross=st.checkbox("Exigir confirmación cross-exchange en radar",value=bool(cfg["only_cross"]))
        submitted=st.form_submit_button("💾 Guardar configuración",use_container_width=True)
        if submitted:
            save_config({
                "min_score":min_score,"watch_score":watch_score,"alert_score":alert_score,
                "priority_score":priority_score,"max_rsi":max_rsi,"min_rel_volume":min_rel,
                "min_rr":min_rr,"refresh_minutes":refresh,
                "only_best":only_best,"only_cross":only_cross
            })
            st.cache_data.clear()
            st.success("Configuración guardada.")
            st.rerun()

st.divider()
st.caption(
    "Performance simulada: TP2 = +2,0R · TP1 + break-even = +0,75R · STOP = -1,0R. "
    "EXPIRED y AMBIGUOUS se excluyen de la tasa de acierto. No ejecuta órdenes reales."
)
