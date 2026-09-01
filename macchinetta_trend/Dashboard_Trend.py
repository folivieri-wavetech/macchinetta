import streamlit as st
import pandas as pd
import time
from config import Config
from core_engine import CoreEngine, Candle
from history_generator import generate_history, load_history
import os

# Configurazione Pagina
st.set_page_config(page_title="Macchinetta Trend V2.1 - Backtester", layout="wide")
st.title("🧪 Macchinetta Trend V2.1 - Laboratorio di Backtest")

# Inizializza session state
if 'config' not in st.session_state:
    st.session_state.config = Config()
if 'engine' not in st.session_state:
    st.session_state.engine = CoreEngine(st.session_state.config)
if 'logs' not in st.session_state:
    st.session_state.logs = []
if 'backtest_data' not in st.session_state:
    st.session_state.backtest_data = [] # Tutte le candele caricate
if 'current_step' not in st.session_state:
    st.session_state.current_step = 0 # Indice della candela a cui siamo arrivati

# --- SIDEBAR: PARAMETRI ---
st.sidebar.header("⚙️ Parametri Strategia V2")
cfg = st.session_state.config

# 1. Selettore Timeframe per autoconfigurare il min_body
tf_options = {"M5 / M10": 5.0, "H1 / H4": 10.0, "Daily": 20.0}
selected_tf = st.sidebar.selectbox("Seleziona Timeframe (Imposta Min Body)", list(tf_options.keys()))
auto_min_body = tf_options[selected_tf]

new_size_i = st.sidebar.number_input("Size Iniziale (Core)", value=cfg.get("size_i"))
new_size_f = st.sidebar.number_input("Size Finale (Max)", value=cfg.get("size_f"))
new_pip_value = st.sidebar.number_input("Valore di 1 Pip/Punto", value=float(cfg.get("pip_value")), format="%0.4f")

st.sidebar.markdown("---")
st.sidebar.subheader("Donchian Channels")
new_tk = st.sidebar.number_input("Periodi Tenkan (TK)", value=cfg.get("tk_periods"))
new_kj = st.sidebar.number_input("Periodi Kijun (KJ)", value=cfg.get("kj_periods"))

st.sidebar.markdown("---")
new_body = st.sidebar.number_input("Body Minimo (Sovrascrivibile)", value=auto_min_body)

if st.sidebar.button("💾 Salva Parametri", width="stretch"):
    cfg.set("size_i", new_size_i)
    cfg.set("size_f", new_size_f)
    cfg.set("pip_value", new_pip_value)
    cfg.set("tk_periods", new_tk)
    cfg.set("kj_periods", new_kj)
    cfg.set("min_body", new_body)
    st.sidebar.success("Parametri salvati!")

# --- GESTIONE DATI STORICI ---
st.markdown("### 📊 Dataset di Mercato")
col_d1, col_d2 = st.columns([1, 2])

with col_d1:
    if st.button("🎲 Genera Nuovo Storico Random (Gold 5M)", width="stretch"):
        filepath, raw_data = generate_history(filename="storico_5m.csv", num_candles=300, start_price=4500.0, pip_value=cfg.get("pip_value"))
        st.session_state.backtest_data = raw_data
        st.session_state.current_step = 0
        st.session_state.engine.reset()
        st.session_state.logs = []
        st.rerun()

with col_d2:
    if st.button("📂 Carica Storico Esistente", width="stretch"):
        raw_data = load_history("storico_5m.csv")
        if raw_data:
            st.session_state.backtest_data = raw_data
            st.session_state.current_step = 0
            st.session_state.engine.reset()
            st.session_state.logs = []
            st.rerun()
        else:
            st.error("Nessun file 'storico_5m.csv' trovato. Generane uno primo!")

st.markdown("---")

if not st.session_state.backtest_data:
    st.info("Nessun dato di mercato caricato. Genera o carica uno storico per iniziare il backtest.")
    st.stop()

# Estraiamo i dati utili per il backtest (le prime 55 candele servono solo per il seed di TK e KJ)
kj_p = cfg.get("kj_periods")
if len(st.session_state.backtest_data) <= kj_p:
    st.error("Lo storico è troppo breve per calcolare gli indicatori!")
    st.stop()

# Le prime N candele le diamo in pasto subito al motore come storico passato
seed_data = st.session_state.backtest_data[:kj_p]
future_data = st.session_state.backtest_data[kj_p:]
tot_future = len(future_data)

