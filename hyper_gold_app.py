import os
import streamlit as st
import time
from hyper_gold_engine import HyperGoldEngine, CANDLE_SECONDS, WARMUP_BARS_KJ, WARMUP_BARS_TK, CORE_CONTRACTS, CORE_TS_TRIGGER_PIPS, CORE_TS_LOCK_PIPS, CORE_TS_DISTANCE_PIPS, INC_CONTRACTS, MAX_INCREMENTS, INC_TP_PIPS, CANDELA_SEGNALE_OFFSET_PIPS, TK_FILTER_PIPS, DEFAULT_SCALINI_PLAN_30S, is_gold_trading_suspended, is_gold_feed_suspended

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
    h3 { font-size: 1.02rem !important; margin-bottom: 8px !important; }
    .kpi-card {
        background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
        border: 1px solid #334155;
        border-radius: 9px;
        padding: 12px 16px;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.2);
    }
    .kpi-title { font-size: 0.74rem; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 3px; }
    .kpi-val { font-size: 1.45rem; font-weight: 700; }
    .kpi-sub { font-size: 0.70rem; margin-top: 3px; }
    .badge-live {
        display: inline-flex; align-items: center; padding: 2px 7px; border-radius: 5px; font-weight: 600; font-size: 0.70rem; white-space: nowrap;
    }
    .table-dark {
        width: 100%; border-collapse: collapse; font-size: 0.78rem;
    }
    .table-dark th { background-color: #1e293b; color: #94a3b8; padding: 6px 8px; text-align: left; font-size: 0.72rem; }
    .table-dark td { padding: 6px 8px; border-bottom: 1px solid #334155; }

    /* Allineamento e stile proporzionato bottoni di controllo */
    div.stButton > button {
        height: 38px !important;
        min-height: 38px !important;
        font-size: 0.78rem !important;
        font-weight: 700 !important;
        padding: 0 10px !important;
        white-space: nowrap !important;
        border-radius: 6px !important;
        margin: 0 !important;
    }
    .btn-start div.stButton > button {
        background-color: #16a34a !important;
        border: 1px solid #22c55e !important;
        color: #ffffff !important;
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

    .btn-stop div.stButton > button {
        background-color: #dc2626 !important;
        border: 1px solid #ef4444 !important;
        color: #ffffff !important;
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

    .btn-reset div.stButton > button {
        background-color: #334155 !important;
        border: 1px solid #475569 !important;
        color: #e2e8f0 !important;
    }
    .btn-reset div.stButton > button:hover {
        background-color: #475569 !important;
        border-color: #64748b !important;
    }

    div[data-testid="stCheckbox"] label {
        font-size: 0.78rem !important;
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
        tk = engine.tk144
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

    # HEADER SUPERIORE
    c_title, c_badges = st.columns([2.3, 1.7])
    with c_title:
        st.markdown("<h3 style='margin: 0; font-size: 1.08rem; font-weight: 700; white-space: nowrap;'>⚡ Hyper-Trading Spot Gold 1€ <span style='background: rgba(56, 189, 248, 0.20); color: #38bdf8; border: 1px solid #38bdf8; padding: 2px 7px; border-radius: 5px; font-size: 0.76rem; font-weight: 800; letter-spacing: 0.04em; margin: 0 4px;'>⏱️ TF 30 SEC</span> <span style='font-size: 0.80rem; color: #94a3b8; font-weight: 500;'>(TK144 / KJ55)</span></h3>", unsafe_allow_html=True)
        st.markdown("<div style='font-size: 0.70rem; color: #94a3b8; white-space: nowrap; margin-top: 2px;'>Filtro Macro TK 144 • Trigger KJ 55 (Paracadute 2p, Candela Segnale 2p) • Scalini Fast: 4c @ 2p + 4c @ 3p • Core Runner 2c (TS a +10p) • Totale 10c • Porta 8501</div>", unsafe_allow_html=True)

    with c_badges:
        is_feed_closed = is_gold_feed_suspended()
        is_trade_frozen = is_gold_trading_suspended()

        if is_conn:
            badge_ls = f"<span class='badge-live' style='background: rgba(34, 197, 94, 0.15); color: #22c55e; border: 1px solid #22c55e;'>🟢 Lightstreamer LIVE ({total_ticks} tick)</span>"
        elif is_feed_closed:
            badge_ls = "<span class='badge-live' style='background: rgba(100, 116, 139, 0.2); color: #94a3b8; border: 1px solid #64748b;'>💤 Feed Chiuso (22:45-00:00)</span>"
        else:
            badge_ls = "<span class='badge-live' style='background: rgba(239, 68, 68, 0.15); color: #ef4444; border: 1px solid #ef4444;'>🔴 In Connessione...</span>"

        if is_trade_frozen:
            badge_st = "<span class='badge-live' style='background: rgba(234, 179, 8, 0.2); color: #facc15; border: 1px solid #facc15;'>🌙 ORDINI CONGELATI</span>"
        elif trading_on:
            badge_st = "<span class='badge-live' style='background: rgba(34, 197, 94, 0.2); color: #4ade80; border: 1px solid #4ade80;'>⚡ TRADING ATTIVO</span>"
        else:
            badge_st = "<span class='badge-live' style='background: rgba(148, 163, 184, 0.2); color: #cbd5e1; border: 1px solid #64748b;'>⏸️ IN PAUSA</span>"

        st.markdown(f"<div style='display: flex; justify-content: flex-end; gap: 8px; align-items: center; margin-top: 4px; white-space: nowrap;'>{badge_ls}{badge_st}</div>", unsafe_allow_html=True)

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
                <div class='kpi-val' style='color: {dir_col}; font-size: 1.12rem; white-space: nowrap;'>{dir_icon} {pos['direction']} <span style='font-size: 0.92rem; font-weight: 600; opacity: 0.88;'>({total_contracts}/10 Contr.)</span></div>
                <div class='kpi-sub' style='color: #cbd5e1;'>{sub_text}</div>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown(f"""
            <div class='kpi-card'>
                <div class='kpi-title'>Esposizione a Mercato</div>
                <div class='kpi-val' style='color: #94a3b8; font-size: 1.12rem;'>⚪ FLAT (0)</div>
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
            <div style='font-size: 1.18rem; font-weight: 700; color: #22c55e;'>{px_str} €</div>
            <div style='font-size: 0.70rem; color: #94a3b8;'>{bid_ask_str}</div>
        </div>
        """, unsafe_allow_html=True)

    with m2:
        tk_str = f"{tk:.2f}" if tk else "--"
        kj_str = f"{kj:.2f}" if kj else "--"
        if live_mid and tk:
            if live_mid > (tk + TK_FILTER_PIPS):
                regime = "🟢 BULLISH (SOLO LONG)"
                col_reg = "#22c55e"
            elif live_mid < (tk - TK_FILTER_PIPS):
                regime = "🔴 BEARISH (SOLO SHORT)"
                col_reg = "#ef4444"
            else:
                regime = "⚪ ZONA NEUTRA TK (±3p)"
                col_reg = "#f59e0b"
        else:
            regime = "Inizializzazione..."
            col_reg = "#94a3b8"

        st.markdown(f"""
        <div class='kpi-card' style='padding: 8px 14px;'>
            <div class='kpi-title' style='display: flex; justify-content: space-between; align-items: center;'>
                <span>Livelli Chiave (30s)</span>
                <span style='color: {col_reg}; font-weight: 700; font-size: 0.72rem;'>{regime}</span>
            </div>
            <div style='display: flex; justify-content: space-around; align-items: center; margin-top: 5px;'>
                <div style='text-align: center;'>
                    <div style='font-size: 0.65rem; color: #94a3b8; font-weight: 600; text-transform: uppercase;'>MID LIVE</div>
                    <div style='font-size: 1.05rem; font-weight: 800; color: #22c55e;'>{px_str} €</div>
                </div>
                <div style='border-left: 1px solid #334155; height: 26px;'></div>
                <div style='text-align: center;'>
                    <div style='font-size: 0.65rem; color: #94a3b8; font-weight: 600; text-transform: uppercase;'>KJ 55</div>
                    <div style='font-size: 1.05rem; font-weight: 800; color: #FFD700;'>{kj_str}</div>
                </div>
                <div style='border-left: 1px solid #334155; height: 26px;'></div>
                <div style='text-align: center;'>
                    <div style='font-size: 0.65rem; color: #94a3b8; font-weight: 600; text-transform: uppercase;'>TK 144</div>
                    <div style='font-size: 1.05rem; font-weight: 800; color: #f97316;'>{tk_str}</div>
                </div>
            </div>
            <div style='font-size: 0.68rem; color: #94a3b8; margin-top: 5px; text-align: center;'>Filtro Macro TK144 (±3p) • Trigger KJ55 • 🪂 Paracadute KJ: ±2p (Live)</div>
        </div>
        """, unsafe_allow_html=True)

    with m3:
        margine_usato = total_contracts * 220.0
        st.markdown(f"""
        <div class='kpi-card' style='padding: 10px 14px;'>
            <div class='kpi-title'>Margine Utilizzato</div>
            <div style='font-size: 1.18rem; font-weight: 700; color: #f59e0b;'>{margine_usato:,.2f} €</div>
            <div style='font-size: 0.70rem; color: #cbd5e1;'>220 € / c • {total_contracts} contratti a mercato</div>
        </div>
        """, unsafe_allow_html=True)

    with m4:
        sec_elapsed = 0
        if curr_bar_t:
            sec_elapsed = min(30, int(time.time() - curr_bar_t))
        st.markdown(f"""
        <div class='kpi-card' style='padding: 10px 14px;'>
            <div class='kpi-title'>Tempo Barra Attuale (30s)</div>
            <div style='font-size: 1.18rem; font-weight: 700; color: #cbd5e1;'>{sec_elapsed}s / 30s</div>
            <div style='font-size: 0.70rem; color: #94a3b8;'>Prossima chiusura: {30 - sec_elapsed}s</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<div style='margin-bottom: 14px;'></div>", unsafe_allow_html=True)

    # 3. STATO ACCUMULO BARRE (SE INIZIALE)
    if candles_count < WARMUP_BARS_TK:
        pct_warmup = min(1.0, candles_count / WARMUP_BARS_TK)
        st.info(f"⏳ **Accumulo Barre 30s In Corso:** {candles_count} / {WARMUP_BARS_TK} barre raccolte. Mancano {max(0, WARMUP_BARS_TK - candles_count)} barre ({max(0, (WARMUP_BARS_TK - candles_count) * 30 // 60)} min) per il calcolo completo di KJ55 e TK144.")
        st.progress(pct_warmup)
    else:
        st.success(f"✅ **Indicatori 30s Pienamente Operativi:** {candles_count} barre storiche disponibili. KJ55 e TK144 calcolate in tempo reale.")

    st.markdown("<div style='margin-bottom: 10px;'></div>", unsafe_allow_html=True)

    use_core_ts = getattr(engine, "use_core_trailing", False)

    # 4 & 5. SEZIONE CONTROLLI, STORICO E POSIZIONI IN PORTAFOGLIO AFFIANCATE
    col_left, col_right = st.columns([1.60, 1.60])

    with col_left:
        # Configurazione Scalini 30S: Fast Scalping (4c @ 2p + 4c @ 3p + Core Runner 2c [TS a +10p])
        cur_core = int(getattr(engine, "core_size", 2))
        cur_plan = getattr(engine, "scalini_plan", DEFAULT_SCALINI_PLAN_30S)
        tot_plan_c = sum(it["contracts"] for it in cur_plan)
        tot_all_c = cur_core + tot_plan_c

        with st.expander("⚙️ Assetto Scalini 30S: Fast Scalping (Totale 10 Contratti)", expanded=True):
            st.markdown(f"""
            <div style='background: rgba(15, 23, 42, 0.6); border: 1px solid #334155; border-radius: 6px; padding: 10px 12px; font-size: 0.80rem; line-height: 1.6;'>
                <div style='color: #38bdf8; font-weight: 700; margin-bottom: 4px;'>🎯 Piano Ingressi Fast Scalping (De-leveraging Fulmineo):</div>
                <div>• <b>Scalino #1</b>: <span style='color: #f59e0b; font-weight: 600;'>4 contratti</span> @ <b>TP 2 pip</b> (+8.00 €)</div>
                <div>• <b>Scalino #2</b>: <span style='color: #f59e0b; font-weight: 600;'>4 contratti</span> @ <b>TP 3 pip</b> (+12.00 €)</div>
                <div style='margin-top: 4px;'>• <b>Core Runner</b>: <span style='color: #4ade80; font-weight: 600;'>{cur_core} contratti</span> (Trailing Stop attivo a <b>+10 pip</b>, Lock +6 pip, Trail dinamico base 4 pip [+1p ogni 10p])</div>
                <div style='border-top: 1px solid #334155; margin-top: 6px; padding-top: 4px; display: flex; justify-content: space-between;'>
                    <span style='color: #94a3b8;'>Esposizione iniziale: <b style='color: #f8fafc;'>{tot_all_c} contratti</b> (Margine: {tot_all_c*220:,.0f} €)</span>
                    <span style='color: #4ade80; font-weight: 700;'>Incasso Scalini (2p + 3p): +20.00 €</span>
                </div>
            </div>
            """, unsafe_allow_html=True)

        st.markdown("<div style='margin-bottom: 8px;'></div>", unsafe_allow_html=True)

        # Pulsanti AVVIA, STOP e RESET (10k) perfettamente allineati in orizzontale
        c_btn1, c_btn2, c_btn3 = st.columns([1, 1, 1.25])
        with c_btn1:
            st.markdown("<div class='btn-start'>", unsafe_allow_html=True)
            if st.button("🟢 AVVIA", key="btn_start_30s", disabled=trading_on, use_container_width=True):
                engine.set_trading(True)
                st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)

        with c_btn2:
            st.markdown("<div class='btn-stop'>", unsafe_allow_html=True)
            if st.button("🔴 STOP", key="btn_stop_30s", disabled=(not trading_on), use_container_width=True):
                engine.set_trading(False)
                st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)

        with c_btn3:
            st.markdown("<div class='btn-reset'>", unsafe_allow_html=True)
            if st.button("🔄 RESET (10k)", key="btn_reset_30s", use_container_width=True):
                engine.reset_portfolio()
                st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)

        st.markdown("<div style='margin-bottom: 12px;'></div>", unsafe_allow_html=True)
        st.markdown("<h3 style='margin: 0 0 8px 0; font-size: 1.02rem; font-weight: 700;'>📋 Storico Operazioni Chiuse (30s • S&R KJ55)</h3>", unsafe_allow_html=True)
        closed_trades = [
            t for t in trades 
            if t.get("close_price") is not None and ("CLOSE" in t.get("action", "") or "TP" in t.get("action", "") or "TS HIT" in t.get("action", "") or "PARACADUTE" in t.get("action", ""))
        ]
        if closed_trades:
            # Calcolo totali cumulativi sessione per Core e Incrementi
            num_core_closed = 0
            pnl_core_closed = 0.0
            num_inc_closed = 0
            pnl_inc_closed = 0.0

            for t in closed_trades:
                act = t.get("action", "").upper()
                p = float(t.get("pnl", 0.0) or 0.0)
                if "CORE" in act:
                    num_core_closed += 1
                    pnl_core_closed += p
                elif "INC" in act or "TP" in act or "SCALINO" in act:
                    num_inc_closed += 1
                    pnl_inc_closed += p

            tot_pnl_closed = round(pnl_core_closed + pnl_inc_closed, 2)
            col_core_pnl = "#22c55e" if pnl_core_closed >= 0 else "#ef4444"
            sign_core = "+" if pnl_core_closed >= 0 else ""
            col_inc_pnl = "#22c55e" if pnl_inc_closed >= 0 else "#ef4444"
            sign_inc = "+" if pnl_inc_closed >= 0 else ""
            col_tot_pnl = "#22c55e" if tot_pnl_closed >= 0 else "#ef4444"
            sign_tot = "+" if tot_pnl_closed >= 0 else ""

            rows_html = []
            for t in closed_trades[:10]:
                col_pnl = "#22c55e" if t["pnl"] > 0 else ("#ef4444" if t["pnl"] < 0 else "#94a3b8")
                sign_p = f"+{t['pnl']:.2f}" if t["pnl"] > 0 else f"{t['pnl']:.2f}"
                if "PARACADUTE" in t["action"]:
                    action_badge = "<span style='color: #f87171; font-weight: bold;'>" + t["action"] + "</span>"
                elif "🏆 TS HIT" in t["action"]:
                    action_badge = "<span style='color: #4ade80; font-weight: bold;'>" + t["action"] + "</span>"
                elif "🎯 TP" in t["action"]:
                    action_badge = "<span style='color: #38bdf8; font-weight: bold;'>🎯 " + t["action"] + "</span>"
                elif "SCALINO" in t["action"] or "CLOSE INC" in t["action"]:
                    action_badge = "<span style='color: #cbd5e1; font-weight: bold;'>⏹️ " + t["action"] + "</span>"
                elif "CLOSE CORE" in t["action"]:
                    action_badge = "<span style='color: #f59e0b; font-weight: bold;'>⏹️ " + t["action"] + "</span>"
                else:
                    action_badge = t["action"]

                close_str = f"{t['close_price']:.2f}" if t.get("close_price") else "--"
                rows_html.append(
                    f"<tr><td>{t['time']}</td><td>{action_badge}</td><td style='white-space: nowrap;'>{t['open_price']:.2f}</td><td style='white-space: nowrap;'>{close_str}</td><td style='color: {col_pnl}; font-weight: bold; white-space: nowrap;'>{sign_p}&nbsp;€</td><td style='font-weight: 600; white-space: nowrap;'>{t['balance']:,.2f}&nbsp;€</td><td style='color: #94a3b8; font-size: 0.78rem;'>{t['reason']}</td></tr>"
                )

            # Riga Totali Cumulativi Sessione
            summary_html = (
                f"<tr style='background-color: #1e293b; border-top: 2px solid #475569; font-weight: 700; font-size: 0.75rem;'>"
                f"<td colspan='2' style='color: #f8fafc; text-transform: uppercase;'>📊 TOTALI CHIUSI</td>"
                f"<td colspan='2' style='color: #cbd5e1;'>Core: <span style='color: #38bdf8;'>{num_core_closed}</span> (<span style='color: {col_core_pnl};'>{sign_core}{pnl_core_closed:,.2f} €</span>) | Incr: <span style='color: #38bdf8;'>{num_inc_closed}</span> (<span style='color: {col_inc_pnl};'>{sign_inc}{pnl_inc_closed:,.2f} €</span>)</td>"
                f"<td style='color: {col_tot_pnl}; font-size: 0.84rem; white-space: nowrap;'>{sign_tot}{tot_pnl_closed:,.2f}&nbsp;€</td>"
                f"<td colspan='2' style='color: #94a3b8; font-size: 0.70rem;'>P&L complessivo operazioni sessione</td>"
                f"</tr>"
            )
            rows_html.append(summary_html)

            tbl_t = (
                "<table class='table-dark'>"
                "<thead><tr><th>Orario</th><th>Azione</th><th>Prezzo In</th><th>Prezzo Out</th><th style='white-space: nowrap;'>P&L</th><th style='white-space: nowrap;'>Saldo</th><th>Trigger</th></tr></thead>"
                f"<tbody>{''.join(rows_html)}</tbody>"
                "</table>"
            )
            st.markdown(tbl_t, unsafe_allow_html=True)
        else:
            st.info("Nessuna operazione ancora chiusa. Non appena una posizione Core o incremento verrà liquidato (Take Profit, Trailing Stop o Uscita KJ), comparirà qui con il relativo P&L.")

    with col_right:
        sig_act = getattr(engine, "signal_candle_active", False)
        sig_px = getattr(engine, "signal_stop_price", None)
        sig_ref = getattr(engine, "signal_ref_price", None)

        if sig_act and sig_px is not None:
            if sig_ref is None:
                if pos and pos.get("direction") == "LONG":
                    sig_ref = round(sig_px + CANDELA_SEGNALE_OFFSET_PIPS, 2)
                elif pos and pos.get("direction") == "SHORT":
                    sig_ref = round(sig_px - CANDELA_SEGNALE_OFFSET_PIPS, 2)
                else:
                    sig_ref = sig_px
            sign_op = "-" if (pos and pos.get("direction") == "LONG") else "+"
            sig_badge = f"<span style='font-size: 0.94rem; font-weight: 700; color: #f97316; white-space: nowrap;'>Candela Segnale: <span style='font-weight: 800; color: #fb923c;'>{sig_px:.2f}</span> <span style='font-size: 0.88rem; color: #fed7aa; font-weight: 600;'>({sig_ref:.2f} {sign_op} {CANDELA_SEGNALE_OFFSET_PIPS:.0f} pip)</span></span>"
        else:
            sig_badge = "<span style='font-size: 0.94rem; font-weight: 700; color: #64748b; white-space: nowrap;'>---</span>"

        st.markdown(f"""
        <div style='display: flex; justify-content: flex-start; align-items: baseline; gap: 14px; margin: 0 0 8px 0;'>
            <h3 style='margin: 0; font-size: 1.05rem; font-weight: 700; white-space: nowrap;'>💼 Posizioni in Portafoglio</h3>
            {sig_badge}
        </div>
        """, unsafe_allow_html=True)
        if pos:
            dir_pos = pos["direction"]
            dir_col = "#22c55e" if dir_pos == "LONG" else "#ef4444"
            dir_badge = f"<span style='color: {dir_col}; font-weight: 700;'>{'🟢' if dir_pos == 'LONG' else '🔴'} Core {dir_pos}</span> <span style='font-size: 0.82rem; color: #cbd5e1; font-weight: 600;'>({pos['open_price']:.2f})</span>"

            # TS Info Core
            if pos.get("ts_active"):
                ts_stop_px = pos.get("ts_price", 0.0)
                ts_dist = pos.get("ts_distance", CORE_TS_DISTANCE_PIPS)
                ts_cell = f"<span style='color: #4ade80; font-weight: 700; white-space: nowrap;'>TS {ts_stop_px:.2f}</span> <span style='font-size: 0.70rem; color: #86efac; font-weight: 600;'>(Dist: {ts_dist:.0f}p)</span>"
            else:
                ts_target = round((pos["open_price"] + CORE_TS_TRIGGER_PIPS) if dir_pos == "LONG" else (pos["open_price"] - CORE_TS_TRIGGER_PIPS), 2)
                ts_sign = "+" if dir_pos == "LONG" else "-"
                ts_cell = f"<span style='color: #38bdf8; font-weight: 600; white-space: nowrap;'>{ts_target:.2f}</span> <span style='font-size: 0.70rem; color: #94a3b8;'>({ts_sign}{CORE_TS_TRIGGER_PIPS:.0f}p)</span>"

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
                f"<td style='text-align: right; white-space: nowrap;'>{ts_cell}</td>"
                f"<td style='text-align: right; color: {col_core_pnl}; font-weight: 700; white-space: nowrap;'>{sign_core}{core_pnl_val:,.2f}&nbsp;€</td>"
                f"</tr>"
            ]

            # Scalini aperti
            for idx, inc in enumerate(increments, 1):
                if live_mid is not None:
                    inc_diff = (live_mid - inc["open_price"]) if inc["direction"] == "LONG" else (inc["open_price"] - live_mid)
                    inc_pnl_val = round(inc_diff * inc.get("contracts", 1) * 1.0, 2)
                else:
                    inc_pnl_val = 0.0

                col_inc_pnl = "#22c55e" if inc_pnl_val >= 0 else "#ef4444"
                sign_inc = "+" if inc_pnl_val >= 0 else ""
                step_i = inc.get("step_idx", idx)
                tp_dist_p = inc.get("tp_dist_pips", step_i * 2.0)
                tp_val = inc.get("tp_price", 0.0)
                tp_cell = f"<span style='color: #38bdf8; font-weight: 700; white-space: nowrap;'>{tp_val:.2f}</span> <span style='font-size: 0.70rem; color: #fed7aa; font-weight: 600;'>(+{tp_dist_p:.0f}p)</span>"

                p_rows.append(
                    f"<tr>"
                    f"<td><span style='color: #f59e0b; font-weight: 600; white-space: nowrap;'>➕ Scalino #{step_i}</span></td>"
                    f"<td style='text-align: center; font-weight: 700; white-space: nowrap;'>{inc.get('contracts', 1)}c</td>"
                    f"<td style='text-align: right; font-weight: 600; white-space: nowrap;'>{inc['open_price']:.2f}</td>"
                    f"<td style='text-align: right; white-space: nowrap;'>{tp_cell}</td>"
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
                f"<td style='text-align: right; color: #64748b; white-space: nowrap;'>--</td>"
                f"<td style='text-align: right; color: {col_tot_pnl}; white-space: nowrap;'>{sign_tot}{float_pnl:,.2f}&nbsp;€</td>"
                f"</tr>"
            )

            tbl_port = (
                "<table class='table-dark'>"
                "<thead><tr><th>Posizione</th><th style='text-align: center; white-space: nowrap;'>Size</th><th style='text-align: right; white-space: nowrap;'>Open</th><th style='text-align: right; white-space: nowrap;'>TP / TS</th><th style='text-align: right; white-space: nowrap;'>P&L (€)</th></tr></thead>"
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
