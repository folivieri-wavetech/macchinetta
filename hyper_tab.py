import os
import time
import datetime
import streamlit as st

from hyper_gold_engine import (
    HyperGoldEngine, CANDLE_SECONDS as CANDLE_SECONDS_30S, WARMUP_BARS_KJ as WARMUP_BARS_KJ_30S,
    WARMUP_BARS_TK as WARMUP_BARS_TK_30S, CORE_CONTRACTS as CORE_CONTRACTS_30S,
    CORE_TS_TRIGGER_PIPS as CORE_TS_TRIGGER_PIPS_30S, CORE_TS_LOCK_PIPS as CORE_TS_LOCK_PIPS_30S,
    CORE_TS_DISTANCE_PIPS as CORE_TS_DISTANCE_PIPS_30S, INC_CONTRACTS as INC_CONTRACTS_30S,
    MAX_INCREMENTS as MAX_INCREMENTS_30S, INC_TP_PIPS as INC_TP_PIPS_30S,
    CANDELA_SEGNALE_OFFSET_PIPS as CANDELA_SEGNALE_OFFSET_PIPS_30S,
    TK_FILTER_PIPS as TK_FILTER_PIPS_30S, DEFAULT_SCALINI_PLAN_30S,
    is_gold_trading_suspended, is_gold_feed_suspended
)