def get_current_portfolio_str(pm, current_price):
    """Genera una stringa riassuntiva del portafoglio attuale per il log"""
    if not pm.core_position and not pm.increments:
        return "FLAT", "0"
        
    parts = []
    tot_pnl = 0.0
    if pm.core_position:
        pnl = pm.core_position.close(current_price)
        pm.core_position.is_closed = False # Solo per simulare il pnl
        tot_pnl += pnl
        sign_c = "+" if pm.core_position.direction == "LONG" else "-"
        parts.append(f"{sign_c}{pm.core_position.size}@{pm.core_position.entry_price:.0f}")
        
    if pm.increments:
        tot_inc_size = sum(inc.size for inc in pm.increments)
        sign_i = "+" if pm.increments[0].direction == "LONG" else "-"
        parts.append(f"{sign_i}{tot_inc_size}")
        
        for inc in pm.increments:
            pnl = inc.close(current_price)
            inc.is_closed = False
            tot_pnl += pnl
        
    return " ".join(parts), f"{tot_pnl:.0f} €"

# --- INIZIO BACKTEST ---
if st.session_state.current_step == 0:
    st.info(f"Storico caricato. {kj_p} candele usate per il setup iniziale. {tot_future} candele pronte da tradare.")
    
    if st.button("▶️ AVVIA BACKTEST (Entra a Mercato)", width="stretch"):
        # Inizializziamo il motore con le prime 55 candele reali
        storico_candele = []
        for d in seed_data:
            storico_candele.append(Candle(d['open'], d['high'], d['low'], d['close']))
        
        st.session_state.engine.seed_history(storico_candele)
        
        # Facciamo entrare il bot a mercato sull'ultima candela del seed
        last_c = seed_data[-1]
        eval_price = last_c['close']
        exec_price = future_data[0]['open'] if future_data else eval_price
        
        # Determinazione direzione iniziale intelligente basata sulla Kijun e Tenkan
        kj_iniziale = st.session_state.engine._calculate_donchian(cfg.get('kj_periods'))
        tk_iniziale = st.session_state.engine._calculate_donchian(cfg.get('tk_periods'))
        
        dir_iniziale = "FLAT"
        tolleranza = cfg.get('min_body') * cfg.get('pip_value')
        max_dist = cfg.get('max_kj_distance') * cfg.get('pip_value')
        
        if eval_price > tk_iniziale and (tk_iniziale > kj_iniziale or abs(tk_iniziale - kj_iniziale) <= tolleranza):
            if abs(exec_price - kj_iniziale) <= max_dist:
                dir_iniziale = "LONG"
        elif eval_price < tk_iniziale and (tk_iniziale < kj_iniziale or abs(tk_iniziale - kj_iniziale) <= tolleranza):
            if abs(exec_price - kj_iniziale) <= max_dist:
                dir_iniziale = "SHORT"
            
        if dir_iniziale != "FLAT":
            st.session_state.engine.start(exec_price, dir_iniziale)
            sign_start = "+" if dir_iniziale == "LONG" else "-"
            azione = f"START {sign_start}{cfg.get('size_i')}{dir_iniziale[0]}@{exec_price}"
        else:
            st.session_state.engine.is_running = True
            st.session_state.engine.current_direction = "FLAT"
            azione = "START FLAT (In Attesa)"
        
        # Inizializza il diario di bordo con la candela di innesco
        st.session_state.logs = []
        portf, latente = get_current_portfolio_str(st.session_state.engine.pm, exec_price)
        
        st.session_state.logs.append({
            "#": kj_p,
            "OHLC": f"{last_c['open']}-{last_c['high']}-{last_c['low']}-{last_c['close']}",
            "TK": f"{tk_iniziale:.0f}",
            "KJ": f"{kj_iniziale:.0f}",
            "Azione": azione,
            "Chiusure": "",
            "P/L Rea": "",
            "Portafoglio": portf,
            "P/L Lat": latente
        })
        
        st.session_state.current_step = 1 # pronti a leggere la prima candela "nuova"
        st.rerun()
    st.stop() # Fermiamoci qui finché non preme avvia


# --- CONTROLLI RIPRODUZIONE ---

