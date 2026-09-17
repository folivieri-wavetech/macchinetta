import os
import streamlit as st
import time
from hyper_gold_engine import HyperGoldEngine, CANDLE_SECONDS, WARMUP_BARS_KJ, CORE_CONTRACTS, CORE_TS_TRIGGER_PIPS, CORE_TS_LOCK_PIPS, CORE_TS_DISTANCE_PIPS, INC_CONTRACTS, MAX_INCREMENTS, INC_TP_PIPS, is_gold_trading_suspended, is_gold_feed_suspended

# Configurazione Pagina Streamlit
st.set_page_config(
    page_title="[30S] Hyper Spot Gold 1€",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Istanza Engine Singleton
engine = HyperGoldEngine.get_instance()
if engine.position is None and os.path.exists("hyper_gold_state.json"):
    engine.load_state()

# Stile CSS Dark Moderno
st.markdown("""
<style>
    .reportview-container, .main { background-color: #0f172a; color: #f8fafc; }
    .kpi-card {
        background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
        border: 1px solid #334155;
        border-radius: 10px;
        padding: 14px 18px;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.2);
    }
    .kpi-title { font-size: 0.82rem; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 4px; }
    .kpi-val { font-size: 1.65rem; font-weight: 700; }
    .kpi-sub { font-size: 0.78rem; margin-top: 3px; }
    .badge-live {
        display: inline-block; padding: 3px 8px; border-radius: 6px; font-weight: 600; font-size: 0.75rem;
    }
    .table-dark {
        width: 100%; border-collapse: collapse; font-size: 0.85rem;
    }
    .table-dark th { background-color: #1e293b; color: #94a3b8; padding: 8px 10px; text-align: left; }
    .table-dark td { padding: 7px 10px; border-bottom: 1px solid #334155; }

    /* Pulsante AVVIA TRADING: verde quando attivo, disabilitato quando trading attivo */
    .btn-start div.stButton > button {
        background-color: #16a34a !important;
        border: 1px solid #22c55e !important;
        color: #ffffff !important;
        font-weight: 700 !important;
    }
    .btn-start div.stButton > button:hover:not(:disabled) {
        background-color: #15803d !important;
        border-color: #16a34a !important;
    }
    .btn-start div.stButton > button:disabled {
        background-color: #1e293b !important;
        border: 1px solid #334155 !important;
        color: #64748b !important;
        opacity: 0.50 !important;
        cursor: not-allowed !important;
    }

    /* Pulsante STOP TRADING: rosso quando attivo, disabilitato quando trading in pausa */
    .btn-stop div.stButton > button {
        background-color: #dc2626 !important;
        border: 1px solid #ef4444 !important;
        color: #ffffff !important;
        font-weight: 700 !important;
    }
    .btn-stop div.stButton > button:hover:not(:disabled) {
        background-color: #b91c1c !important;
        border-color: #dc2626 !important;
    }
    .btn-stop div.stButton > button:disabled {
        background-color: #1e293b !important;
        border: 1px solid #334155 !important;
        color: #64748b !important;
        opacity: 0.50 !important;
        cursor: not-allowed !important;
    }
</style>
""", unsafe_allow_html=True)

# Frammento autorefresh ogni 1 secondo
@st.fragment(run_every=1)
def render_live_desk():
    with engine.lock:
        is_conn = engine.ls_connected
        live_mid = engine.live_mid
        live_bid = engine.live_bid
        live_ask = engine.live_ask
        live_time = engine.live_time_str
        total_ticks = engine.total_ticks
        candles_count = len(engine.candles)
        kj = engine.kj55
        balance = engine.balance
        init_bal = engine.initial_balance
        pos = engine.position
        increments = list(engine.increments)
        total_contracts = (pos.get("contracts", CORE_CONTRACTS) + sum(i.get("contracts", INC_CONTRACTS) for i in increments)) if pos else 0
        trading_on = engine.trading_enabled
        trades = list(engine.trades)
        candles_recent = list(engine.candles[-10:])
        curr_bar_t = engine.curr_bar_start_t

    float_pnl = engine.get_floating_pnl()
    equity = balance + float_pnl
    realized_pnl = balance - init_bal

    # Determinazione Regime S&R Puro KJ55
    if live_mid and kj:
        if live_mid > kj:
            regime_label = "🟢 SUPPORTO KJ (LONG)"
            regime_col = "#22c55e"
        elif live_mid < kj:
            regime_label = "🔴 RESISTENZA KJ (SHORT)"
            regime_col = "#ef4444"
        else:
            regime_label = "⚪ PIVOT KJ"
            regime_col = "#94a3b8"
    else:
        regime_label = "⏳ CALCOLO KJ55..."
        regime_col = "#cbd5e1"

    # HEADER SUPERIORE
    c_title, c_badges = st.columns([2.9, 1.1])
    with c_title:
        st.markdown("<h3 style='margin: 0; font-size: 1.18rem; font-weight: 700; white-space: nowrap;'>⚡ Hyper-Trading Spot Gold 1€ <span style='background: rgba(56, 189, 248, 0.20); color: #38bdf8; border: 1px solid #38bdf8; padding: 2px 8px; border-radius: 6px; font-size: 0.82rem; font-weight: 800; letter-spacing: 0.04em; margin: 0 4px;'>⏱️ TF 30 SEC</span> <span style='font-size: 0.88rem; color: #94a3b8; font-weight: 500;'>(S&R Puro KJ55)</span></h3>", unsafe_allow_html=True)
        st.markdown("<div style='font-size: 0.74rem; color: #94a3b8; white-space: nowrap; margin-top: 2px;'>S&R Puro KJ 55 (Toll. 3p) • Core 4c (TS a +10p, Lock +6p, Trail 4p) • Incr 2c (TP +2p, Max 4) • Max 12c • Stop Trading auto su TS Hit • Porta 8501</div>", unsafe_allow_html=True)

    with c_badges:
        st.markdown("<div style='display: flex; justify-content: flex-end; gap: 8px; align-items: center; margin-top: 4px; white-space: nowrap;'>", unsafe_allow_html=True)
        is_feed_closed = is_gold_feed_suspended()
        is_trade_frozen = is_gold_trading_suspended()

        if is_conn:
            st.markdown(f"<span class='badge-live' style='background: rgba(34, 197, 94, 0.15); color: #22c55e; border: 1px solid #22c55e;'>🟢 Lightstreamer LIVE ({total_ticks} tick)</span>", unsafe_allow_html=True)
        elif is_feed_closed:
            st.markdown("<span class='badge-live' style='background: rgba(100, 116, 139, 0.2); color: #94a3b8; border: 1px solid #64748b;'>💤 Feed Chiuso (22:45-00:00)</span>", unsafe_allow_html=True)
        else:
            st.markdown("<span class='badge-live' style='background: rgba(239, 68, 68, 0.15); color: #ef4444; border: 1px solid #ef4444;'>🔴 In Connessione...</span>", unsafe_allow_html=True)

        if is_trade_frozen:
            st.markdown("<span class='badge-live' style='background: rgba(234, 179, 8, 0.2); color: #facc15; border: 1px solid #facc15;'>🌙 ORDINI CONGELATI (fino 00:15)</span>", unsafe_allow_html=True)
        elif trading_on:
            st.markdown("<span class='badge-live' style='background: rgba(34, 197, 94, 0.2); color: #4ade80; border: 1px solid #4ade80;'>⚡ TRADING ATTIVO</span>", unsafe_allow_html=True)
        else:
            st.markdown("<span class='badge-live' style='background: rgba(148, 163, 184, 0.2); color: #cbd5e1; border: 1px solid #64748b;'>⏸️ IN PAUSA</span>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<hr style='margin: 10px 0 14px 0; border-color: #334155;' />", unsafe_allow_html=True)

    # Avviso Sospensione Notturna Gold
    if is_trade_frozen:
        st.markdown("""
        <div style='background: rgba(234, 179, 8, 0.12); border: 1px solid #eab308; border-radius: 8px; padding: 10px 16px; margin-bottom: 14px;'>
            <div style='display: flex; align-items: center; gap: 12px;'>
                <span style='font-size: 1.3rem;'>🌙</span>
                <div>
                    <span style='font-size: 0.98rem; font-weight: 700; color: #fde047;'>OPERATIVITÀ ORDINI CONGELATA (22:45 - 00:15)</span>
                    <div style='font-size: 0.83rem; color: #cbd5e1; margin-top: 2px;'>
                        Dalle 00:00 il feed quotazioni e candele è attivo per aggiornare la Kijun 55 in tempo reale. <b>Apertura automatica nuovi ordini alle 00:15</b>.
                    </div>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)

    # Banner Ciclo Trailing Stop Completato
    last_c = engine.last_ts_cycle
    if last_c and not trading_on:
        st.markdown(f"""
        <div style='background: rgba(34, 197, 94, 0.12); border: 1px solid #22c55e; border-radius: 8px; padding: 10px 16px; margin-bottom: 14px;'>
            <div style='display: flex; justify-content: space-between; align-items: center;'>
                <div>
                    <span style='font-size: 1.02rem; font-weight: 700; color: #4ade80;'>🏆 CICLO TRAILING STOP COMPLETATO</span>
                    <div style='font-size: 0.83rem; color: #cbd5e1; margin-top: 3px;'>
                        Chiusura {last_c['direction']} @ {last_c['close_price']:.2f} (+{last_c['core_pips']:.1f} pip Core, Peak: {last_c['peak_price']:.2f}) • <b>P&L Ciclo: +{last_c['total_pnl']:,.2f} €</b> • Bot posto in <b>STOP TRADING</b> per proteggere il profitto.
                    </div>
                </div>
                <div style='font-size: 0.78rem; color: #94a3b8;'>Orario: {last_c['time']}</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

    # 1. KPI PORTAFOGLIO PRINCIPALI
    k1, k2, k3, k4 = st.columns(4)
    with k1:
        col_eq = "#22c55e" if equity >= init_bal else "#ef4444"
        delta_eq = equity - init_bal
        sign_eq = "+" if delta_eq >= 0 else ""
        st.markdown(f"""
        <div class='kpi-card'>
            <div class='kpi-title'>Portafoglio Totale (Equity)</div>
            <div class='kpi-val' style='color: {col_eq};'>{equity:,.2f} €</div>
            <div class='kpi-sub' style='color: {col_eq};'>{sign_eq}{delta_eq:,.2f} € ({sign_eq}{(delta_eq/init_bal)*100:.2f}%)</div>
        </div>
        """, unsafe_allow_html=True)

    with k2:
        col_bal = "#38bdf8"
        col_real = "#22c55e" if realized_pnl >= 0 else "#ef4444"
        sign_real = "+" if realized_pnl >= 0 else ""
        st.markdown(f"""
        <div class='kpi-card'>
            <div class='kpi-title'>Saldo Realizzato</div>
            <div class='kpi-val' style='color: {col_bal};'>{balance:,.2f} €</div>
            <div class='kpi-sub' style='color: {col_real};'>P&L Chiuso: {sign_real}{realized_pnl:,.2f} €</div>
        </div>
        """, unsafe_allow_html=True)

    with k3:
        if pos or increments:
            col_float = "#22c55e" if float_pnl >= 0 else "#ef4444"
            sign_fl = "+" if float_pnl >= 0 else ""
            st.markdown(f"""
            <div class='kpi-card'>
                <div class='kpi-title'>P&L Flottante (Live)</div>
                <div class='kpi-val' style='color: {col_float};'>{sign_fl}{float_pnl:,.2f} €</div>
                <div class='kpi-sub' style='color: #94a3b8;'>Core + {len(increments)} Incrementi</div>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown(f"""
            <div class='kpi-card'>
                <div class='kpi-title'>P&L Flottante (Live)</div>
                <div class='kpi-val' style='color: #94a3b8;'>0.00 €</div>
                <div class='kpi-sub' style='color: #64748b;'>Nessuna posizione aperta</div>
            </div>
            """, unsafe_allow_html=True)

    with k4:
        if pos:
            dir_col = "#22c55e" if pos["direction"] == "LONG" else "#ef4444"
            dir_icon = "🟢" if pos["direction"] == "LONG" else "🔴"
            num_inc = len(increments)
            if pos.get("ts_active"):
                ts_px = pos.get("ts_price", 0.0)
                peak_px = pos.get("peak_price", pos["open_price"])
                sub_text = f"🚀 TRAILING ATTIVO | Stop: {ts_px:.2f} (Peak: {peak_px:.2f}) | Incr: {num_inc}/{MAX_INCREMENTS}"
            else:
                sub_text = f"Core: {CORE_CONTRACTS}c @ {pos['open_price']:.2f} (TS Trigger: +{CORE_TS_TRIGGER_PIPS:.0f} pip) | Incr: {num_inc}/{MAX_INCREMENTS}"

            st.markdown(f"""
            <div class='kpi-card'>
                <div class='kpi-title'>Esposizione a Mercato</div>
                <div class='kpi-val' style='color: {dir_col};'>{dir_icon} {pos['direction']} ({total_contracts}/12 Contr.)</div>
                <div class='kpi-sub' style='color: #cbd5e1;'>{sub_text}</div>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown(f"""
            <div class='kpi-card'>
                <div class='kpi-title'>Esposizione a Mercato</div>
                <div class='kpi-val' style='color: #94a3b8;'>⚪ FLAT (0)</div>
                <div class='kpi-sub' style='color: #64748b;'>In attesa automatica nuovo segnale</div>
            </div>
            """, unsafe_allow_html=True)

    st.markdown("<div style='margin-bottom: 16px;'></div>", unsafe_allow_html=True)

    # 2. INDICATORI DI MERCATO (30S: TK233 & KJ55 & MID LIVE)
    m1, m2, m3, m4 = st.columns([1, 1.8, 1.1, 1.1])
    with m1:
        px_str = f"{live_mid:.2f}" if live_mid else "--"
        bid_ask_str = f"Bid: {live_bid:.2f} | Ask: {live_ask:.2f}" if (live_bid and live_ask) else ""
        st.markdown(f"""
        <div class='kpi-card' style='padding: 10px 14px;'>
            <div class='kpi-title'>Spot Gold 1€ (Mid Live)</div>
            <div style='font-size: 1.30rem; font-weight: 700; color: #22c55e;'>{px_str} €</div>
            <div style='font-size: 0.75rem; color: #94a3b8;'>{bid_ask_str}</div>
        </div>
        """, unsafe_allow_html=True)

    with m2:
        kj_str = f"{kj:.2f}" if kj else "--"
        st.markdown(f"""
        <div class='kpi-card' style='padding: 10px 14px;'>
            <div class='kpi-title'>Livello S&R (30s) • <span style='color: {regime_col}; font-weight: bold;'>{regime_label}</span></div>
            <div style='display: flex; gap: 18px; align-items: baseline; margin-top: 4px;'>
                <div>
                    <span style='font-size: 0.75rem; color: #94a3b8;'>MID LIVE: </span>
                    <span style='font-size: 1.15rem; font-weight: 700; color: #22c55e;'>{px_str} €</span>
                </div>
                <div>
                    <span style='font-size: 0.75rem; color: #94a3b8;'>KJ 55 (S&R): </span>
                    <span style='font-size: 1.15rem; font-weight: 700; color: #FFD700;'>{kj_str}</span>
                </div>
            </div>
            <div style='font-size: 0.73rem; color: #94a3b8; margin-top: 3px;'>S&R Puro: Prezzo > KJ Supporto (Long) • Prezzo < KJ Resistenza (Short)</div>
        </div>
        """, unsafe_allow_html=True)

    with m3:
        margine_usato = total_contracts * 220.0
        st.markdown(f"""
        <div class='kpi-card' style='padding: 10px 14px;'>
            <div class='kpi-title'>Margine Utilizzato</div>
            <div style='font-size: 1.30rem; font-weight: 700; color: #f59e0b;'>{margine_usato:,.2f} €</div>
            <div style='font-size: 0.75rem; color: #cbd5e1;'>220 € / c • {total_contracts} contratti a mercato</div>
        </div>
        """, unsafe_allow_html=True)

    with m4:
        sec_elapsed = 0
        if curr_bar_t:
            sec_elapsed = min(30, int(time.time() - curr_bar_t))
        st.markdown(f"""
        <div class='kpi-card' style='padding: 10px 14px;'>
            <div class='kpi-title'>Tempo Barra Attuale (30s)</div>
            <div style='font-size: 1.30rem; font-weight: 700; color: #cbd5e1;'>{sec_elapsed}s / 30s</div>
            <div style='font-size: 0.75rem; color: #94a3b8;'>Prossima chiusura: {30 - sec_elapsed}s</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<div style='margin-bottom: 14px;'></div>", unsafe_allow_html=True)

    # 3. STATO ACCUMULO BARRE (SE INIZIALE)
    if candles_count < WARMUP_BARS_KJ:
        pct_warmup = min(1.0, candles_count / WARMUP_BARS_KJ)
        st.info(f"⏳ **Accumulo Barre 30s In Corso:** {candles_count} / {WARMUP_BARS_KJ} barre raccolte. Mancano {max(0, WARMUP_BARS_KJ - candles_count)} barre ({max(0, (WARMUP_BARS_KJ - candles_count) * 30 // 60)} min) per il calcolo completo della KJ 55.")
        st.progress(pct_warmup)
    else:
        st.success(f"✅ **Indicatori 30s Pienamente Operativi:** {candles_count} barre storiche disponibili. KJ55 (S&R) calcolata in tempo reale.")

    st.markdown("<div style='margin-bottom: 10px;'></div>", unsafe_allow_html=True)

    # 4. PANNELLO CONTROLLI (AVVIA / STOP / RESET)
    col_btn1, col_btn2, col_btn3 = st.columns([1.5, 1.5, 2])
    with col_btn1:
        st.markdown("<div class='btn-start'>", unsafe_allow_html=True)
        if st.button("🟢 AVVIA TRADING 30S", key="btn_start_30s", disabled=trading_on, use_container_width=True):
            engine.set_trading(True)
            st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

    with col_btn2:
        st.markdown("<div class='btn-stop'>", unsafe_allow_html=True)
        if st.button("🛑 STOP TRADING 30S", key="btn_stop_30s", disabled=not trading_on, use_container_width=True):
            engine.set_trading(False)
            st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

    with col_btn3:
        if st.button("🔄 RESET SALDO A 10.000 €", key="btn_reset_30s", use_container_width=True):
            engine.reset_portfolio()
            st.rerun()

    st.markdown("<div style='margin-bottom: 18px;'></div>", unsafe_allow_html=True)

    # 5. TABELLA STORICO ESEGUITI E LOG OPERAZIONI
    col_t1, col_t2 = st.columns([2, 1.2])

    with col_t1:
        st.markdown("### 📋 Storico Operazioni Chiuse (30s • S&R KJ55)")
        closed_trades = [
            t for t in trades 
            if t.get("close_price") is not None and ("CLOSE" in t.get("action", "") or "TP" in t.get("action", "") or "TS HIT" in t.get("action", ""))
        ]
        if closed_trades:
            rows_html = []
            for t in closed_trades[:30]:
                col_pnl = "#22c55e" if t["pnl"] > 0 else ("#ef4444" if t["pnl"] < 0 else "#94a3b8")
                sign_p = f"+{t['pnl']:.2f}" if t["pnl"] > 0 else f"{t['pnl']:.2f}"
                if "🏆 TS HIT" in t["action"]:
                    action_badge = "<span style='color: #4ade80; font-weight: bold;'>" + t["action"] + "</span>"
                elif "🎯 TP" in t["action"]:
                    action_badge = "<span style='color: #38bdf8; font-weight: bold;'>🎯 " + t["action"] + "</span>"
                elif "CLOSE INC" in t["action"]:
                    action_badge = "<span style='color: #cbd5e1; font-weight: bold;'>⏹️ " + t["action"] + "</span>"
                elif "CLOSE CORE" in t["action"]:
                    action_badge = "<span style='color: #f59e0b; font-weight: bold;'>⏹️ " + t["action"] + "</span>"
                else:
                    action_badge = t["action"]

                close_str = f"{t['close_price']:.2f}" if t.get("close_price") else "--"
                rows_html.append(
                    f"<tr><td>{t['time']}</td><td>{action_badge}</td><td style='white-space: nowrap;'>{t['open_price']:.2f}</td><td style='white-space: nowrap;'>{close_str}</td><td style='color: {col_pnl}; font-weight: bold; white-space: nowrap;'>{sign_p}&nbsp;€</td><td style='font-weight: 600; white-space: nowrap;'>{t['balance']:,.2f}&nbsp;€</td><td style='color: #94a3b8; font-size: 0.78rem;'>{t['reason']}</td></tr>"
                )
            tbl_t = (
                "<table class='table-dark'>"
                "<thead><tr><th>Orario</th><th>Azione</th><th>Prezzo In</th><th>Prezzo Out</th><th style='white-space: nowrap;'>P&L</th><th style='white-space: nowrap;'>Saldo</th><th>Trigger</th></tr></thead>"
                f"<tbody>{''.join(rows_html)}</tbody>"
                "</table>"
            )
            st.markdown(tbl_t, unsafe_allow_html=True)
        else:
            st.info("Nessuna operazione ancora chiusa. Non appena una posizione Core o incremento verrà liquidato (Take Profit, Trailing Stop o Uscita KJ), comparirà qui con il relativo P&L.")

    with col_t2:
        st.markdown("### 💼 Posizioni in Portafoglio")
        if pos:
            dir_pos = pos["direction"]
            dir_col = "#22c55e" if dir_pos == "LONG" else "#ef4444"
            dir_badge = f"<span style='color: {dir_col}; font-weight: 700;'>{'🟢' if dir_pos == 'LONG' else '🔴'} Core {dir_pos}</span>"

            # PnL Core
            if live_mid is not None:
                core_diff = (live_mid - pos["open_price"]) if dir_pos == "LONG" else (pos["open_price"] - live_mid)
                core_pnl_val = round(core_diff * pos.get("contracts", CORE_CONTRACTS) * 1.0, 2)
            else:
                core_pnl_val = 0.0

            col_core_pnl = "#22c55e" if core_pnl_val >= 0 else "#ef4444"
            sign_core = "+" if core_pnl_val >= 0 else ""

            p_rows = [
                f"<tr>"
                f"<td>{dir_badge}</td>"
                f"<td style='text-align: center; font-weight: 700; white-space: nowrap;'>{pos.get('contracts', CORE_CONTRACTS)}c</td>"
                f"<td style='text-align: right; font-weight: 600; white-space: nowrap;'>{pos['open_price']:.2f}</td>"
                f"<td style='text-align: right; color: {col_core_pnl}; font-weight: 700; white-space: nowrap;'>{sign_core}{core_pnl_val:,.2f}&nbsp;€</td>"
                f"</tr>"
            ]

            # Incrementi aperti
            for idx, inc in enumerate(increments, 1):
                if live_mid is not None:
                    inc_diff = (live_mid - inc["open_price"]) if inc["direction"] == "LONG" else (inc["open_price"] - live_mid)
                    inc_pnl_val = round(inc_diff * inc.get("contracts", INC_CONTRACTS) * 1.0, 2)
                else:
                    inc_pnl_val = 0.0

                col_inc_pnl = "#22c55e" if inc_pnl_val >= 0 else "#ef4444"
                sign_inc = "+" if inc_pnl_val >= 0 else ""

                p_rows.append(
                    f"<tr>"
                    f"<td><span style='color: #f59e0b; font-weight: 600; white-space: nowrap;'>➕ Incr #{idx}</span></td>"
                    f"<td style='text-align: center; font-weight: 700; white-space: nowrap;'>{inc.get('contracts', INC_CONTRACTS)}c</td>"
                    f"<td style='text-align: right; font-weight: 600; white-space: nowrap;'>{inc['open_price']:.2f}</td>"
                    f"<td style='text-align: right; color: {col_inc_pnl}; font-weight: 700; white-space: nowrap;'>{sign_inc}{inc_pnl_val:,.2f}&nbsp;€</td>"
                    f"</tr>"
                )

            # Riga Totale
            col_tot_pnl = "#22c55e" if float_pnl >= 0 else "#ef4444"
            sign_tot = "+" if float_pnl >= 0 else ""
            px_live_str = f"{live_mid:.2f}" if live_mid is not None else "--"
            p_rows.append(
                f"<tr style='background: rgba(30, 41, 59, 0.9); border-top: 2px solid #475569; font-weight: 800;'>"
                f"<td style='color: #f8fafc;'>TOTALE</td>"
                f"<td style='text-align: center; color: #38bdf8; white-space: nowrap;'>{total_contracts}c</td>"
                f"<td style='text-align: right; color: #94a3b8; white-space: nowrap;'>Live: {px_live_str}</td>"
                f"<td style='text-align: right; color: {col_tot_pnl}; white-space: nowrap;'>{sign_tot}{float_pnl:,.2f}&nbsp;€</td>"
                f"</tr>"
            )

            tbl_port = (
                "<table class='table-dark'>"
                "<thead><tr><th>Posizione</th><th style='text-align: center; white-space: nowrap;'>Size</th><th style='text-align: right; white-space: nowrap;'>Open</th><th style='text-align: right; white-space: nowrap;'>P&L (€)</th></tr></thead>"
                f"<tbody>{''.join(p_rows)}</tbody>"
                "</table>"
            )
            st.markdown(tbl_port, unsafe_allow_html=True)
        else:
            st.markdown("""
            <div style='background: rgba(30, 41, 59, 0.5); border: 1px dashed #334155; border-radius: 8px; padding: 22px 16px; text-align: center;'>
                <div style='font-size: 1.4rem; margin-bottom: 6px;'>⚪</div>
                <div style='font-weight: 700; color: #e2e8f0; font-size: 0.92rem;'>Nessuna posizione aperta (FLAT)</div>
                <div style='font-size: 0.76rem; color: #94a3b8; margin-top: 4px;'>Size: 0c • In attesa automatica del prossimo segnale</div>
            </div>
            """, unsafe_allow_html=True)

# Render del desk
render_live_desk()
