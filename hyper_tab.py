import os
import time
import datetime
import streamlit as st
import streamlit.components.v1 as components

from hyper_gold_m5_engine import (
    HyperGoldM5Engine, CANDLE_SECONDS as CANDLE_SECONDS_5M, WARMUP_BARS_KJ as WARMUP_BARS_KJ_5M,
    WARMUP_BARS_TK as WARMUP_BARS_TK_5M, CORE_CONTRACTS as CORE_CONTRACTS_5M,
    CORE_TS_TRIGGER_PIPS as CORE_TS_TRIGGER_PIPS_5M, INC_CONTRACTS as INC_CONTRACTS_5M,
    MAX_INCREMENTS as MAX_INCREMENTS_5M, INC_TP_PIPS as INC_TP_PIPS_5M,
    CANDELA_SEGNALE_OFFSET_PIPS as CANDELA_SEGNALE_OFFSET_PIPS_5M,
    TK_FILTER_PIPS as TK_FILTER_PIPS_5M,
    is_gold_trading_suspended, is_gold_feed_suspended
)
from hyper_us500_m5_engine import (
    HyperUS500M5Engine, is_us500_trading_suspended, is_us500_feed_suspended, EPIC_US500
)
import json
from hyper_order_manager import HyperOrderManager

_sidebar_cache = {"time": 0.0, "conto": None, "data": {}}

def get_sidebar_account_data(conto_selezionato):
    """Recupera e sincronizza i dati patrimoniali (Capitale, Margine, Disponibile, Drawdown)
    esattamente come mostrati nella Sidebar della Dashboard, con cache e aggiornamento ogni 15 secondi."""
    now = time.time()
    if _sidebar_cache["conto"] == conto_selezionato and (now - _sidebar_cache["time"]) < 15.0 and _sidebar_cache["data"]:
        return _sidebar_cache["data"]

    candidates = []
    if conto_selezionato:
        candidates.append(os.path.join(conto_selezionato, "stato_sistema.json"))
    candidates.append("stato_sistema.json")

    saldo_fl, disp_fl, marg_fl, dd_fl = 0.0, 0.0, 0.0, 0.0
    for p in candidates:
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    d = json.load(f)
                    saldo_fl = float(d.get("saldo", 0.0) or 0.0)
                    disp_fl = float(d.get("disponibile", 0.0) or 0.0)
                    marg_fl = float(d.get("margine", 0.0) or 0.0)
                    dd_fl = float(d.get("drawdown", 0.0) or 0.0)
                    break
            except Exception:
                pass

    def _fmt(v):
        return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    data = {
        "saldo_float": saldo_fl,
        "disp_float": disp_fl,
        "marg_float": marg_fl,
        "dd_float": dd_fl,
        "saldo_str": _fmt(saldo_fl),
        "disp_str": _fmt(disp_fl),
        "marg_str": _fmt(marg_fl),
        "dd_str": _fmt(dd_fl)
    }
    _sidebar_cache["time"] = now
    _sidebar_cache["conto"] = conto_selezionato
    _sidebar_cache["data"] = data
    return data

def inject_hyper_css():
    st.markdown("""
    <style>
        .kpi-card-hyper {
            background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
            border: 1px solid #334155;
            border-radius: 9px;
            padding: 12px 16px;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.2);
        }
        .kpi-title-hyper { font-size: 0.74rem; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 3px; }
        .kpi-val-hyper { font-size: 1.45rem; font-weight: 700; }
        .kpi-sub-hyper { font-size: 0.70rem; margin-top: 3px; }
        .badge-live-hyper {
            display: inline-flex; align-items: center; padding: 2px 7px; border-radius: 5px; font-weight: 600; font-size: 0.70rem; white-space: nowrap;
        }
        .table-dark-hyper {
            width: 100%; border-collapse: collapse; font-size: 0.78rem;
        }
        .table-dark-hyper th { background-color: #1e293b; color: #94a3b8; padding: 6px 8px; text-align: left; font-size: 0.72rem; }
        .table-dark-hyper td { padding: 6px 8px; border-bottom: 1px solid #334155; }

        /* Bottoni personalizzati proporzionati */
        .btn-start-hyper div.stButton > button {
            background-color: #16a34a !important;
            border: 1px solid #22c55e !important;
            color: #ffffff !important;
            height: 38px !important;
            font-weight: 700 !important;
            border-radius: 6px !important;
        }
        .btn-start-hyper div.stButton > button:hover:not(:disabled) {
            background-color: #15803d !important;
            border-color: #4ade80 !important;
            box-shadow: 0 0 10px rgba(34, 197, 94, 0.45) !important;
        }
        .btn-stop-hyper div.stButton > button {
            background-color: #dc2626 !important;
            border: 1px solid #ef4444 !important;
            color: #ffffff !important;
            height: 38px !important;
            font-weight: 700 !important;
            border-radius: 6px !important;
        }
        .btn-stop-hyper div.stButton > button:hover:not(:disabled) {
            background-color: #b91c1c !important;
            border-color: #f87171 !important;
            box-shadow: 0 0 10px rgba(239, 68, 68, 0.45) !important;
        }
        .btn-reset-hyper div.stButton > button {
            background-color: #334155 !important;
            border: 1px solid #64748b !important;
            color: #cbd5e1 !important;
            height: 38px !important;
            font-weight: 700 !important;
            border-radius: 6px !important;
        }
        .btn-reset-hyper div.stButton > button:hover:not(:disabled) {
            background-color: #475569 !important;
            border-color: #94a3b8 !important;
            color: #ffffff !important;
        }
        .btn-azzera-hyper div.stButton > button {
            white-space: nowrap !important;
            font-size: 0.82rem !important;
            padding: 4px 12px !important;
            height: 34px !important;
            font-weight: 600 !important;
            display: inline-flex !important;
            align-items: center !important;
            justify-content: center !important;
            width: 100% !important;
        }
        .btn-azzera-hyper div.stButton > button p {
            white-space: nowrap !important;
            word-break: keep-all !important;
            margin: 0 !important;
        }
        /* Forza la visibilità di tutte le sottotab di Hyper (5m) */
        div[data-testid="stTabsContent"] div[data-testid="stTabs"] div[role="tablist"] > button,
        div[data-testid="stTabsContent"] div[role="tablist"] > button {
            display: inline-flex !important;
            visibility: visible !important;
            opacity: 1 !important;
        }

        /* ANTI-FLICKER: Elimina il lampeggio/dissolvenza di Streamlit durante i refresh dei frammenti */
        div[data-testid="stFragment"],
        div[data-testid="stFragment"] > div,
        div[data-stale="true"],
        div[data-stale="true"] * {
            opacity: 1 !important;
            filter: none !important;
            transition: none !important;
            animation: none !important;
        }
        /* Nasconde il widget rotante di caricamento in alto a destra */
        div[data-testid="stStatusWidget"] {
            display: none !important;
            visibility: hidden !important;
        }

        /* Expander compatto e proporzionato in Hyper */
        div[data-testid="stTabsContent"] details[data-testid="stExpander"] {
            border: 1px solid #334155 !important;
            border-radius: 6px !important;
            background: rgba(15, 23, 42, 0.45) !important;
            margin-bottom: 4px !important;
        }
        div[data-testid="stTabsContent"] details[data-testid="stExpander"] summary {
            padding: 3px 8px !important;
            min-height: 28px !important;
        }
        div[data-testid="stTabsContent"] details[data-testid="stExpander"] summary p {
            font-size: 0.74rem !important;
            font-weight: 600 !important;
            color: #94a3b8 !important;
            margin: 0 !important;
        }
        div[data-testid="stTabsContent"] details[data-testid="stExpander"] summary svg {
            width: 13px !important;
            height: 13px !important;
        }
        div[data-testid="stTabsContent"] details[data-testid="stExpander"] div[data-testid="stExpanderDetails"] {
            padding: 4px 8px 6px 8px !important;
        }
    </style>
    """, unsafe_allow_html=True)