def elabora_candela_step(indice_relativo):
    d = future_data[indice_relativo]
    c = Candle(d['open'], d['high'], d['low'], d['close'])
    
    next_open = future_data[indice_relativo + 1]['open'] if indice_relativo + 1 < len(future_data) else d['close']
    evs = st.session_state.engine.on_candle_close(c, next_open)
    azione_txt = ""
    chiusure_txt = ""
    pnl_real_txt = ""
    
    # Decodifichiamo gli eventi in azioni testuali super compatte
    if evs:
        azioni = []
        chiusure = []
        pnl_real_tot = 0.0
        
        for e in evs:
            if e['type'] == 'increment_opened':
                sign_inc = "+1" if e['direction'] == 'LONG' else "-1"
                azioni.append(f"{sign_inc}{e['direction'][0]}@{e['price']}")
            elif e['type'] == 'increments_cleared':
                azioni.append("TkCross")
            elif e['type'] == 'reversal':
                if e['new_direction'] == 'FLAT':
                    azioni.append("STOP -> FLAT")
                else:
                    sign_rev = "+" if e['new_direction'] == 'LONG' else "-"
                    azioni.append(f"Rev->{sign_rev}{cfg.get('size_i')}{e['new_direction'][0]}")
            elif e['type'] == 'fifo_close':
                azioni.append("FIFO")
            
            # Tracciamo le chiusure
            if e['type'] in ['increment_closed', 'core_closed', 'fifo_close']:
                chiusure.append(f"{e['type'].split('_')[0][:3]}@{e['price']}({e['pnl']:.0f}€)")
                pnl_real_tot += e.get('pnl', 0.0)
                
        if azioni:
            azione_txt = " ".join(azioni)
        if chiusure:
            chiusure_txt = " ".join(chiusure)
            pnl_real_txt = f"{pnl_real_tot:.0f}"
            
    tk_val = st.session_state.engine.current_tk
    kj_val = st.session_state.engine.current_kj
    portf, latente = get_current_portfolio_str(st.session_state.engine.pm, d['close'])
            
    st.session_state.logs.append({
        "#": kj_p + indice_relativo + 1,
        "OHLC": f"{d['open']}-{d['high']}-{d['low']}-{d['close']}",
        "TK": f"{tk_val:.0f}" if tk_val else "-",
        "KJ": f"{kj_val:.0f}" if kj_val else "-",
        "Azione": azione_txt,
        "Chiusure": chiusure_txt,
        "P/L Rea": pnl_real_txt,
        "Portafoglio": portf,
        "P/L Lat": latente
    })



# --- PANNELLO GRAFICO E INFO ---
st.markdown("---")
st.subheader("📈 Grafico di Mercato")

import plotly.graph_objects as go

if st.session_state.backtest_data:
    df_chart = pd.DataFrame(st.session_state.backtest_data)
    df_chart['TK'] = (df_chart['high'].rolling(cfg.get('tk_periods')).max() + df_chart['low'].rolling(cfg.get('tk_periods')).min()) / 2
    df_chart['KJ'] = (df_chart['high'].rolling(cfg.get('kj_periods')).max() + df_chart['low'].rolling(cfg.get('kj_periods')).min()) / 2
    
    current_idx = kj_p + max(0, st.session_state.current_step - 1)
    df_vis = df_chart.iloc[:current_idx+1]
    
    fig = go.Figure()
    fig.add_trace(go.Candlestick(x=df_vis.index,
                    open=df_vis['open'], high=df_vis['high'],
                    low=df_vis['low'], close=df_vis['close'],
                    name='Prezzo'))
    fig.add_trace(go.Scatter(x=df_vis.index, y=df_vis['TK'], line=dict(color='#00BFFF', width=1), name='Tenkan (TK)'))
    fig.add_trace(go.Scatter(x=df_vis.index, y=df_vis['KJ'], line=dict(color='#FFD700', width=2), name='Kijun (KJ)'))
    
    fig.update_layout(height=400, margin=dict(l=20, r=20, t=20, b=20), xaxis_rangeslider_visible=False)
    st.plotly_chart(fig, use_container_width=True)


col_info1, col_info2 = st.columns([1, 1.5])

