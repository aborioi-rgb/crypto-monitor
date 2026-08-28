
import json
from pathlib import Path
from datetime import datetime, timezone

import pandas as pd
import streamlit as st
from streamlit_autorefresh import st_autorefresh
from scanner import scan_market

st.set_page_config(page_title="Crypto Monitor", page_icon="📈", layout="wide",
                   initial_sidebar_state="expanded")

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
.block-container {padding-top:1.0rem; max-width:1600px;}
section[data-testid="stSidebar"] {background:#071827; border-right:1px solid #183044;}
section[data-testid="stSidebar"] .block-container {padding-top:1rem;}
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
.small {opacity:.70;font-size:.86rem}
.kicker {opacity:.62;font-size:.72rem;text-transform:uppercase;letter-spacing:.08em}
.badge {display:inline-block;padding:4px 9px;border-radius:7px;font-weight:700;font-size:.78rem}
.badge-green {background:#123b22;color:#55e77c}
.badge-yellow {background:#40350c;color:#ffd43b}
.badge-orange {background:#47280c;color:#ff9f43}
.badge-gray {background:#202c38;color:#b9c5d2}
</style>
""", unsafe_allow_html=True)

# Sidebar navigation + configuration
with st.sidebar:
    st.markdown("## 📈 CRYPTO MONITOR")
    st.caption("SCANNER INTELIGENTE")
    page = st.radio("Navegación",
        ["Dashboard","Oportunidades","Radar de mercado","Evolución de scores",
         "Alertas","Portfolio","Backtesting","Configuración"],
        label_visibility="collapsed")
    st.divider()
    st.caption("SISTEMA")
    st.success("● Sistema activo")
    st.write("KuCoin + MEXC")
    st.caption("Spot USDT · Universo dinámico")

# Refresh interval is editable from Config
st_autorefresh(interval=int(cfg["refresh_minutes"] * 60_000), key="auto_refresh")

@st.cache_data(ttl=max(50, int(cfg["refresh_minutes"]*60)-10), show_spinner=False)
def get_data():
    return scan_market()

def append_history(df):
    if df.empty: return
    h = df[df["best_exchange"]][["base","exchange","score","state","price",
                                "rsi_15m","rel_volume_15m"]].copy()
    h["timestamp"] = datetime.now(timezone.utc).isoformat()
    header = not HISTORY_FILE.exists()
    h.to_csv(HISTORY_FILE, mode="a", header=header, index=False)

def load_history():
    if not HISTORY_FILE.exists(): return pd.DataFrame()
    try:
        h = pd.read_csv(HISTORY_FILE)
        h["timestamp"] = pd.to_datetime(h["timestamp"], utc=True)
        cutoff = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=7)
        return h[h["timestamp"] >= cutoff].copy()
    except Exception:
        return pd.DataFrame()

with st.spinner("Actualizando mercados..."):
    df = get_data()
if df.empty:
    st.error("No fue posible obtener datos de mercado.")
    st.stop()

# Reclassify using editable settings.
def state_cfg(r):
    extended = r["rsi_15m"] > cfg["max_rsi"]
    if (r["score"] >= cfg["alert_score"] and not extended
        and r["rel_volume_15m"] >= cfg["min_rel_volume"]
        and r["rr_tp2"] >= cfg["min_rr"]):
        return "ENTRAR AHORA"
    if r["score"] >= cfg["alert_score"] and extended:
        return "ESPERAR PULLBACK"
    if r["score"] >= cfg["watch_score"]:
        return "CERCA"
    return "SIN SEÑAL"

df["state"] = df.apply(state_cfg, axis=1)
append_history(df)
history = load_history()

# Fix score delta: compare current score against most recent PRIOR recorded score.
def delta_for(r):
    if history.empty: return 0.0
    h = history[(history["base"]==r["base"]) & (history["exchange"]==r["exchange"])].sort_values("timestamp")
    if len(h) < 2: return 0.0
    # Last row is often the just-appended current scan; use previous distinct observation.
    vals = h["score"].astype(float).tolist()
    current = float(r["score"])
    prior = None
    for v in reversed(vals[:-1]):
        if abs(v-current) > 1e-9:
            prior = v
            break
    if prior is None and len(vals) >= 2:
        prior = vals[-2]
    return round(current - float(prior), 1) if prior is not None else 0.0

df["score_delta"] = df.apply(delta_for, axis=1)
df = df.sort_values(["score","volume_24h"], ascending=[False,False])
best = df.iloc[0]
opps = df[df["state"]=="ENTRAR AHORA"]
watch = df[df["state"].isin(["CERCA","ESPERAR PULLBACK"])]

def header():
    now = datetime.now(timezone.utc)
    c1,c2,c3,c4 = st.columns([1.4,1,1,1])
    c1.markdown('<div class="kicker">Última actualización</div>',unsafe_allow_html=True)
    c1.markdown(f"**{now.strftime('%d/%m/%Y %H:%M:%S UTC')}**")
    c2.markdown('<div class="kicker">Próximo escaneo</div>',unsafe_allow_html=True)
    c2.markdown(f"**~{cfg['refresh_minutes']} minutos**")
    c3.markdown('<div class="kicker">Intervalo</div>',unsafe_allow_html=True)
    c3.markdown(f"**{cfg['refresh_minutes']} min**")
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
      <div style="display:flex;gap:50px;flex-wrap:wrap">
       <div><span class="small">Mejor candidato</span><br><b style="font-size:1.25rem">{best['symbol']}</b> · {best['exchange']}</div>
       <div><span class="small">Score</span><br><b style="font-size:1.25rem">{best['score']:.1f}</b></div>
       <div><span class="small">Precio</span><br><b>{best['price']:.8g}</b></div>
       <div><span class="small">RSI 15m</span><br><b>{best['rsi_15m']:.1f}</b></div>
       <div><span class="small">Volumen rel.</span><br><b>{best['rel_volume_15m']:.2f}x</b></div>
      </div>
    </div>""", unsafe_allow_html=True)

def summary():
    a,b,c,d = st.columns(4)
    a.metric("Activos analizados",len(df))
    b.metric("ENTRAR AHORA",len(opps))
    c.metric("En observación",len(watch))
    d.metric("Score máximo",f"{df['score'].max():.1f}")

def radar_table(data, height=480):
    x=data.copy()
    labels={"ENTRAR AHORA":"🚨 ENTRAR","ESPERAR PULLBACK":"🟠 ESPERAR",
            "CERCA":"🟡 CERCA","SIN SEÑAL":"⚪ SIN SEÑAL"}
    x["Estado"]=x["state"].map(labels)
    x["Δ Score"]=x["score_delta"].map(lambda v: f"{'↑ +' if v>0 else '↓ ' if v<0 else '→ '}{v:.1f}")
    x["Cross"]=x["cross_exchange"].map({True:"✅",False:"—"})
    out=x[["Estado","symbol","exchange","score","Δ Score","price","rsi_15m",
           "rel_volume_15m","change_24h_pct","rr_tp2","spread_pct","Cross"]].rename(columns={
        "symbol":"Token","exchange":"Exchange","score":"Score","price":"Precio",
        "rsi_15m":"RSI 15m","rel_volume_15m":"Vol. rel.","change_24h_pct":"24h %",
        "rr_tp2":"R/R","spread_pct":"Spread %"})
    st.dataframe(out,use_container_width=True,hide_index=True,height=height)

def score_chart():
    if history.empty:
        st.info("El historial se irá formando con cada escaneo.")
        return
    bases=df[df["best_exchange"]].head(6)["base"].tolist()
    hp=history[history["base"].isin(bases)]
    if hp.empty:
        st.info("Todavía no hay historial suficiente.")
        return
    pivot=hp.pivot_table(index="timestamp",columns="base",values="score",aggfunc="last").sort_index()
    st.line_chart(pivot,use_container_width=True,height=330)

header()

if page=="Dashboard":
    market_banner()
    summary()
    st.markdown("### Estado de señales")
    a,b,c,d=st.columns(4)
    a.metric("🚨 ENTRAR AHORA",len(df[df.state=="ENTRAR AHORA"]))
    b.metric("🟠 ESPERAR PULLBACK",len(df[df.state=="ESPERAR PULLBACK"]))
    c.metric("🟡 CERCA",len(df[df.state=="CERCA"]))
    d.metric("⚪ SIN SEÑAL",len(df[df.state=="SIN SEÑAL"]))
    left,right=st.columns([1.55,1])
    with left:
        st.markdown("### 📡 Radar de mercado")
        radar_table(df[df["best_exchange"]].head(12),390)
    with right:
        st.markdown("### 📈 Evolución del score")
        score_chart()

elif page=="Oportunidades":
    st.markdown("## 🚨 Oportunidades")
    if opps.empty:
        st.info("No hay entradas de alta calidad en este momento.")
    else:
        for _,r in opps.iterrows():
            st.markdown(f"""<div class="fin-card market-good">
            <b style="font-size:1.2rem">{r['symbol']} · {r['exchange']} · Score {r['score']:.1f}</b><br>
            <span class="small">Entrada {r['entry_low']:.8g}–{r['entry_high']:.8g} · Stop {r['stop']:.8g} ·
            TP1 {r['tp1']:.8g} · TP2 {r['tp2']:.8g} · R/R {r['rr_tp2']:.2f}</span>
            </div>""",unsafe_allow_html=True)

elif page=="Radar de mercado":
    st.markdown("## 📡 Radar de mercado")
    min_score=st.slider("Score mínimo visible",0,100,int(cfg["min_score"]))
    data=df[df["score"]>=min_score]
    if cfg["only_best"]: data=data[data["best_exchange"]]
    if cfg["only_cross"]: data=data[data["cross_exchange"]]
    radar_table(data,650)

elif page=="Evolución de scores":
    st.markdown("## 📈 Evolución de scores")
    score_chart()
    st.caption("La serie se construye con los escaneos guardados en el equipo/servidor.")

elif page=="Alertas":
    st.markdown("## 🔔 Alertas")
    st.info("Este módulo quedará conectado al worker 24/7 y a las notificaciones al celular en la próxima etapa.")
    radar_table(df[df["state"].isin(["ENTRAR AHORA","ESPERAR PULLBACK","CERCA"])].head(20),420)

elif page=="Portfolio":
    st.markdown("## 💼 Portfolio")
    st.info("Próxima etapa: registrar una compra y seguir P&L, stop, TP y deterioro del momentum.")

elif page=="Backtesting":
    st.markdown("## 🧪 Backtesting")
    st.info("Próxima etapa: medir cuántas señales habrían alcanzado TP1, TP2 o stop antes de operar con dinero real.")

elif page=="Configuración":
    st.markdown("## ⚙️ Configuración")
    st.caption("Estos parámetros se guardan desde la propia página. No necesitás tocar CMD.")
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
            refresh=st.selectbox("Intervalo de escaneo (min)",[1,2,3,5,10],
                                 index=[1,2,3,5,10].index(int(cfg["refresh_minutes"])) if int(cfg["refresh_minutes"]) in [1,2,3,5,10] else 2)
        only_best=st.checkbox("Solo mejor exchange por token",value=bool(cfg["only_best"]))
        only_cross=st.checkbox("Exigir confirmación cross-exchange en radar",value=bool(cfg["only_cross"]))
        submitted=st.form_submit_button("💾 Guardar configuración",use_container_width=True)
        if submitted:
            new={"min_score":min_score,"watch_score":watch_score,"alert_score":alert_score,
                 "priority_score":priority_score,"max_rsi":max_rsi,"min_rel_volume":min_rel,
                 "min_rr":min_rr,"refresh_minutes":refresh,"only_best":only_best,"only_cross":only_cross}
            save_config(new)
            st.cache_data.clear()
            st.success("Configuración guardada. Recargando...")
            st.rerun()

    if st.button("Restaurar valores recomendados"):
        save_config(DEFAULTS)
        st.cache_data.clear()
        st.rerun()

st.divider()
st.caption("Crypto Monitor · Herramienta experimental de análisis técnico. No ejecuta órdenes; ninguna señal garantiza rentabilidad.")