@st.fragment(run_every=2)
def render_hyper_5m(conto_selezionato="DANY_DEMO", is_other_active=False, is_us500=False, **kwargs):
    conto_attivo = st.session_state.get("conto_selezionato") or conto_selezionato or "DANY_DEMO"
    nome_clean = conto_attivo.replace("_DEMO", "").replace("_REALE", "")

    if is_us500:
        engine = HyperUS500M5Engine.get_instance(account_dir=conto_attivo)
        is_feed_closed = is_us500_feed_suspended()
        is_trade_frozen = is_us500_trading_suspended()
        instr_name = "US 500 Cash 1€"
        unit_lbl = "pt"
        core_c = 4
        inc_c = 2
        max_inc = 2
        inc_tp = 10.0
        parachute_p = 10.0
        ts_trig = 15.0
        ts_lock = 10.0
        ts_stp = 4.0
        margin_per_c = 400.0
        sig_offset = 5.0
        epic_filter = "IX.D.SPTRD.IBE.IP"
        btn_sfx = f"us500_{conto_attivo}"
    else:
        engine = HyperGoldM5Engine.get_instance(account_dir=conto_attivo)
        is_feed_closed = is_gold_feed_suspended()
        is_trade_frozen = is_gold_trading_suspended()
        instr_name = "Spot Gold 1€"
        unit_lbl = "p"
        core_c = CORE_CONTRACTS_5M
        inc_c = INC_CONTRACTS_5M
        max_inc = MAX_INCREMENTS_5M
        inc_tp = INC_TP_PIPS_5M
        parachute_p = 6.0
        ts_trig = CORE_TS_TRIGGER_PIPS_5M
        ts_lock = 6.0
        ts_stp = 2.0
        margin_per_c = 220.0
        sig_offset = CANDELA_SEGNALE_OFFSET_PIPS_5M
        epic_filter = "CS.D.CFDGOLD.CFD.IP"
        btn_sfx = f"gold_{conto_attivo}"

    with engine.lock:
        is_conn = engine.ls_connected
        live_mid = engine.live_mid
        live_bid = engine.live_bid
        live_ask = engine.live_ask
        total_ticks = engine.total_ticks
        candles_count = len(engine.candles)
        kj = engine.kj55
        pos = engine.position
        increments = list(engine.increments)
        total_contracts = (pos.get("contracts", core_c) + sum(i.get("contracts", inc_c) for i in increments)) if pos else 0
        trading_on = engine.trading_enabled
        trades = list(engine.trades)
        curr_bar_t = engine.curr_bar_start_t

    # Dati patrimoniali sincronizzati con la Sidebar ogni 15s
    acc_data = get_sidebar_account_data(conto_attivo)
    float_pnl = engine.get_floating_pnl()

    saldo_fl = acc_data["saldo_float"]
    equity_fl = saldo_fl + float_pnl

    val_capitale = acc_data["saldo_str"]
    val_disp = acc_data["disp_str"]
    val_margine = acc_data["marg_str"]
    val_equity = f"{equity_fl:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    # P&L e Storico Eseguiti Reali IG per 5M (Fonte di verità assoluta)
    order_mgr = HyperOrderManager.get_instance(conto_attivo)
    history_5m = order_mgr.get_trades_history(tf="5M", epic=epic_filter)
    session_realized_pnl = sum(float(t.get("pnl_eur", 0.0) or 0.0) for t in history_5m)
    num_closed = len(history_5m)

    # Intestazione e Badge di Stato
    c_title, c_badges = st.columns([2.3, 1.7])
    with c_title:
        st.markdown(f"<h3 style='margin: 0; font-size: 1.05rem; font-weight: 700; white-space: nowrap;'>⚡ Hyper {instr_name} <span style='background: rgba(245, 158, 11, 0.20); color: #f59e0b; border: 1px solid #f59e0b; padding: 2px 7px; border-radius: 5px; font-size: 0.76rem; font-weight: 800; letter-spacing: 0.04em; margin: 0 4px;'>📊 TF 5 MIN</span> <span style='font-size: 0.80rem; color: #94a3b8;'>({conto_attivo})</span></h3>", unsafe_allow_html=True)
        st.markdown(f"<div style='font-size: 0.70rem; color: #94a3b8; white-space: nowrap; margin-top: 2px;'>Supporto & Resistenza Puro KJ 55 • Core {core_c}c • Max {max_inc} Incrementi Pullback (TP +{inc_tp:.0f}{unit_lbl}) • Trailing Stop Core • 🪂 ±{parachute_p:.0f}{unit_lbl}</div>", unsafe_allow_html=True)

    with c_badges:
        if is_conn:
            badge_ls = f"<span class='badge-live-hyper' style='background: rgba(34, 197, 94, 0.15); color: #22c55e; border: 1px solid #22c55e;'>🟢 Lightstreamer LIVE ({total_ticks} tick)</span>"
        elif is_feed_closed:
            badge_ls = "<span class='badge-live-hyper' style='background: rgba(100, 116, 139, 0.2); color: #94a3b8; border: 1px solid #64748b;'>💤 Feed Chiuso</span>"
        else:
            badge_ls = "<span class='badge-live-hyper' style='background: rgba(239, 68, 68, 0.15); color: #ef4444; border: 1px solid #ef4444;'>🔴 In Connessione...</span>"

        if is_trade_frozen:
            badge_st = "<span class='badge-live-hyper' style='background: rgba(234, 179, 8, 0.2); color: #facc15; border: 1px solid #facc15;'>🌙 ORDINI CONGELATI</span>"
        elif trading_on:
            badge_st = "<span class='badge-live-hyper' style='background: rgba(34, 197, 94, 0.2); color: #4ade80; border: 1px solid #4ade80;'>⚡ TRADING ATTIVO</span>"
        else:
            badge_st = "<span class='badge-live-hyper' style='background: rgba(148, 163, 184, 0.2); color: #cbd5e1; border: 1px solid #64748b;'>⏸️ IN PAUSA</span>"

        st.markdown(f"<div style='display: flex; justify-content: flex-end; gap: 8px; align-items: center; margin-top: 4px; white-space: nowrap;'>{badge_ls}{badge_st}</div>", unsafe_allow_html=True)

    st.markdown("<hr style='margin: 8px 0 12px 0; border-color: #334155;' />", unsafe_allow_html=True)

    # 1. KPI PORTAFOGLIO PRINCIPALI
    k1, k2, k3, k4 = st.columns(4)
    with k1:
        st.markdown(f"""
        <div class='kpi-card-hyper'>
            <div class='kpi-title-hyper'>Capitale Conto ({nome_clean})</div>
            <div class='kpi-val-hyper' style='color: #FFD700;'>{val_capitale} €</div>
            <div class='kpi-sub-hyper' style='color: #94a3b8;'>Disponibile: <b style='color: #4ade80;'>{val_disp} €</b></div>
        </div>
        """, unsafe_allow_html=True)

    with k2:
        col_real = "#22c55e" if session_realized_pnl >= 0 else ("#ef4444" if session_realized_pnl < 0 else "#94a3b8")
        sign_real = "+" if session_realized_pnl > 0 else ""
        pnl_str = f"{session_realized_pnl:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        st.markdown(f"""
        <div class='kpi-card-hyper'>
            <div class='kpi-title-hyper'>P&L Sessione Hyper (5m)</div>
            <div class='kpi-val-hyper' style='color: {col_real};'>{sign_real}{pnl_str} €</div>
            <div class='kpi-sub-hyper' style='color: #cbd5e1;'>{num_closed} operazioni concluse</div>
        </div>
        """, unsafe_allow_html=True)

    with k3:
        if pos or increments:
            col_float = "#22c55e" if float_pnl >= 0 else "#ef4444"
            sign_fl = "+" if float_pnl >= 0 else ""
            st.markdown(f"""
            <div class='kpi-card-hyper'>
                <div class='kpi-title-hyper'>P&L Flottante (Live)</div>
                <div class='kpi-val-hyper' style='color: {col_float};'>{sign_fl}{float_pnl:,.2f} €</div>
                <div class='kpi-sub-hyper' style='color: #94a3b8;'>Core + {len(increments)} Incrementi</div>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown(f"""
            <div class='kpi-card-hyper'>
                <div class='kpi-title-hyper'>P&L Flottante (Live)</div>
                <div class='kpi-val-hyper' style='color: #94a3b8;'>0.00 €</div>
                <div class='kpi-sub-hyper' style='color: #64748b;'>Nessuna posizione aperta</div>
            </div>
            """, unsafe_allow_html=True)

    with k4:
        if pos:
            dir_col = "#22c55e" if pos["direction"] == "LONG" else "#ef4444"
            dir_icon = "🟢" if pos["direction"] == "LONG" else "🔴"
            num_inc = len(increments)
            sub_text = f"Core: {core_c}c @ {pos['open_price']:.2f} | Incr: {num_inc}/{max_inc}"
            st.markdown(f"""
            <div class='kpi-card-hyper'>
                <div class='kpi-title-hyper'>Esposizione a Mercato</div>
                <div class='kpi-val-hyper' style='color: {dir_col}; font-size: 1.12rem; white-space: nowrap;'>{dir_icon} {pos['direction']} <span style='font-size: 0.92rem; font-weight: 600; opacity: 0.88;'>({total_contracts} Contr.)</span></div>
                <div class='kpi-sub-hyper' style='color: #cbd5e1;'>{sub_text}</div>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown(f"""
            <div class='kpi-card-hyper'>
                <div class='kpi-title-hyper'>Esposizione a Mercato</div>
                <div class='kpi-val-hyper' style='color: #94a3b8; font-size: 1.12rem;'>⚪ FLAT (0)</div>
                <div class='kpi-sub-hyper' style='color: #64748b;'>In attesa automatica nuovo segnale</div>
            </div>
            """, unsafe_allow_html=True)

    st.markdown("<div style='margin-bottom: 12px;'></div>", unsafe_allow_html=True)

    # 2. INDICATORI DI MERCATO (5M: S&R PURO KJ55)
    m1, m2, m3 = st.columns([2.0, 1.0, 1.0])
    with m1:
        px_str = f"{live_mid:.2f}" if live_mid else "--"
        kj_str = f"{kj:.2f}" if kj else "--"
        dist_str = f"{abs(live_mid - kj):.2f} {unit_lbl}" if (live_mid and kj) else "--"
        if live_mid and kj:
            if live_mid > kj:
                regime = "🟢 SOPRA KJ55 (BULLISH)"
                col_reg = "#22c55e"
            elif live_mid < kj:
                regime = "🔴 SOTTO KJ55 (BEARISH)"
                col_reg = "#ef4444"
            else:
                regime = "⚪ A CONTATTO CON KJ55"
                col_reg = "#f59e0b"
        else:
            regime = "Inizializzazione..."
            col_reg = "#94a3b8"

        st.markdown(f"""
        <div class='kpi-card-hyper' style='padding: 8px 14px;'>
            <div class='kpi-title-hyper' style='display: flex; justify-content: space-between; align-items: center;'>
                <span style='color: #f59e0b; font-weight: 800;'>📊 SUPPORTO & RESISTENZA PURO (5M)</span>
                <span style='color: {col_reg}; font-weight: 700; font-size: 0.72rem;'>{regime}</span>
            </div>
            <div style='display: flex; justify-content: space-around; align-items: center; margin-top: 5px;'>
                <div style='text-align: center;'>
                    <div style='font-size: 0.65rem; color: #94a3b8; font-weight: 600; text-transform: uppercase;'>MID LIVE</div>
                    <div style='font-size: 1.05rem; font-weight: 800; color: #22c55e;'>{px_str} €</div>
                </div>
                <div style='border-left: 1px solid #334155; height: 26px;'></div>
                <div style='text-align: center;'>
                    <div style='font-size: 0.65rem; color: #94a3b8; font-weight: 600; text-transform: uppercase;'>KJ 55 (S&R)</div>
                    <div style='font-size: 1.05rem; font-weight: 800; color: #FFD700;'>{kj_str}</div>
                </div>
                <div style='border-left: 1px solid #334155; height: 26px;'></div>
                <div style='text-align: center;'>
                    <div style='font-size: 0.65rem; color: #94a3b8; font-weight: 600; text-transform: uppercase;'>DISTANZA KJ</div>
                    <div style='font-size: 1.05rem; font-weight: 800; color: #38bdf8;'>{dist_str}</div>
                </div>
            </div>
            <div style='font-size: 0.66rem; color: #94a3b8; margin-top: 5px; text-align: center; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;'>S&R Puro KJ55 • Trailing Stop Core • 🪂 Paracadute KJ: ±{parachute_p:.0f}{unit_lbl} • Incr Pullback ≤5{unit_lbl} (TP +{inc_tp:.0f}{unit_lbl})</div>
        </div>
        """, unsafe_allow_html=True)

    with m2:
        hyper_margine = total_contracts * margin_per_c
        st.markdown(f"""
        <div class='kpi-card-hyper' style='padding: 10px 14px;'>
            <div class='kpi-title-hyper'>Margine ({nome_clean})</div>
            <div style='font-size: 1.18rem; font-weight: 700; color: #f59e0b;'>{val_margine} €</div>
            <div style='font-size: 0.70rem; color: #cbd5e1;'>Hyper: {hyper_margine:,.0f} €</div>
        </div>
        """, unsafe_allow_html=True)

    with m3:
        sec_elapsed = 0
        if curr_bar_t:
            sec_elapsed = min(300, int(time.time() - curr_bar_t))
        sec_left = max(0, 300 - sec_elapsed)
        sec_left_str = f"{sec_left // 60:02d}:{sec_left % 60:02d}"
        st.markdown(f"""
        <div class='kpi-card-hyper' style='padding: 10px 14px; text-align: center;'>
            <div class='kpi-title-hyper'>Tempo Barra (M5)</div>
            <div style='font-size: 1.30rem; font-weight: 800; font-family: monospace; color: #38bdf8; margin-top: 2px;'>{sec_left_str}</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<div style='margin-bottom: 12px;'></div>", unsafe_allow_html=True)

    # 3. SEZIONE CONTROLLI E OPERAZIONI
    col_left, col_right = st.columns([1.15, 1.85])

    with col_left:
        with st.expander(f"⚙️ Assetto M5: S&R Puro KJ55 (Core {core_c}c + Incr {inc_c}c)", expanded=False):
            st.markdown(f"""
            <div style='background: rgba(15, 23, 42, 0.6); border: 1px solid #334155; border-radius: 5px; padding: 6px 10px; font-size: 0.73rem; line-height: 1.45;'>
                <div style='color: #f59e0b; font-weight: 700; margin-bottom: 3px; font-size: 0.75rem;'>🎯 Piano Ingressi M5 S&R Puro KJ55:</div>
                <div>• <b>Regime</b>: LONG se Chiusura > KJ55 | SHORT se Chiusura < KJ55</div>
                <div>• <b>Ingresso Core</b>: <span style='color: #4ade80; font-weight: 600;'>{core_c}c</span> su stacco Prezzo - KJ >= 2 {unit_lbl}</div>
                <div>• <b>Incrementi Pullback</b>: fino a <b>{max_inc}</b> da <span style='color: #f59e0b; font-weight: 600;'>{inc_c}c</span> (distanza <= 5{unit_lbl} da KJ, TP +{inc_tp:.0f}{unit_lbl})</div>
                <div>• <b>Trailing Stop Core</b>: Trigger +{ts_trig:.0f}{unit_lbl}, Lock +{ts_lock:.0f}{unit_lbl}, Step {ts_stp:.0f}{unit_lbl}</div>
                <div style='border-top: 1px solid #334155; margin-top: 4px; padding-top: 3px;'>
                    <span style='color: #94a3b8;'>Paracadute KJ55: <b>±{parachute_p:.0f} {unit_lbl}</b> • Candela Segnale: <b>±{sig_offset:.0f} {unit_lbl}</b></span>
                </div>
            </div>
            """, unsafe_allow_html=True)

        st.markdown("<div style='margin-bottom: 8px;'></div>", unsafe_allow_html=True)

        c_btn1, c_btn2 = st.columns([1, 1])
        dis_start = trading_on
        with c_btn1:
            st.markdown("<div class='btn-start-hyper'>", unsafe_allow_html=True)
            if st.button("🟢 AVVIA 5M", key=f"btn_start_m5_{btn_sfx}", disabled=dis_start, use_container_width=True):
                st.session_state["hyper_target_subtab"] = "5m"
                engine.set_trading(True)
                st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)
            st.markdown("<div class='btn-azzera-hyper' style='margin-top: 6px;'>", unsafe_allow_html=True)
            if st.button("🔄 Azzera Sessione", key=f"btn_clr_trades_m5_{btn_sfx}", help="Azzera lo storico delle operazioni chiuse e il P&L di sessione", use_container_width=True):
                st.session_state["hyper_target_subtab"] = "5m"
                order_mgr.clear_trades_history(tf="5M", epic=epic_filter)
                engine.clear_session_trades()
                st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)

        with c_btn2:
            st.markdown("<div class='btn-stop-hyper'>", unsafe_allow_html=True)
            if st.button("🔴 STOP 5M", key=f"btn_stop_m5_{btn_sfx}", disabled=(not trading_on), use_container_width=True):
                st.session_state["hyper_target_subtab"] = "5m"
                engine.set_trading(False)
                st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)

        st.markdown("<h4 style='margin: 12px 0 8px 0; font-size: 0.90rem; font-weight: 700;'>📋 Storico Operazioni (M5)</h4>", unsafe_allow_html=True)
        closed_trades = history_5m
        if closed_trades:
            num_core_closed = 0
            pnl_core_closed = 0.0
            num_inc_closed = 0
            pnl_inc_closed = 0.0

            for t in closed_trades:
                lbl = t.get("label", "").upper()
                p = float(t.get("pnl_eur", 0.0) or 0.0)
                if "CORE" in lbl or "M5" in lbl or "5M" in lbl:
                    num_core_closed += 1
                    pnl_core_closed += p
                else:
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
            for t in closed_trades[:12]:
                pnl_val = float(t.get("pnl_eur", 0.0) or 0.0)
                col_pnl = "#22c55e" if pnl_val > 0 else ("#ef4444" if pnl_val < 0 else "#94a3b8")
                sign_p = f"+{pnl_val:.2f}" if pnl_val > 0 else f"{pnl_val:.2f}"
                lbl = t.get("label", "Trade")
                rsn = t.get("reason", "")

                if "PARACADUTE" in rsn.upper():
                    action_badge = f"<span style='color: #f87171; font-weight: bold;'>🪂 {lbl}</span>"
                elif "TP" in rsn.upper() or "TP" in lbl.upper():
                    action_badge = f"<span style='color: #38bdf8; font-weight: bold;'>🎯 {lbl}</span>"
                elif "TRAILING" in rsn.upper() or "TS" in rsn.upper():
                    action_badge = f"<span style='color: #4ade80; font-weight: bold;'>🏆 TS {lbl}</span>"
                else:
                    action_badge = f"<span style='color: #cbd5e1; font-weight: bold;'>⏹️ {lbl}</span>"

                t_str = t.get("time_close", "").split(" ")[-1] if " " in t.get("time_close", "") else t.get("time_close", "")
                rows_html.append(
                    f"<tr><td style='white-space: nowrap;'>{t_str}</td><td style='white-space: nowrap;'>{action_badge}</td><td style='white-space: nowrap;'>{t['open_price']:.2f}</td><td style='white-space: nowrap;'>{t['close_price']:.2f}</td><td style='color: {col_pnl}; font-weight: bold; white-space: nowrap;'>{sign_p}&nbsp;€</td><td style='font-family: monospace; font-size: 0.74rem; color: #94a3b8; white-space: nowrap;'>{t.get('deal_id', '--')}</td><td style='color: #cbd5e1; font-size: 0.78rem;'>{rsn}</td></tr>"
                )

            summary_html = (
                f"<tr style='background-color: #1e293b; border-top: 2px solid #475569; font-weight: 700; font-size: 0.75rem;'>"
                f"<td colspan='2' style='color: #f8fafc; text-transform: uppercase;'>📊 TOTALI CHIUSI (5M)</td>"
                f"<td colspan='2' style='color: #cbd5e1;'>Core: <span style='color: #38bdf8;'>{num_core_closed}</span> (<span style='color: {col_core_pnl};'>{sign_core}{pnl_core_closed:,.2f} €</span>) | Incr: <span style='color: #38bdf8;'>{num_inc_closed}</span> (<span style='color: {col_inc_pnl};'>{sign_inc}{pnl_inc_closed:,.2f} €</span>)</td>"
                f"<td style='color: {col_tot_pnl}; font-size: 0.84rem; white-space: nowrap;'>{sign_tot}{tot_pnl_closed:,.2f}&nbsp;€</td>"
                f"<td colspan='2' style='color: #94a3b8; font-size: 0.70rem;'>P&L complessivo eseguiti reali IG</td>"
                f"</tr>"
            )
            rows_html.append(summary_html)

            st.markdown(f"""
            <table class='table-dark-hyper' style='width: 100%;'>
                <thead>
                    <tr><th style='width: 9%; white-space: nowrap;'>Orario</th><th style='width: 14%; white-space: nowrap;'>Posizione</th><th style='width: 9%; white-space: nowrap;'>Prezzo In</th><th style='width: 9%; white-space: nowrap;'>Prezzo Out</th><th style='width: 9%; white-space: nowrap;'>P&L</th><th style='width: 11%; white-space: nowrap;'>Deal ID</th><th style='width: 39%;'>Trigger Chiusura</th></tr>
                </thead>
                <tbody>{''.join(rows_html)}</tbody>
            </table>
            """, unsafe_allow_html=True)
        else:
            st.info("Nessuna operazione ancora chiusa in sessione 5m.")

    with col_right:
        sig_act = getattr(engine, "signal_candle_active", False)
        sig_px = getattr(engine, "signal_stop_price", None)
        sig_ref = getattr(engine, "signal_ref_price", None)

        if sig_act and sig_px is not None:
            if sig_ref is None:
                if pos and pos.get("direction") == "LONG":
                    sig_ref = round(sig_px + sig_offset, 2)
                elif pos and pos.get("direction") == "SHORT":
                    sig_ref = round(sig_px - sig_offset, 2)
                else:
                    sig_ref = sig_px
            sign_op = "-" if (pos and pos.get("direction") == "LONG") else "+"
            sig_badge = f"<span style='font-size: 0.90rem; font-weight: 700; color: #f97316; white-space: nowrap;'>Candela Segnale: <span style='font-weight: 800; color: #fb923c;'>{sig_px:.2f}</span> <span style='font-size: 0.82rem; color: #fed7aa;'>({sig_ref:.2f} {sign_op} {sig_offset:.0f}{unit_lbl})</span></span>"
        else:
            sig_badge = "<span style='font-size: 0.90rem; font-weight: 700; color: #64748b; white-space: nowrap;'>---</span>"

        st.markdown(f"""
        <div style='display: flex; justify-content: space-between; align-items: baseline; margin: 0 0 8px 0;'>
            <h4 style='margin: 0; font-size: 0.95rem; font-weight: 700;'>💼 Posizioni in Portafoglio (M5)</h4>
            {sig_badge}
        </div>
        """, unsafe_allow_html=True)

        if pos:
            dir_pos = pos["direction"]
            dir_col = "#22c55e" if dir_pos == "LONG" else "#ef4444"
            dir_badge = f"<span style='color: {dir_col}; font-weight: 700;'>{'🟢' if dir_pos == 'LONG' else '🔴'} Core {dir_pos}</span> <span style='font-size: 0.82rem; color: #cbd5e1;'>({pos['open_price']:.2f})</span>"

            ts_target = round((pos["open_price"] + ts_trig) if dir_pos == "LONG" else (pos["open_price"] - ts_trig), 2)
            ts_sign = "+" if dir_pos == "LONG" else "-"
            ts_cell = f"<span style='color: #38bdf8; font-weight: 600; white-space: nowrap;'>{ts_target:.2f}</span> <span style='font-size: 0.70rem; color: #94a3b8;'>({ts_sign}{ts_trig:.0f}{unit_lbl})</span>"

            if live_mid is not None:
                core_diff = (live_mid - pos["open_price"]) if dir_pos == "LONG" else (pos["open_price"] - live_mid)
                core_pnl_val = round(core_diff * pos.get("contracts", core_c) * 1.0, 2)
            else:
                core_pnl_val = 0.0

            col_core_pnl = "#22c55e" if core_pnl_val >= 0 else "#ef4444"
            sign_core = "+" if core_pnl_val >= 0 else ""

            p_rows = [
                f"<tr>"
                f"<td>{dir_badge}</td>"
                f"<td style='text-align: center; font-weight: 700;'>{pos.get('contracts', core_c)}c</td>"
                f"<td style='text-align: right; font-weight: 600;'>{pos['open_price']:.2f}</td>"
                f"<td style='text-align: right;'>{ts_cell}</td>"
                f"<td style='text-align: right; color: {col_core_pnl}; font-weight: 700;'>{sign_core}{core_pnl_val:,.2f}&nbsp;€</td>"
                f"</tr>"
            ]

            for idx, inc in enumerate(increments, 1):
                if live_mid is not None:
                    inc_diff = (live_mid - inc["open_price"]) if inc["direction"] == "LONG" else (inc["open_price"] - live_mid)
                    inc_pnl_val = round(inc_diff * inc.get("contracts", inc_c) * 1.0, 2)
                else:
                    inc_pnl_val = 0.0

                col_inc_pnl = "#22c55e" if inc_pnl_val >= 0 else "#ef4444"
                sign_inc = "+" if inc_pnl_val >= 0 else ""
                tp_val = inc.get("tp_price", 0.0)
                tp_cell = f"<span style='color: #38bdf8; font-weight: 700; white-space: nowrap;'>{tp_val:.2f}</span>"

                p_rows.append(
                    f"<tr>"
                    f"<td><span style='color: #f59e0b; font-weight: 600;'>➕ Incr #{idx}</span></td>"
                    f"<td style='text-align: center; font-weight: 700;'>{inc.get('contracts', inc_c)}c</td>"
                    f"<td style='text-align: right; font-weight: 600;'>{inc['open_price']:.2f}</td>"
                    f"<td style='text-align: right;'>{tp_cell}</td>"
                    f"<td style='text-align: right; color: {col_inc_pnl}; font-weight: 700;'>{sign_inc}{inc_pnl_val:,.2f}&nbsp;€</td>"
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

            st.markdown(f"""
            <table class='table-dark-hyper'>
                <thead>
                    <tr><th>Posizione</th><th style='text-align: center;'>Size</th><th style='text-align: right;'>Open</th><th style='text-align: right;'>TP / TS</th><th style='text-align: right;'>P&L</th></tr>
                </thead>
                <tbody>{''.join(p_rows)}</tbody>
            </table>
            """, unsafe_allow_html=True)
        else:
            st.info("Portafoglio Flat. Nessun contratto a mercato.")


def render_sintesi_hyp(conto_selezionato="DANY_DEMO", is_us500=False, **kwargs):
    """Visualizza il riepilogo analitico delle operazioni reali chiuse su IG su Hyper 5M."""
    conto_attivo = st.session_state.get("conto_selezionato") or conto_selezionato or "DANY_DEMO"
    nome_clean = conto_attivo.replace("_DEMO", "").replace("_REALE", "")
    mgr = HyperOrderManager.get_instance(conto_attivo)

    trades_all = mgr.get_trades_history()
    # Filtriamo per 5M (escludendo eventuali residui 30S)
    trades_5m = [t for t in trades_all if t.get("tf") == "5M"]
    trades_active = trades_5m if trades_5m else [t for t in trades_all if t.get("tf") != "30S"]

    trades_gold = [t for t in trades_active if "CFDGOLD" in t.get("epic", "").upper() or "GOLD" in t.get("label", "").upper()]
    trades_us500 = [t for t in trades_active if "SPTRD" in t.get("epic", "").upper() or "US500" in t.get("label", "").upper()]

    tot_pnl = sum(float(t.get("pnl_eur", 0.0) or 0.0) for t in trades_active)
    tot_gold = sum(float(t.get("pnl_eur", 0.0) or 0.0) for t in trades_gold)
    tot_us500 = sum(float(t.get("pnl_eur", 0.0) or 0.0) for t in trades_us500)

    n_tot = len(trades_active)
    n_win = len([t for t in trades_active if float(t.get("pnl_eur", 0.0) or 0.0) > 0])
    wr = (n_win / n_tot * 100.0) if n_tot > 0 else 0.0

    st.markdown(f"<h3 style='margin: 0 0 10px 0; font-size: 1.05rem; font-weight: 700;'>📋 Sintesi Eseguiti Reali Hyper 5M <span style='font-size: 0.80rem; color: #94a3b8;'>({nome_clean})</span></h3>", unsafe_allow_html=True)

    # 1. KPI SINTESI
    s1, s2, s3, s4 = st.columns(4)
    with s1:
        col_pnl = "#22c55e" if tot_pnl > 0 else ("#ef4444" if tot_pnl < 0 else "#94a3b8")
        sign_p = "+" if tot_pnl > 0 else ""
        st.markdown(f"""
        <div class='kpi-card-hyper'>
            <div class='kpi-title-hyper'>P&L Totale Reale Hyper 5M</div>
            <div class='kpi-val-hyper' style='color: {col_pnl};'>{sign_p}{tot_pnl:,.2f} €</div>
            <div class='kpi-sub-hyper' style='color: #cbd5e1;'>Somma Gold + US500 su IG</div>
        </div>
        """, unsafe_allow_html=True)

    with s2:
        col_wr = "#22c55e" if wr >= 50 else ("#f59e0b" if wr > 0 else "#94a3b8")
        st.markdown(f"""
        <div class='kpi-card-hyper'>
            <div class='kpi-title-hyper'>Operazioni Chiuse / Win Rate</div>
            <div class='kpi-val-hyper' style='color: {col_wr};'>{wr:.1f}%</div>
            <div class='kpi-sub-hyper' style='color: #cbd5e1;'>{n_win} vincenti su {n_tot} concluse</div>
        </div>
        """, unsafe_allow_html=True)

    with s3:
        col_g = "#22c55e" if tot_gold > 0 else ("#ef4444" if tot_gold < 0 else "#94a3b8")
        sign_g = "+" if tot_gold > 0 else ""
        st.markdown(f"""
        <div class='kpi-card-hyper'>
            <div class='kpi-title-hyper'>P&L Spot Gold 1€ (5M)</div>
            <div class='kpi-val-hyper' style='color: {col_g};'>{sign_g}{tot_gold:,.2f} €</div>
            <div class='kpi-sub-hyper' style='color: #cbd5e1;'>{len(trades_gold)} operazioni concluse</div>
        </div>
        """, unsafe_allow_html=True)

    with s4:
        col_u = "#22c55e" if tot_us500 > 0 else ("#ef4444" if tot_us500 < 0 else "#94a3b8")
        sign_u = "+" if tot_us500 > 0 else ""
        st.markdown(f"""
        <div class='kpi-card-hyper'>
            <div class='kpi-title-hyper'>P&L US 500 Cash 1€ (5M)</div>
            <div class='kpi-val-hyper' style='color: {col_u};'>{sign_u}{tot_us500:,.2f} €</div>
            <div class='kpi-sub-hyper' style='color: #cbd5e1;'>{len(trades_us500)} operazioni concluse</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<div style='margin-bottom: 14px;'></div>", unsafe_allow_html=True)

    tab_s_gold, tab_s_us500, tab_s_all = st.tabs([
        f"🪙 Spot Gold 5M ({len(trades_gold)})",
        f"🇺🇸 US 500 Cash 5M ({len(trades_us500)})",
        f"📜 Tutti i Trade 5M ({len(trades_active)})"
    ])

    def _render_trades_table(trade_list, empty_msg):
        if not trade_list:
            st.info(empty_msg)
            return
        rows = []
        for t in trade_list:
            pnl = float(t.get("pnl_eur", 0.0) or 0.0)
            col_p = "#22c55e" if pnl > 0 else ("#ef4444" if pnl < 0 else "#94a3b8")
            sign = "+" if pnl > 0 else ""
            d_col = "#22c55e" if t.get("direction") == "LONG" else "#ef4444"
            deal = t.get("deal_id", "--")
            deal_short = deal[:10] + "..." if len(deal) > 12 else deal
            is_us = ("SPTRD" in t.get("epic", "").upper() or "US500" in t.get("label", "").upper())
            inst_badge = "<span style='color: #38bdf8; font-weight: 700;'>🇺🇸 US500</span>" if is_us else "<span style='color: #FFD700; font-weight: 700;'>🪙 Gold</span>"
            rows.append(
                f"<tr>"
                f"<td style='white-space: nowrap;'>{t.get('time_close', '--')}</td>"
                f"<td style='white-space: nowrap;'>{inst_badge}</td>"
                f"<td style='font-family: monospace; color: #94a3b8;'>{deal_short}</td>"
                f"<td style='color: {d_col}; font-weight: 700;'>{t.get('direction', '--')}</td>"
                f"<td style='text-align: center;'>{t.get('contracts', 0)}c</td>"
                f"<td style='text-align: right;'>{float(t.get('open_price', 0.0)):.2f}</td>"
                f"<td style='text-align: right;'>{float(t.get('close_price', 0.0)):.2f}</td>"
                f"<td style='text-align: right; color: {col_p}; font-weight: 700;'>{sign}{pnl:,.2f} €</td>"
                f"<td style='color: #cbd5e1; font-size: 0.72rem;'>{t.get('reason', '--')}</td>"
                f"</tr>"
            )
        st.markdown(f"""
        <table class='table-dark-hyper'>
            <thead>
                <tr>
                    <th>Data/Ora Chiusura</th>
                    <th>Strumento</th>
                    <th>Deal ID IG</th>
                    <th>Direzione</th>
                    <th style='text-align: center;'>Contratti</th>
                    <th style='text-align: right;'>Open</th>
                    <th style='text-align: right;'>Close</th>
                    <th style='text-align: right;'>P&L Netto</th>
                    <th>Motivo Uscita</th>
                </tr>
            </thead>
            <tbody>{''.join(rows)}</tbody>
        </table>
        """, unsafe_allow_html=True)

    with tab_s_gold:
        _render_trades_table(trades_gold, "Nessuna operazione reale chiusa su Spot Gold 5M.")

    with tab_s_us500:
        _render_trades_table(trades_us500, "Nessuna operazione reale chiusa su US 500 Cash 5M.")

    with tab_s_all:
        _render_trades_table(trades_active, "Nessuna operazione 5M registrata.")
        if trades_active:
            c_cl1, c_cl2 = st.columns([3, 1])
            with c_cl2:
                if st.button("🗑️ Azzera Archivio Sintesi", key="btn_clear_sintesi"):
                    st.session_state["hyper_target_subtab"] = "sintesi"
                    mgr.clear_trades_history()
                    st.rerun()


def render_hyper_tab(conto_selezionato="DANY_DEMO"):
    """Pannello principale integrato per la tab HYPER nella Dashboard principale."""
    inject_hyper_css()

    conto_attivo = st.session_state.get("conto_selezionato") or conto_selezionato or "DANY_DEMO"

    # Selettore Strumento Operativo Hyper in evidenza
    c_sel, c_info = st.columns([1.8, 3.2])
    with c_sel:
        scelta_inst = st.radio(
            "Strumento Hyper:",
            ["🪙 Spot Gold 1€", "🇺🇸 US 500 Cash 1€"],
            index=0,
            horizontal=True,
            label_visibility="collapsed",
            key=f"radio_inst_hyper_{conto_attivo}"
        )
    is_us500 = ("US 500" in scelta_inst)

    with c_info:
        if is_us500:
            st.markdown("<div style='padding-top: 6px; font-size: 0.76rem; color: #38bdf8; font-weight: 600;'>🇺🇸 US 500 Cash (1€/pt) • S&R Puro KJ55 (5M: Core 4c + 2 Incr 2c, TP 10pt)</div>", unsafe_allow_html=True)
        else:
            st.markdown("<div style='padding-top: 6px; font-size: 0.76rem; color: #facc15; font-weight: 600;'>🪙 Spot Gold (1€/p) • S&R Puro KJ55 (5M: Core 5c + Incr 3c, TP 5p)</div>", unsafe_allow_html=True)

    if is_us500:
        engine_5m = HyperUS500M5Engine.get_instance(account_dir=conto_attivo)
    else:
        engine_5m = HyperGoldM5Engine.get_instance(account_dir=conto_attivo)

    is_5m_on = engine_5m.trading_enabled

    tab_h5m, tab_sintesi = st.tabs([
        "📊 Hyper 5M (Trend Scalping)" + (" 🟢 ATTIVO" if is_5m_on else ""),
        "📋 Sintesi Hyp (Eseguiti)"
    ])

    with tab_h5m:
        render_hyper_5m(conto_selezionato=conto_attivo, is_us500=is_us500)

    with tab_sintesi:
        render_sintesi_hyp(conto_selezionato=conto_attivo, is_us500=is_us500)

    target_subtab = st.session_state.pop("hyper_target_subtab", None)
    target_js = target_subtab if target_subtab else ""

    components.html(f"""
        <script>
        (function() {{
            function gestisciHyperTabs() {{
                try {{
                    const tabs = window.parent.document.querySelectorAll('div[data-testid="stTabs"] button[role="tab"]');
                    let target = "{target_js}";
                    if (target) {{
                        sessionStorage.setItem("hyper_active_subtab", target);
                    }} else {{
                        target = sessionStorage.getItem("hyper_active_subtab") || "";
                    }}

                    for (let t of tabs) {{
                        const txt = (t.innerText || t.textContent || "").trim();
                        if (txt.includes("Hyper 5M") && !t._hyper_listener) {{
                            t._hyper_listener = true;
                            t.addEventListener("click", function() {{
                                sessionStorage.setItem("hyper_active_subtab", "5m");
                            }});
                        }} else if (txt.includes("Sintesi Hyp") && !t._hyper_listener) {{
                            t._hyper_listener = true;
                            t.addEventListener("click", function() {{
                                sessionStorage.setItem("hyper_active_subtab", "sintesi");
                            }});
                        }}
                    }}

                    if (target === "5m") {{
                        for (let t of tabs) {{
                            const txt = (t.innerText || t.textContent || "").trim();
                            if (txt.includes("Hyper 5M")) {{
                                if (t.getAttribute("aria-selected") !== "true") {{
                                    t.click();
                                }}
                                break;
                            }}
                        }}
                    }} else if (target === "sintesi") {{
                        for (let t of tabs) {{
                            const txt = (t.innerText || t.textContent || "").trim();
                            if (txt.includes("Sintesi Hyp")) {{
                                if (t.getAttribute("aria-selected") !== "true") {{
                                    t.click();
                                }}
                                break;
                            }}
                        }}
                    }}
                }} catch(e) {{
                    console.error("Hyper tab switcher error:", e);
                }}
            }}
            gestisciHyperTabs();
            setTimeout(gestisciHyperTabs, 60);
            setTimeout(gestisciHyperTabs, 180);
        }})();
        </script>
    """, height=0, width=0)