with col_info1:
    st.subheader("⚙️ Stato & Indicatori")
    engine = st.session_state.engine
    st.metric("Motore Macchinetta", "🟢 RUNNING" if engine.is_running else "🔴 STOPPED")
    
    if engine.current_tk is not None and engine.current_kj is not None:
        last_price = engine.candles[-1].close
        st.markdown(f"**Ultimo Prezzo:** {last_price:.2f}")
        st.write(f"🔵 **Tenkan (TK):** {engine.current_tk:.2f}")
        st.write(f"🔴 **Kijun (KJ):** {engine.current_kj:.2f}")
        
        if last_price > engine.current_kj:
            st.success(f"Tendenza: Rialzista (Prezzo > KJ) | Posizione: {engine.current_direction}")
        else:
            st.error(f"Tendenza: Ribassista (Prezzo < KJ) | Posizione: {engine.current_direction}")

with col_info2:
    st.subheader("💼 Posizioni Attive")
    pm = engine.pm
    curr_p = engine.candles[-1].close if engine.candles else 0.0
    
    active_data = []
    tot_pnl = 0.0
    
    if pm.core_position:
        if pm.core_position.direction == "LONG":
            pnl = (curr_p - pm.core_position.entry_price) * pm.core_position.size
        else:
            pnl = (pm.core_position.entry_price - curr_p) * pm.core_position.size
        tot_pnl += pnl
        active_data.append({
            "Tipo": f"Core ({pm.core_position.direction})",
            "Entry": f"{pm.core_position.entry_price:.2f}",
            "Size": pm.core_position.size,
            "P&L €": round(pnl, 2)
        })
        
    for i, inc in enumerate(pm.increments):
        if inc.direction == "LONG":
            pnl = (curr_p - inc.entry_price) * inc.size
        else:
            pnl = (inc.entry_price - curr_p) * inc.size
        tot_pnl += pnl
        active_data.append({
            "Tipo": f"Inc {i+1} ({inc.direction})",
            "Entry": f"{inc.entry_price:.2f}",
            "Size": inc.size,
            "P&L €": round(pnl, 2)
        })
        
    if active_data:
        st.dataframe(pd.DataFrame(active_data), hide_index=True)
        st.success(f"**P&L Corrente Latente: {round(tot_pnl, 2)} €**")
    else:
        st.info("Nessuna posizione a mercato in questo istante.")

# Log Unico
st.markdown("---")

col_ctrl1, col_ctrl2 = st.columns(2)

with col_ctrl1:
    if st.button("⏯️ PROSSIMA CANDELA", width="stretch"):
        if st.session_state.current_step <= tot_future:
            elabora_candela_step(st.session_state.current_step - 1)
            st.session_state.current_step += 1
            st.rerun()

with col_ctrl2:
    if st.button("⏩ ESEGUI TUTTO", width="stretch"):
        for i in range(st.session_state.current_step - 1, tot_future):
            elabora_candela_step(i)
        st.session_state.current_step = tot_future + 1
        st.rerun()

st.progress(min(st.session_state.current_step / tot_future, 1.0), text=f"Step: {min(st.session_state.current_step-1, tot_future)}/{tot_future}")

if st.session_state.current_step > tot_future:
    if st.button("🔄 Reset Simulazione", width="stretch"):
        st.session_state.current_step = 0
        st.session_state.engine.reset()
        st.session_state.logs = []
        st.rerun()

st.subheader("📜 Diario Operativo Dettagliato (Ultime 10 Righe)")
if st.session_state.logs:
    df_logs = pd.DataFrame(st.session_state.logs).tail(10)
    
    def color_ohlc(val):
        """Colora la cella OHLC di verde o rosso in base a open e close."""
        if not isinstance(val, str) or '-' not in val:
            return ''
        try:
            parts = val.split('-')
            o = float(parts[0])
            c = float(parts[3])
            if c > o:
                return 'background-color: #7CFC00; color: black; font-weight: bold' # Verde erba (LawnGreen)
            elif c < o:
                return 'background-color: #FA8072; color: black; font-weight: bold' # Rosso salmone
        except:
            pass
        return ''
        
    def color_tk(val):
        return 'color: #00BFFF; font-weight: bold' # Azzurro chiaro
        
    def color_kj(val):
        return 'color: #FFD700; font-weight: bold' # Giallo oro
        
    styled_df = df_logs.style.map(color_ohlc, subset=['OHLC']) \
                             .map(color_tk, subset=['TK']) \
                             .map(color_kj, subset=['KJ'])
                             
    st.dataframe(styled_df, use_container_width=True, hide_index=True)
