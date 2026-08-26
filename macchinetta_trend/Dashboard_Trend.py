import streamlit as st
import pandas as pd
import time
import random
from config import Config
from core_engine import CoreEngine

# Configurazione Pagina
st.set_page_config(page_title="Macchinetta Trend - Simulatore", layout="wide")

st.title("📈 Macchinetta Trend - Dashboard di Simulazione Locale")

# Inizializza session state
if 'config' not in st.session_state:
    st.session_state.config = Config()
if 'engine' not in st.session_state:
    st.session_state.engine = CoreEngine(st.session_state.config)
if 'price_history' not in st.session_state:
    st.session_state.price_history = []
if 'current_price' not in st.session_state:
    st.session_state.current_price = 5000.0
if 'logs' not in st.session_state:
    st.session_state.logs = []

# --- SIDEBAR: PARAMETRI ---
st.sidebar.header("⚙️ Parametri Macchinetta")
cfg = st.session_state.config

# Costruisci input fields dai config
new_size_i = st.sidebar.number_input("Size Iniziale (Core)", value=cfg.get("size_i"))
new_size_f = st.sidebar.number_input("Size Finale (Max)", value=cfg.get("size_f"))
new_griglia = st.sidebar.number_input("Griglia Breakout", value=cfg.get("griglia"))
st.sidebar.markdown(f"*(TS Distanza: {new_griglia} | Passo: {new_griglia/4})*")
st.sidebar.markdown("---")
new_inc_tp = st.sidebar.number_input("Incremento Take Profit", value=cfg.get("inc_tp"))
st.sidebar.markdown("---")
st.sidebar.subheader("Logica Uncino")
new_step = st.sidebar.number_input("Step Correzione (Drop)", value=cfg.get("step_correzione"))
new_rimbalzo = st.sidebar.number_input("Rimbalzo (Conferma Uncino)", value=cfg.get("rimbalzo_uncino"))

if st.sidebar.button("💾 Salva Parametri"):
    cfg.set("size_i", new_size_i)
    cfg.set("size_f", new_size_f)
    cfg.set("griglia", new_griglia)
    cfg.set("inc_tp", new_inc_tp)
    cfg.set("step_correzione", new_step)
    cfg.set("rimbalzo_uncino", new_rimbalzo)
    st.sidebar.success("Parametri salvati!")

# --- MAIN AREA ---
col1, col2, col3 = st.columns(3)

# Controlli Simulatore
with col1:
    st.subheader("🕹️ Controlli Simulazione")
    manual_price = st.number_input("Prezzo Mercato Reale", value=st.session_state.current_price, step=1.0)
    
    colA, colB = st.columns(2)
    with colA:
        if st.button("▶️ START Macchinetta", width="stretch"):
            if not st.session_state.engine.is_running:
                st.session_state.engine.start(manual_price)
                st.session_state.logs.insert(0, f"Avvio Macchinetta. Prezzo: {manual_price}")
                st.rerun()
            else:
                st.warning("Macchinetta già in esecuzione!")
                
    with colB:
        if st.button("⏹️ STOP", width="stretch"):
            st.session_state.engine.reset()
            st.session_state.logs.insert(0, "Macchinetta fermata manualmente.")
            st.rerun()

    # Simulatore di movimento (Tick manuale)
    st.markdown("---")
    st.write("Spingi il prezzo a mano:")
    
    col_up, col_dw = st.columns(2)
    with col_up:
        if st.button("📈 TICK SU (+1pt)"):
            st.session_state.current_price += 1.0
            manual_price = st.session_state.current_price
            st.session_state.price_history.append(manual_price)
            st.session_state.logs.insert(0, f"--- Inviato Tick SU: {manual_price} ---")
            events = st.session_state.engine.on_tick(manual_price)
            for ev in events:
                st.session_state.logs.insert(0, str(ev))
            st.rerun()
            
    with col_dw:
        if st.button("📉 TICK GIÙ (-1pt)"):
            st.session_state.current_price -= 1.0
            manual_price = st.session_state.current_price
            st.session_state.price_history.append(manual_price)
            st.session_state.logs.insert(0, f"--- Inviato Tick GIU': {manual_price} ---")
            events = st.session_state.engine.on_tick(manual_price)
            for ev in events:
                st.session_state.logs.insert(0, str(ev))
            st.rerun()

    st.markdown("---")
    if st.button("Invia Prezzo Personalizzato 📩", width="stretch"):
        st.session_state.current_price = manual_price
        st.session_state.price_history.append(manual_price)
        st.session_state.logs.insert(0, f"--- Inviato Salto Prezzo a: {manual_price} ---")
        events = st.session_state.engine.on_tick(manual_price)
        for ev in events:
            st.session_state.logs.insert(0, str(ev))
        st.rerun()

    # Generatore Randomico
    st.markdown("---")
    if st.button("Simula 10 Tick Random 🎲"):
        for _ in range(10):
            # Movimento randomico +/- 10 punti
            move = random.uniform(-10, 10)
            st.session_state.current_price += move
            p = round(st.session_state.current_price, 2)
            st.session_state.price_history.append(p)
            events = st.session_state.engine.on_tick(p)
            for ev in events:
                st.session_state.logs.insert(0, f"Prezzo {p}: {str(ev)}")
        st.rerun()

# Info Stato Motore
with col2:
    st.subheader("⚙️ Stato Motore")
    engine = st.session_state.engine
    
    st.metric("Status", "🟢 RUNNING" if engine.is_running else "🔴 STOPPED")
    if engine.is_running:
        st.write(f"**Massimo Assoluto:** {engine.absolute_high}")
        if engine.buy_stop_level:
            st.write(f"**Attesa Buy Stop:** {engine.buy_stop_level}")
        st.write(f"**In Correzione:** {'Sì' if engine.is_in_correction else 'No'} (Low: {engine.correction_low})")

# Posizioni Attive
with col3:
    st.subheader("💼 Posizioni Attive")
    pm = st.session_state.engine.pm
    curr_p = st.session_state.current_price
    
    active_data = []
    tot_pnl = 0.0
    
    if pm.core_position:
        pnl = (curr_p - pm.core_position.entry_price) * pm.core_position.size
        tot_pnl += pnl
        active_data.append({
            "Tipo": "Core",
            "Entry": pm.core_position.entry_price,
            "Size": pm.core_position.size,
            "TS": pm.core_position.trailing_stop_level,
            "P&L €": round(pnl, 2)
        })
        
    for i, inc in enumerate(pm.increments):
        pnl = (curr_p - inc.entry_price) * inc.size
        tot_pnl += pnl
        active_data.append({
            "Tipo": f"Inc {i+1}",
            "Entry": inc.entry_price,
            "Size": inc.size,
            "TS": inc.trailing_stop_level,
            "P&L €": round(pnl, 2)
        })
        
    if active_data:
        st.dataframe(pd.DataFrame(active_data), hide_index=True)
        st.success(f"**P&L Totale Aperto: {round(tot_pnl, 2)} €**")
    else:
        st.info("Nessuna posizione aperta.")

# Log Eventi
st.markdown("---")
st.subheader("📜 Log Eventi")
log_df = pd.DataFrame({"Eventi Recenti": st.session_state.logs[:50]})
st.dataframe(log_df, use_container_width=True, hide_index=True)