from hyper_gold_m1_engine import (
    HyperGoldM1Engine, CANDLE_SECONDS as CANDLE_SECONDS_5M, WARMUP_BARS_KJ as WARMUP_BARS_KJ_5M,
    WARMUP_BARS_TK as WARMUP_BARS_TK_5M, CORE_CONTRACTS as CORE_CONTRACTS_5M,
    CORE_TS_TRIGGER_PIPS as CORE_TS_TRIGGER_PIPS_5M, INC_CONTRACTS as INC_CONTRACTS_5M,
    MAX_INCREMENTS as MAX_INCREMENTS_5M, INC_TP_PIPS as INC_TP_PIPS_5M,
    CANDELA_SEGNALE_OFFSET_PIPS as CANDELA_SEGNALE_OFFSET_PIPS_5M,
    TK_FILTER_PIPS as TK_FILTER_PIPS_5M
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
        /* Forza la visibilità di tutte le sottotab di Hyper (30s e 5m) */
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
    </style>
    """, unsafe_allow_html=True)


@st.fragment(run_every=2)
def render_hyper_30s(conto_selezionato="DANY_DEMO", is_other_active=False, **kwargs):
    conto_attivo = st.session_state.get("conto_selezionato") or conto_selezionato or "DANY_DEMO"
    nome_clean = conto_attivo.replace("_DEMO", "").replace("_REALE", "")

    engine = HyperGoldEngine.get_instance(account_dir=conto_attivo)

    with engine.lock:
        is_conn = engine.ls_connected
        live_mid = engine.live_mid
        live_bid = engine.live_bid
        live_ask = engine.live_ask
        total_ticks = engine.total_ticks
        candles_count = len(engine.candles)
        kj = engine.kj55
        tk = engine.tk144
        pos = engine.position
        increments = list(engine.increments)
        total_contracts = (pos.get("contracts", CORE_CONTRACTS_30S) + sum(i.get("contracts", INC_CONTRACTS_30S) for i in increments)) if pos else 0
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

    # P&L e Storico Eseguiti Reali IG per 30S (Fonte di verità assoluta)
    order_mgr = HyperOrderManager.get_instance(conto_attivo)
    history_30s = order_mgr.get_trades_history(tf="30S")
    session_realized_pnl = sum(float(t.get("pnl_eur", 0.0) or 0.0) for t in history_30s)
    num_closed = len(history_30s)

    # Intestazione e Badge di Stato
    c_title, c_badges = st.columns([2.3, 1.7])
    with c_title:
        st.markdown(f"<h3 style='margin: 0; font-size: 1.05rem; font-weight: 700; white-space: nowrap;'>⚡ Hyper Spot Gold 1€ <span style='background: rgba(56, 189, 248, 0.20); color: #38bdf8; border: 1px solid #38bdf8; padding: 2px 7px; border-radius: 5px; font-size: 0.76rem; font-weight: 800; letter-spacing: 0.04em; margin: 0 4px;'>⏱️ TF 30 SEC</span> <span style='font-size: 0.80rem; color: #94a3b8;'>({conto_attivo})</span></h3>", unsafe_allow_html=True)
        st.markdown("<div style='font-size: 0.70rem; color: #94a3b8; white-space: nowrap; margin-top: 2px;'>Filtro Macro TK 144 • Trigger KJ 55 (±2p) • Scalini Fast: 4c @ 2p + 4c @ 3p • Core Runner 2c (TS +10p din.)</div>", unsafe_allow_html=True)

    with c_badges:
        is_feed_closed = is_gold_feed_suspended()
        is_trade_frozen = is_gold_trading_suspended()

        if is_conn:
            badge_ls = f"<span class='badge-live-hyper' style='background: rgba(34, 197, 94, 0.15); color: #22c55e; border: 1px solid #22c55e;'>🟢 Lightstreamer LIVE ({total_ticks} tick)</span>"
        elif is_feed_closed:
            badge_ls = "<span class='badge-live-hyper' style='background: rgba(100, 116, 139, 0.2); color: #94a3b8; border: 1px solid #64748b;'>💤 Feed Chiuso (22:45-00:00)</span>"
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
            <div class='kpi-sub-hyper' style='color: #94a3b8;'>Disponibile: <b style='color: #4ade80;'>{val_disp} €</b> • Equity: <b style='color: #38bdf8;'>{val_equity} €</b></div>
        </div>
        """, unsafe_allow_html=True)

    with k2:
        col_real = "#22c55e" if session_realized_pnl >= 0 else ("#ef4444" if session_realized_pnl < 0 else "#94a3b8")
        sign_real = "+" if session_realized_pnl > 0 else ""
        pnl_str = f"{session_realized_pnl:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        st.markdown(f"""
        <div class='kpi-card-hyper'>
            <div class='kpi-title-hyper'>P&L Sessione Hyper (30s)</div>
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
            if pos.get("ts_active"):
                ts_px = pos.get("ts_price", 0.0)
                peak_px = pos.get("peak_price", pos["open_price"])
                sub_text = f"🚀 TRAILING ATTIVO | Stop: {ts_px:.2f} (Peak: {peak_px:.2f}) | Incr: {num_inc}/{MAX_INCREMENTS_30S}"
            else:
                sub_text = f"Core: {CORE_CONTRACTS_30S}c @ {pos['open_price']:.2f} (TS Trigger: +{CORE_TS_TRIGGER_PIPS_30S:.0f} pip) | Incr: {num_inc}/{MAX_INCREMENTS_30S}"

            st.markdown(f"""
            <div class='kpi-card-hyper'>
                <div class='kpi-title-hyper'>Esposizione a Mercato</div>
                <div class='kpi-val-hyper' style='color: {dir_col}; font-size: 1.12rem; white-space: nowrap;'>{dir_icon} {pos['direction']} <span style='font-size: 0.92rem; font-weight: 600; opacity: 0.88;'>({total_contracts}/10 Contr.)</span></div>
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

    # 2. INDICATORI DI MERCATO (30S)
    m1, m2, m3, m4 = st.columns([1.10, 1.90, 1.0, 1.0])
    with m1:
        px_str = f"{live_mid:.2f}" if live_mid else "--"
        st.markdown(f"""
        <div class='kpi-card-hyper' style='padding: 10px 14px; display: flex; flex-direction: column; justify-content: center;'>
            <div class='kpi-title-hyper'>Spot Gold 1€ (Mid Live)</div>
            <div style='font-size: 1.25rem; font-weight: 800; color: #22c55e; margin-top: 4px;'>{px_str} €</div>
        </div>
        """, unsafe_allow_html=True)

    with m2:
        tk_str = f"{tk:.2f}" if tk else "--"
        kj_str = f"{kj:.2f}" if kj else "--"
        if live_mid and tk:
            if live_mid > (tk + TK_FILTER_PIPS_30S):
                regime = "🟢 BULLISH (SOLO LONG)"
                col_reg = "#22c55e"
            elif live_mid < (tk - TK_FILTER_PIPS_30S):
                regime = "🔴 BEARISH (SOLO SHORT)"
                col_reg = "#ef4444"
            else:
                regime = "⚪ ZONA NEUTRA TK (±3p)"
                col_reg = "#f59e0b"
        else:
            regime = "Inizializzazione..."
            col_reg = "#94a3b8"

        st.markdown(f"""
        <div class='kpi-card-hyper' style='padding: 8px 14px;'>
            <div class='kpi-title-hyper' style='display: flex; justify-content: space-between; align-items: center;'>
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
            <div style='font-size: 0.66rem; color: #94a3b8; margin-top: 5px; text-align: center; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;'>Filtro Macro TK144 (±3p) • Trigger KJ55 • 🪂 Paracadute KJ: ±2p</div>
        </div>
        """, unsafe_allow_html=True)

    with m3:
        hyper_margine = total_contracts * 220.0
        st.markdown(f"""
        <div class='kpi-card-hyper' style='padding: 10px 14px;'>
            <div class='kpi-title-hyper'>Margine ({nome_clean})</div>
            <div style='font-size: 1.18rem; font-weight: 700; color: #f59e0b;'>{val_margine} €</div>
            <div style='font-size: 0.70rem; color: #cbd5e1;'>Hyper: {hyper_margine:,.0f} € ({total_contracts}c) • Marg. Conto</div>
        </div>
        """, unsafe_allow_html=True)

    with m4:
        sec_elapsed = 0
        if curr_bar_t:
            sec_elapsed = min(30, int(time.time() - curr_bar_t))
        st.markdown(f"""
        <div class='kpi-card-hyper' style='padding: 10px 14px;'>
            <div class='kpi-title-hyper'>Tempo Barra (30s)</div>
            <div style='font-size: 1.18rem; font-weight: 700; color: #cbd5e1;'>{sec_elapsed}s / 30s</div>
            <div style='font-size: 0.70rem; color: #94a3b8;'>Prossima chiusura: {30 - sec_elapsed}s</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<div style='margin-bottom: 12px;'></div>", unsafe_allow_html=True)

    # 3. SEZIONE CONTROLLI E OPERAZIONI
    col_left, col_right = st.columns([1.60, 1.60])

    with col_left:
        cur_core = int(getattr(engine, "core_size", 2))
        cur_plan = getattr(engine, "scalini_plan", DEFAULT_SCALINI_PLAN_30S)
        tot_plan_c = sum(it["contracts"] for it in cur_plan)
        tot_all_c = cur_core + tot_plan_c

        with st.expander("⚙️ Assetto Scalini 30S: Fast Scalping (10 Contratti)", expanded=False):
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

        c_btn1, c_btn2 = st.columns([1, 1])
        dis_start = trading_on
        with c_btn1:
            st.markdown("<div class='btn-start-hyper'>", unsafe_allow_html=True)
            if st.button("🟢 AVVIA 30S", key=f"btn_start_30s_{conto_selezionato}", disabled=dis_start, use_container_width=True):
                engine.set_trading(True)
                st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)

        with c_btn2:
            st.markdown("<div class='btn-stop-hyper'>", unsafe_allow_html=True)
            if st.button("🔴 STOP 30S", key=f"btn_stop_30s_{conto_selezionato}", disabled=(not trading_on), use_container_width=True):
                engine.set_trading(False)
                st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)

        st.markdown("<div style='margin-bottom: 12px;'></div>", unsafe_allow_html=True)
        c_th1, c_th2 = st.columns([1.15, 1.85])
        with c_th1:
            st.markdown("<h4 style='margin: 6px 0 8px 0; font-size: 0.90rem; font-weight: 700; white-space: nowrap;'>📋 Storico Operazioni (30s)</h4>", unsafe_allow_html=True)
        with c_th2:
            st.markdown("<div class='btn-azzera-hyper'>", unsafe_allow_html=True)
            if st.button("🔄 Azzera Sessione", key=f"btn_clr_trades_30s_{conto_selezionato}", help="Azzera lo storico delle operazioni chiuse e il P&L di sessione", use_container_width=True):
                order_mgr.clear_trades_history(tf="30S")
                engine.clear_session_trades()
                st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)
        closed_trades = history_30s
        if closed_trades:
            num_core_closed = 0
            pnl_core_closed = 0.0
            num_inc_closed = 0
            pnl_inc_closed = 0.0

            for t in closed_trades:
                lbl = t.get("label", "").upper()
                p = float(t.get("pnl_eur", 0.0) or 0.0)
                if "CORE" in lbl:
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
                    f"<tr><td>{t_str}</td><td>{action_badge}</td><td style='white-space: nowrap;'>{t['open_price']:.2f}</td><td style='white-space: nowrap;'>{t['close_price']:.2f}</td><td style='color: {col_pnl}; font-weight: bold; white-space: nowrap;'>{sign_p}&nbsp;€</td><td style='font-family: monospace; font-size: 0.74rem; color: #94a3b8; white-space: nowrap;'>{t.get('deal_id', '--')}</td><td style='color: #cbd5e1; font-size: 0.78rem;'>{rsn}</td></tr>"
                )

            summary_html = (
                f"<tr style='background-color: #1e293b; border-top: 2px solid #475569; font-weight: 700; font-size: 0.75rem;'>"
                f"<td colspan='2' style='color: #f8fafc; text-transform: uppercase;'>📊 TOTALI CHIUSI (30S)</td>"
                f"<td colspan='2' style='color: #cbd5e1;'>Core: <span style='color: #38bdf8;'>{num_core_closed}</span> (<span style='color: {col_core_pnl};'>{sign_core}{pnl_core_closed:,.2f} €</span>) | Scalini: <span style='color: #38bdf8;'>{num_inc_closed}</span> (<span style='color: {col_inc_pnl};'>{sign_inc}{pnl_inc_closed:,.2f} €</span>)</td>"
                f"<td style='color: {col_tot_pnl}; font-size: 0.84rem; white-space: nowrap;'>{sign_tot}{tot_pnl_closed:,.2f}&nbsp;€</td>"
                f"<td colspan='2' style='color: #94a3b8; font-size: 0.70rem;'>P&L complessivo eseguiti reali IG</td>"
                f"</tr>"
            )
            rows_html.append(summary_html)

            st.markdown(f"""
            <table class='table-dark-hyper'>
                <thead>
                    <tr><th>Orario</th><th>Posizione</th><th>Prezzo In</th><th>Prezzo Out</th><th style='white-space: nowrap;'>P&L</th><th style='white-space: nowrap;'>Deal ID</th><th>Trigger Chiusura</th></tr>
                </thead>
                <tbody>{''.join(rows_html)}</tbody>
            </table>
            """, unsafe_allow_html=True)
        else:
            st.info("Nessuna operazione ancora chiusa in sessione 30s.")

    with col_right:
        sig_act = getattr(engine, "signal_candle_active", False)
        sig_px = getattr(engine, "signal_stop_price", None)
        sig_ref = getattr(engine, "signal_ref_price", None)

        if sig_act and sig_px is not None:
            if sig_ref is None:
                if pos and pos.get("direction") == "LONG":
                    sig_ref = round(sig_px + CANDELA_SEGNALE_OFFSET_PIPS_30S, 2)
                elif pos and pos.get("direction") == "SHORT":
                    sig_ref = round(sig_px - CANDELA_SEGNALE_OFFSET_PIPS_30S, 2)
                else:
                    sig_ref = sig_px
            sign_op = "-" if (pos and pos.get("direction") == "LONG") else "+"
            sig_badge = f"<span style='font-size: 0.90rem; font-weight: 700; color: #f97316; white-space: nowrap;'>Candela Segnale: <span style='font-weight: 800; color: #fb923c;'>{sig_px:.2f}</span> <span style='font-size: 0.82rem; color: #fed7aa;'>({sig_ref:.2f} {sign_op} {CANDELA_SEGNALE_OFFSET_PIPS_30S:.0f}p)</span></span>"
        else:
            sig_badge = "<span style='font-size: 0.90rem; font-weight: 700; color: #64748b; white-space: nowrap;'>---</span>"

        st.markdown(f"""
        <div style='display: flex; justify-content: space-between; align-items: baseline; margin: 0 0 8px 0;'>
            <h4 style='margin: 0; font-size: 0.95rem; font-weight: 700;'>💼 Posizioni in Portafoglio (30s)</h4>
            {sig_badge}
        </div>
        """, unsafe_allow_html=True)

        if pos:
            dir_pos = pos["direction"]
            dir_col = "#22c55e" if dir_pos == "LONG" else "#ef4444"
            dir_badge = f"<span style='color: {dir_col}; font-weight: 700;'>{'🟢' if dir_pos == 'LONG' else '🔴'} Core {dir_pos}</span> <span style='font-size: 0.82rem; color: #cbd5e1;'>({pos['open_price']:.2f})</span>"

            if pos.get("ts_active"):
                ts_stop_px = pos.get("ts_price", 0.0)
                ts_dist = pos.get("ts_distance", CORE_TS_DISTANCE_PIPS_30S)
                ts_cell = f"<span style='color: #4ade80; font-weight: 700; white-space: nowrap;'>TS {ts_stop_px:.2f}</span> <span style='font-size: 0.70rem; color: #86efac;'>(Dist: {ts_dist:.0f}p)</span>"
            else:
                ts_target = round((pos["open_price"] + CORE_TS_TRIGGER_PIPS_30S) if dir_pos == "LONG" else (pos["open_price"] - CORE_TS_TRIGGER_PIPS_30S), 2)
                ts_sign = "+" if dir_pos == "LONG" else "-"
                ts_cell = f"<span style='color: #38bdf8; font-weight: 600; white-space: nowrap;'>{ts_target:.2f}</span> <span style='font-size: 0.70rem; color: #94a3b8;'>({ts_sign}{CORE_TS_TRIGGER_PIPS_30S:.0f}p)</span>"

            if live_mid is not None:
                core_diff = (live_mid - pos["open_price"]) if dir_pos == "LONG" else (pos["open_price"] - live_mid)
                core_pnl_val = round(core_diff * pos.get("contracts", CORE_CONTRACTS_30S) * 1.0, 2)
            else:
                core_pnl_val = 0.0

            col_core_pnl = "#22c55e" if core_pnl_val >= 0 else "#ef4444"
            sign_core = "+" if core_pnl_val >= 0 else ""

            p_rows = [
                f"<tr>"
                f"<td>{dir_badge}</td>"
                f"<td style='text-align: center; font-weight: 700;'>{pos.get('contracts', CORE_CONTRACTS_30S)}c</td>"
                f"<td style='text-align: right; font-weight: 600;'>{pos['open_price']:.2f}</td>"
                f"<td style='text-align: right;'>{ts_cell}</td>"
                f"<td style='text-align: right; color: {col_core_pnl}; font-weight: 700;'>{sign_core}{core_pnl_val:,.2f}&nbsp;€</td>"
                f"</tr>"
            ]

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
                tp_cell = f"<span style='color: #38bdf8; font-weight: 700; white-space: nowrap;'>{tp_val:.2f}</span> <span style='font-size: 0.70rem; color: #fed7aa;'>(+{tp_dist_p:.0f}p)</span>"

                p_rows.append(
                    f"<tr>"
                    f"<td><span style='color: #f59e0b; font-weight: 600;'>➕ Scalino #{step_i}</span></td>"
                    f"<td style='text-align: center; font-weight: 700;'>{inc.get('contracts', 1)}c</td>"
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


@st.fragment(run_every=2)
def render_hyper_5m(conto_selezionato="DANY_DEMO", is_other_active=False, **kwargs):
    conto_attivo = st.session_state.get("conto_selezionato") or conto_selezionato or "DANY_DEMO"
    nome_clean = conto_attivo.replace("_DEMO", "").replace("_REALE", "")

    engine = HyperGoldM1Engine.get_instance(account_dir=conto_attivo)

    with engine.lock:
        is_conn = engine.ls_connected
        live_mid = engine.live_mid
        live_bid = engine.live_bid
        live_ask = engine.live_ask
        total_ticks = engine.total_ticks
        candles_count = len(engine.candles)
        kj = engine.kj55
        tk = engine.tk144
        pos = engine.position
        increments = list(engine.increments)
        total_contracts = (pos.get("contracts", CORE_CONTRACTS_5M) + sum(i.get("contracts", INC_CONTRACTS_5M) for i in increments)) if pos else 0
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
    history_5m = order_mgr.get_trades_history(tf="5M")
    session_realized_pnl = sum(float(t.get("pnl_eur", 0.0) or 0.0) for t in history_5m)
    num_closed = len(history_5m)

    # Intestazione e Badge di Stato
    c_title, c_badges = st.columns([2.3, 1.7])
    with c_title:
        st.markdown(f"<h3 style='margin: 0; font-size: 1.05rem; font-weight: 700; white-space: nowrap;'>⚡ Hyper Spot Gold 1€ <span style='background: rgba(245, 158, 11, 0.20); color: #f59e0b; border: 1px solid #f59e0b; padding: 2px 7px; border-radius: 5px; font-size: 0.76rem; font-weight: 800; letter-spacing: 0.04em; margin: 0 4px;'>📊 TF 5 MIN</span> <span style='font-size: 0.80rem; color: #94a3b8;'>({conto_attivo})</span></h3>", unsafe_allow_html=True)
        st.markdown("<div style='font-size: 0.70rem; color: #94a3b8; white-space: nowrap; margin-top: 2px;'>Filtro Macro TK 144 • Trigger KJ 55 (Paracadute 6p, Candela Segnale 3p) • Core 5c • Incr 3c (TP +5p)</div>", unsafe_allow_html=True)

    with c_badges:
        is_feed_closed = is_gold_feed_suspended()
        is_trade_frozen = is_gold_trading_suspended()

        if is_conn:
            badge_ls = f"<span class='badge-live-hyper' style='background: rgba(34, 197, 94, 0.15); color: #22c55e; border: 1px solid #22c55e;'>🟢 Lightstreamer LIVE ({total_ticks} tick)</span>"
        elif is_feed_closed:
            badge_ls = "<span class='badge-live-hyper' style='background: rgba(100, 116, 139, 0.2); color: #94a3b8; border: 1px solid #64748b;'>💤 Feed Chiuso (22:45-00:00)</span>"
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
            <div class='kpi-sub-hyper' style='color: #94a3b8;'>Disponibile: <b style='color: #4ade80;'>{val_disp} €</b> • Equity: <b style='color: #38bdf8;'>{val_equity} €</b></div>
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
            sub_text = f"Core: {CORE_CONTRACTS_5M}c @ {pos['open_price']:.2f} (TS Trigger: +{CORE_TS_TRIGGER_PIPS_5M:.0f}p) | Incr: {num_inc}/{MAX_INCREMENTS_5M}"
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

    # 2. INDICATORI DI MERCATO (5M)
    m1, m2, m3, m4 = st.columns([1.10, 1.90, 1.0, 1.0])
    with m1:
        px_str = f"{live_mid:.2f}" if live_mid else "--"
        st.markdown(f"""
        <div class='kpi-card-hyper' style='padding: 10px 14px; display: flex; flex-direction: column; justify-content: center;'>
            <div class='kpi-title-hyper'>Spot Gold 1€ (Mid Live)</div>
            <div style='font-size: 1.25rem; font-weight: 800; color: #22c55e; margin-top: 4px;'>{px_str} €</div>
        </div>
        """, unsafe_allow_html=True)

    with m2:
        tk_str = f"{tk:.2f}" if tk else "--"
        kj_str = f"{kj:.2f}" if kj else "--"
        if live_mid and tk:
            if live_mid > (tk + TK_FILTER_PIPS_5M):
                regime = "🟢 BULLISH (SOLO LONG)"
                col_reg = "#22c55e"
            elif live_mid < (tk - TK_FILTER_PIPS_5M):
                regime = "🔴 BEARISH (SOLO SHORT)"
                col_reg = "#ef4444"
            else:
                regime = "⚪ ZONA NEUTRA TK (±3p)"
                col_reg = "#f59e0b"
        else:
            regime = "Inizializzazione..."
            col_reg = "#94a3b8"

        st.markdown(f"""
        <div class='kpi-card-hyper' style='padding: 8px 14px;'>
            <div class='kpi-title-hyper' style='display: flex; justify-content: space-between; align-items: center;'>
                <span>Livelli Chiave (M5)</span>
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
            <div style='font-size: 0.66rem; color: #94a3b8; margin-top: 5px; text-align: center; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;'>Filtro Macro TK144 (±3p) • Trigger KJ55 • 🪂 Paracadute KJ: ±6p</div>
        </div>
        """, unsafe_allow_html=True)

    with m3:
        hyper_margine = total_contracts * 220.0
        st.markdown(f"""
        <div class='kpi-card-hyper' style='padding: 10px 14px;'>
            <div class='kpi-title-hyper'>Margine ({nome_clean})</div>
            <div style='font-size: 1.18rem; font-weight: 700; color: #f59e0b;'>{val_margine} €</div>
            <div style='font-size: 0.70rem; color: #cbd5e1;'>Hyper: {hyper_margine:,.0f} € ({total_contracts}c) • Marg. Conto</div>
        </div>
        """, unsafe_allow_html=True)

    with m4:
        sec_elapsed = 0
        if curr_bar_t:
            sec_elapsed = min(300, int(time.time() - curr_bar_t))
        st.markdown(f"""
        <div class='kpi-card-hyper' style='padding: 10px 14px;'>
            <div class='kpi-title-hyper'>Tempo Barra (M5)</div>
            <div style='font-size: 1.18rem; font-weight: 700; color: #cbd5e1;'>{sec_elapsed}s / 300s</div>
            <div style='font-size: 0.70rem; color: #94a3b8;'>Prossima chiusura: {300 - sec_elapsed}s</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<div style='margin-bottom: 12px;'></div>", unsafe_allow_html=True)

    # 3. SEZIONE CONTROLLI E OPERAZIONI
    col_left, col_right = st.columns([1.60, 1.60])

    with col_left:
        with st.expander("⚙️ Assetto Contratti M5 (Core 5c + Incr 3c)", expanded=False):
            st.markdown(f"""
            <div style='background: rgba(15, 23, 42, 0.6); border: 1px solid #334155; border-radius: 6px; padding: 10px 12px; font-size: 0.80rem; line-height: 1.6;'>
                <div style='color: #f59e0b; font-weight: 700; margin-bottom: 4px;'>🎯 Piano Ingressi M5 Trend Scalping:</div>
                <div>• <b>Core Runner</b>: <span style='color: #4ade80; font-weight: 600;'>{CORE_CONTRACTS_5M} contratti</span> (TS a <b>+{CORE_TS_TRIGGER_PIPS_5M:.0f} pip</b>)</div>
                <div>• <b>Incrementi</b>: fino a <b>{MAX_INCREMENTS_5M}</b> da <span style='color: #f59e0b; font-weight: 600;'>{INC_CONTRACTS_5M} contratti</span> (TP +{INC_TP_PIPS_5M:.0f} pip)</div>
                <div style='border-top: 1px solid #334155; margin-top: 6px; padding-top: 4px;'>
                    <span style='color: #94a3b8;'>Paracadute KJ55: <b>±6 pip</b> • Candela Segnale: <b>±3 pip</b></span>
                </div>
            </div>
            """, unsafe_allow_html=True)

        st.markdown("<div style='margin-bottom: 8px;'></div>", unsafe_allow_html=True)

        c_btn1, c_btn2 = st.columns([1, 1])
        dis_start = trading_on
        with c_btn1:
            st.markdown("<div class='btn-start-hyper'>", unsafe_allow_html=True)
            if st.button("🟢 AVVIA 5M", key=f"btn_start_m5_{conto_selezionato}", disabled=dis_start, use_container_width=True):
                engine.set_trading(True)
                st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)

        with c_btn2:
            st.markdown("<div class='btn-stop-hyper'>", unsafe_allow_html=True)
            if st.button("🔴 STOP 5M", key=f"btn_stop_m5_{conto_selezionato}", disabled=(not trading_on), use_container_width=True):
                engine.set_trading(False)
                st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)

        st.markdown("<div style='margin-bottom: 12px;'></div>", unsafe_allow_html=True)
        c_th1, c_th2 = st.columns([1.15, 1.85])
        with c_th1:
            st.markdown("<h4 style='margin: 6px 0 8px 0; font-size: 0.90rem; font-weight: 700; white-space: nowrap;'>📋 Storico Operazioni (M5)</h4>", unsafe_allow_html=True)
        with c_th2:
            st.markdown("<div class='btn-azzera-hyper'>", unsafe_allow_html=True)
            if st.button("🔄 Azzera Sessione", key=f"btn_clr_trades_m5_{conto_selezionato}", help="Azzera lo storico delle operazioni chiuse e il P&L di sessione", use_container_width=True):
                order_mgr.clear_trades_history(tf="5M")
                engine.clear_session_trades()
                st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)
        closed_trades = history_5m
        if closed_trades:
            num_core_closed = 0
            pnl_core_closed = 0.0
            num_inc_closed = 0
            pnl_inc_closed = 0.0

            for t in closed_trades:
                lbl = t.get("label", "").upper()
                p = float(t.get("pnl_eur", 0.0) or 0.0)
                if "CORE" in lbl:
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
                    f"<tr><td>{t_str}</td><td>{action_badge}</td><td style='white-space: nowrap;'>{t['open_price']:.2f}</td><td style='white-space: nowrap;'>{t['close_price']:.2f}</td><td style='color: {col_pnl}; font-weight: bold; white-space: nowrap;'>{sign_p}&nbsp;€</td><td style='font-family: monospace; font-size: 0.74rem; color: #94a3b8; white-space: nowrap;'>{t.get('deal_id', '--')}</td><td style='color: #cbd5e1; font-size: 0.78rem;'>{rsn}</td></tr>"
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
            <table class='table-dark-hyper'>
                <thead>
                    <tr><th>Orario</th><th>Posizione</th><th>Prezzo In</th><th>Prezzo Out</th><th style='white-space: nowrap;'>P&L</th><th style='white-space: nowrap;'>Deal ID</th><th>Trigger Chiusura</th></tr>
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
                    sig_ref = round(sig_px + CANDELA_SEGNALE_OFFSET_PIPS_5M, 2)
                elif pos and pos.get("direction") == "SHORT":
                    sig_ref = round(sig_px - CANDELA_SEGNALE_OFFSET_PIPS_5M, 2)
                else:
                    sig_ref = sig_px
            sign_op = "-" if (pos and pos.get("direction") == "LONG") else "+"
            sig_badge = f"<span style='font-size: 0.90rem; font-weight: 700; color: #f97316; white-space: nowrap;'>Candela Segnale: <span style='font-weight: 800; color: #fb923c;'>{sig_px:.2f}</span> <span style='font-size: 0.82rem; color: #fed7aa;'>({sig_ref:.2f} {sign_op} {CANDELA_SEGNALE_OFFSET_PIPS_5M:.0f}p)</span></span>"
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

            ts_target = round((pos["open_price"] + CORE_TS_TRIGGER_PIPS_5M) if dir_pos == "LONG" else (pos["open_price"] - CORE_TS_TRIGGER_PIPS_5M), 2)
            ts_sign = "+" if dir_pos == "LONG" else "-"
            ts_cell = f"<span style='color: #38bdf8; font-weight: 600; white-space: nowrap;'>{ts_target:.2f}</span> <span style='font-size: 0.70rem; color: #94a3b8;'>({ts_sign}{CORE_TS_TRIGGER_PIPS_5M:.0f}p)</span>"

            if live_mid is not None:
                core_diff = (live_mid - pos["open_price"]) if dir_pos == "LONG" else (pos["open_price"] - live_mid)
                core_pnl_val = round(core_diff * pos.get("contracts", CORE_CONTRACTS_5M) * 1.0, 2)
            else:
                core_pnl_val = 0.0

            col_core_pnl = "#22c55e" if core_pnl_val >= 0 else "#ef4444"
            sign_core = "+" if core_pnl_val >= 0 else ""

            p_rows = [
                f"<tr>"
                f"<td>{dir_badge}</td>"
                f"<td style='text-align: center; font-weight: 700;'>{pos.get('contracts', CORE_CONTRACTS_5M)}c</td>"
                f"<td style='text-align: right; font-weight: 600;'>{pos['open_price']:.2f}</td>"
                f"<td style='text-align: right;'>{ts_cell}</td>"
                f"<td style='text-align: right; color: {col_core_pnl}; font-weight: 700;'>{sign_core}{core_pnl_val:,.2f}&nbsp;€</td>"
                f"</tr>"
            ]

            for idx, inc in enumerate(increments, 1):
                if live_mid is not None:
                    inc_diff = (live_mid - inc["open_price"]) if inc["direction"] == "LONG" else (inc["open_price"] - live_mid)
                    inc_pnl_val = round(inc_diff * inc.get("contracts", 1) * 1.0, 2)
                else:
                    inc_pnl_val = 0.0

                col_inc_pnl = "#22c55e" if inc_pnl_val >= 0 else "#ef4444"
                sign_inc = "+" if inc_pnl_val >= 0 else ""
                tp_val = inc.get("tp_price", 0.0)
                tp_cell = f"<span style='color: #38bdf8; font-weight: 700; white-space: nowrap;'>{tp_val:.2f}</span>"

                p_rows.append(
                    f"<tr>"
                    f"<td><span style='color: #f59e0b; font-weight: 600;'>➕ Incr #{idx}</span></td>"
                    f"<td style='text-align: center; font-weight: 700;'>{inc.get('contracts', 1)}c</td>"
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


def render_sintesi_hyp(conto_selezionato="DANY_DEMO", **kwargs):
    """Visualizza il riepilogo analitico delle operazioni reali chiuse su IG divise per TimeFrame."""
    conto_attivo = st.session_state.get("conto_selezionato") or conto_selezionato or "DANY_DEMO"
    nome_clean = conto_attivo.replace("_DEMO", "").replace("_REALE", "")
    mgr = HyperOrderManager.get_instance(conto_attivo)

    trades_all = mgr.get_trades_history()
    trades_30s = [t for t in trades_all if t.get("tf") == "30S"]
    trades_5m = [t for t in trades_all if t.get("tf") == "5M"]

    tot_pnl = sum(float(t.get("pnl_eur", 0.0) or 0.0) for t in trades_all)
    tot_30s = sum(float(t.get("pnl_eur", 0.0) or 0.0) for t in trades_30s)
    tot_5m = sum(float(t.get("pnl_eur", 0.0) or 0.0) for t in trades_5m)

    n_tot = len(trades_all)
    n_win = len([t for t in trades_all if float(t.get("pnl_eur", 0.0) or 0.0) > 0])
    wr = (n_win / n_tot * 100.0) if n_tot > 0 else 0.0

    st.markdown(f"<h3 style='margin: 0 0 10px 0; font-size: 1.05rem; font-weight: 700;'>📋 Sintesi Eseguiti Reali Hyper <span style='font-size: 0.80rem; color: #94a3b8;'>({nome_clean})</span></h3>", unsafe_allow_html=True)

    # 1. KPI SINTESI
    s1, s2, s3, s4 = st.columns(4)
    with s1:
        col_pnl = "#22c55e" if tot_pnl > 0 else ("#ef4444" if tot_pnl < 0 else "#94a3b8")
        sign_p = "+" if tot_pnl > 0 else ""
        st.markdown(f"""
        <div class='kpi-card-hyper'>
            <div class='kpi-title-hyper'>P&L Totale Reale Hyper</div>
            <div class='kpi-val-hyper' style='color: {col_pnl};'>{sign_p}{tot_pnl:,.2f} €</div>
            <div class='kpi-sub-hyper' style='color: #cbd5e1;'>Somma 30S + 5M su IG</div>
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
        col_30 = "#22c55e" if tot_30s > 0 else ("#ef4444" if tot_30s < 0 else "#94a3b8")
        sign_30 = "+" if tot_30s > 0 else ""
        st.markdown(f"""
        <div class='kpi-card-hyper'>
            <div class='kpi-title-hyper'>P&L Hyper 30S (Scalping)</div>
            <div class='kpi-val-hyper' style='color: {col_30};'>{sign_30}{tot_30s:,.2f} €</div>
            <div class='kpi-sub-hyper' style='color: #cbd5e1;'>{len(trades_30s)} operazioni concluse</div>
        </div>
        """, unsafe_allow_html=True)

    with s4:
        col_5m = "#22c55e" if tot_5m > 0 else ("#ef4444" if tot_5m < 0 else "#94a3b8")
        sign_5m = "+" if tot_5m > 0 else ""
        st.markdown(f"""
        <div class='kpi-card-hyper'>
            <div class='kpi-title-hyper'>P&L Hyper 5M (Trend)</div>
            <div class='kpi-val-hyper' style='color: {col_5m};'>{sign_5m}{tot_5m:,.2f} €</div>
            <div class='kpi-sub-hyper' style='color: #cbd5e1;'>{len(trades_5m)} operazioni concluse</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<div style='margin-bottom: 14px;'></div>", unsafe_allow_html=True)

    tab_s30, tab_s5m, tab_s_all = st.tabs([
        f"⚡ Eseguiti 30S ({len(trades_30s)})",
        f"📊 Eseguiti 5M ({len(trades_5m)})",
        f"📜 Tutti i Trade ({len(trades_all)})"
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
            rows.append(
                f"<tr>"
                f"<td style='white-space: nowrap;'>{t.get('time_close', '--')}</td>"
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

    with tab_s30:
        _render_trades_table(trades_30s, "Nessuna operazione reale chiusa su Hyper 30S.")

    with tab_s5m:
        _render_trades_table(trades_5m, "Nessuna operazione reale chiusa su Hyper 5M.")

    with tab_s_all:
        _render_trades_table(trades_all, "Nessuna operazione registrata.")
        if trades_all:
            c_cl1, c_cl2 = st.columns([3, 1])
            with c_cl2:
                if st.button("🗑️ Azzera Archivio Sintesi", key="btn_clear_sintesi"):
                    mgr.clear_trades_history()
                    st.rerun()


def render_hyper_tab(conto_selezionato="DANY_DEMO"):
    """Pannello principale integrato per la tab HYPER nella Dashboard principale."""
    inject_hyper_css()

    conto_attivo = st.session_state.get("conto_selezionato") or conto_selezionato or "DANY_DEMO"

    engine_30s = HyperGoldEngine.get_instance(account_dir=conto_attivo)
    engine_5m = HyperGoldM1Engine.get_instance(account_dir=conto_attivo)

    is_30s_on = engine_30s.trading_enabled
    is_5m_on = engine_5m.trading_enabled

    tab_h30, tab_h5m, tab_sintesi = st.tabs([
        "⚡ Hyper 30s (Fast Scalping)" + (" 🟢 ATTIVO" if is_30s_on else ""),
        "📊 Hyper 5m (Trend Scalping)" + (" 🟢 ATTIVO" if is_5m_on else ""),
        "📋 Sintesi Hyp (Eseguiti)"
    ])

    with tab_h30:
        render_hyper_30s(conto_selezionato=conto_attivo, is_other_active=is_5m_on)

    with tab_h5m:
        render_hyper_5m(conto_selezionato=conto_attivo, is_other_active=is_30s_on)

    with tab_sintesi:
        render_sintesi_hyp(conto_selezionato=conto_attivo)

