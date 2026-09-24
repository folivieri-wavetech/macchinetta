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

        /* Nuovi stili compatti per visualizzazione affiancata Hyper 5M */
        .inst-container-hyper {
            background: rgba(15, 23, 42, 0.45);
            border: 1px solid #334155;
            border-radius: 8px;
            padding: 10px 12px;
            margin-bottom: 8px;
        }
        .micro-card-hyper {
            background: linear-gradient(135deg, rgba(30, 41, 59, 0.7) 0%, rgba(15, 23, 42, 0.8) 100%);
            border: 1px solid #334155;
            border-radius: 7px;
            padding: 5px 6px;
            text-align: center;
            box-shadow: 0 2px 4px rgba(0, 0, 0, 0.15);
        }
        .micro-label-hyper {
            font-size: 0.60rem;
            color: #94a3b8;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.04em;
            margin-bottom: 2px;
            white-space: nowrap;
        }
        .micro-val-hyper {
            font-size: 1.05rem;
            font-weight: 800;
            line-height: 1.15;
            white-space: nowrap;
        }
        .micro-sub-hyper {
            font-size: 0.62rem;
            color: #cbd5e1;
            margin-top: 2px;
            white-space: nowrap;
        }
        .table-compact-hyper {
            width: 100%;
            border-collapse: collapse;
            font-size: 0.71rem;
        }
        .table-compact-hyper th {
            background-color: #1e293b;
            color: #94a3b8;
            padding: 4px 6px;
            text-align: left;
            font-size: 0.66rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.03em;
            border-bottom: 1px solid #475569;
        }
        .table-compact-hyper td {
            padding: 4px 6px;
            border-bottom: 1px solid #334155;
        }
        .btn-compact-hyper div.stButton > button {
            height: 30px !important;
            font-size: 0.74rem !important;
            font-weight: 700 !important;
            padding: 2px 6px !important;
            border-radius: 5px !important;
            white-space: nowrap !important;
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


def _render_instrument_column(engine, instr_type, conto_attivo, order_mgr):
    """Renderizza una colonna compatta ed elegante per un singolo strumento Hyper 5M."""
    if instr_type == "US500":
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
        is_feed_closed = is_us500_feed_suspended()
        is_trade_frozen = is_us500_trading_suspended()
    else:
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
        is_feed_closed = is_gold_feed_suspended()
        is_trade_frozen = is_gold_trading_suspended()

    with engine.lock:
        is_conn = engine.ls_connected
        live_mid = engine.live_mid
        total_ticks = engine.total_ticks
        kj = engine.kj55
        pos = engine.position
        increments = list(engine.increments)
        total_contracts = (pos.get("contracts", core_c) + sum(i.get("contracts", inc_c) for i in increments)) if pos else 0
        trading_on = engine.trading_enabled
        curr_bar_t = engine.curr_bar_start_t
        sig_act = getattr(engine, "signal_candle_active", False)
        sig_px = getattr(engine, "signal_stop_price", None)
        sig_ref = getattr(engine, "signal_ref_price", None)

    float_pnl = engine.get_floating_pnl()
    history_inst = order_mgr.get_trades_history(tf="5M", epic=epic_filter)
    session_realized_pnl = sum(float(t.get("pnl_eur", 0.0) or 0.0) for t in history_inst)
    num_closed = len(history_inst)

    # Badges Stato Connessione e Trading
    if is_conn:
        badge_ls = f"<span class='badge-live-hyper' style='background: rgba(34, 197, 94, 0.15); color: #22c55e; border: 1px solid #22c55e;'>🟢 LIVE ({total_ticks} t)</span>"
    elif is_feed_closed:
        badge_ls = "<span class='badge-live-hyper' style='background: rgba(100, 116, 139, 0.2); color: #94a3b8; border: 1px solid #64748b;'>💤 Feed Chiuso</span>"
    else:
        badge_ls = "<span class='badge-live-hyper' style='background: rgba(239, 68, 68, 0.15); color: #ef4444; border: 1px solid #ef4444;'>🔴 Offline</span>"

    if is_trade_frozen:
        badge_st = "<span class='badge-live-hyper' style='background: rgba(234, 179, 8, 0.2); color: #facc15; border: 1px solid #facc15;'>🌙 CONGELATO</span>"
    elif trading_on:
        badge_st = "<span class='badge-live-hyper' style='background: rgba(34, 197, 94, 0.2); color: #4ade80; border: 1px solid #4ade80;'>⚡ ATTIVO</span>"
    else:
        badge_st = "<span class='badge-live-hyper' style='background: rgba(148, 163, 184, 0.2); color: #cbd5e1; border: 1px solid #64748b;'>⏸️ PAUSA</span>"

    # Intestazione compatta dell'Asset
    st.markdown(f"""
    <div style='display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; padding-bottom: 4px; border-bottom: 1px solid #334155;'>
        <div style='display: flex; align-items: center; gap: 6px;'>
            <span style='font-size: 0.95rem; font-weight: 800; color: #f8fafc;'>{instr_name}</span>
            <span style='background: rgba(245, 158, 11, 0.20); color: #f59e0b; border: 1px solid #f59e0b; padding: 1px 5px; border-radius: 4px; font-size: 0.68rem; font-weight: 800;'>5M</span>
        </div>
        <div style='display: flex; gap: 4px; align-items: center;'>
            {badge_ls}{badge_st}
        </div>
    </div>
    """, unsafe_allow_html=True)

    # 4 Micro cards: Prezzo, KJ, Distanza e Countdown Barra
    px_str = f"{live_mid:.2f}" if live_mid else "--"
    kj_str = f"{kj:.2f}" if kj else "--"
    dist_str = f"{abs(live_mid - kj):.2f}{unit_lbl}" if (live_mid and kj) else "--"

    sec_elapsed = min(300, int(time.time() - curr_bar_t)) if curr_bar_t else 0
    sec_left = max(0, 300 - sec_elapsed)
    sec_left_str = f"{sec_left // 60:02d}:{sec_left % 60:02d}"

    st.markdown(f"""
    <div style='display: grid; grid-template-columns: repeat(4, 1fr); gap: 5px; margin-bottom: 7px;'>
        <div class='micro-card-hyper'>
            <div class='micro-label-hyper'>MID LIVE</div>
            <div class='micro-val-hyper' style='color: #22c55e;'>{px_str}</div>
        </div>
        <div class='micro-card-hyper'>
            <div class='micro-label-hyper'>KJ 55 (S&R)</div>
            <div class='micro-val-hyper' style='color: #FFD700;'>{kj_str}</div>
        </div>
        <div class='micro-card-hyper'>
            <div class='micro-label-hyper'>DISTANZA</div>
            <div class='micro-val-hyper' style='color: #38bdf8;'>{dist_str}</div>
        </div>
        <div class='micro-card-hyper'>
            <div class='micro-label-hyper'>BARRA M5</div>
            <div class='micro-val-hyper' style='color: #cbd5e1; font-family: monospace;'>{sec_left_str}</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Mini Barra Stato: Esposizione, Flottante, Sessione e Candela Segnale
    if pos:
        dir_col = "#22c55e" if pos["direction"] == "LONG" else "#ef4444"
        dir_icon = "🟢" if pos["direction"] == "LONG" else "🔴"
        pos_str = f"<span style='color: {dir_col}; font-weight: 700;'>{dir_icon} {pos['direction']} {total_contracts}c</span> <span style='font-size: 0.68rem; color: #94a3b8;'>@{pos['open_price']:.2f}</span>"
    else:
        pos_str = "<span style='color: #94a3b8; font-weight: 600;'>⚪ FLAT (0c)</span>"

    col_fl = "#22c55e" if float_pnl > 0 else ("#ef4444" if float_pnl < 0 else "#94a3b8")
    sign_fl = "+" if float_pnl > 0 else ""
    fl_str = f"<span style='color: {col_fl}; font-weight: 700;'>{sign_fl}{float_pnl:,.2f} €</span>"

    col_sess = "#22c55e" if session_realized_pnl > 0 else ("#ef4444" if session_realized_pnl < 0 else "#94a3b8")
    sign_sess = "+" if session_realized_pnl > 0 else ""
    sess_str = f"<span style='color: {col_sess}; font-weight: 700;'>{sign_sess}{session_realized_pnl:,.2f} €</span> <span style='font-size: 0.65rem; color: #64748b;'>({num_closed} op)</span>"

    if sig_act and sig_px is not None:
        if sig_ref is None:
            if pos and pos.get("direction") == "LONG":
                sig_ref = round(sig_px + sig_offset, 2)
            elif pos and pos.get("direction") == "SHORT":
                sig_ref = round(sig_px - sig_offset, 2)
            else:
                sig_ref = sig_px
        sign_op = "-" if (pos and pos.get("direction") == "LONG") else "+"
        sig_html = f"<div style='font-size: 0.68rem; color: #f97316; font-weight: 700; margin-top: 3px;'>⚠️ Candela Segnale: <span style='color: #fb923c; font-weight: 800;'>{sig_px:.2f}</span> ({sig_ref:.2f} {sign_op} {sig_offset:.0f}{unit_lbl})</div>"
    else:
        sig_html = "<div style='font-size: 0.68rem; color: #64748b; font-weight: 600; margin-top: 3px;'>⚠️ Candela Segnale: <span style='color: #94a3b8;'>---</span></div>"

    st.markdown(f"""
    <div style='background: rgba(15, 23, 42, 0.5); border: 1px solid #334155; border-radius: 6px; padding: 5px 8px; margin-bottom: 7px;'>
        <div style='display: flex; justify-content: space-between; align-items: center; font-size: 0.73rem;'>
            <div>Pos: {pos_str}</div>
            <div>Latente: {fl_str}</div>
            <div>Tot. P/L: {sess_str}</div>
        </div>
        {sig_html}
    </div>
    """, unsafe_allow_html=True)

    # Pulsanti di Controllo compatti
    c_b1, c_b2, c_b3 = st.columns([1.1, 1.1, 1.0])
    with c_b1:
        st.markdown("<div class='btn-start-hyper btn-compact-hyper'>", unsafe_allow_html=True)
        if st.button("🟢 AVVIA 5M", key=f"btn_start_m5_{btn_sfx}", disabled=trading_on, use_container_width=True):
            st.session_state["hyper_target_subtab"] = "5m"
            engine.set_trading(True)
            st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

    with c_b2:
        st.markdown("<div class='btn-stop-hyper btn-compact-hyper'>", unsafe_allow_html=True)
        if st.button("🔴 STOP 5M", key=f"btn_stop_m5_{btn_sfx}", disabled=(not trading_on), use_container_width=True):
            st.session_state["hyper_target_subtab"] = "5m"
            engine.set_trading(False)
            st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

    with c_b3:
        st.markdown("<div class='btn-azzera-hyper btn-compact-hyper'>", unsafe_allow_html=True)
        if st.button("🔄 Azzera", key=f"btn_clr_trades_m5_{btn_sfx}", help="Azzera lo storico delle operazioni chiuse e il P&L di sessione per questo strumento", use_container_width=True):
            st.session_state["hyper_target_subtab"] = "5m"
            order_mgr.clear_trades_history(tf="5M", epic=epic_filter)
            engine.clear_session_trades()
            st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

    # Posizioni in Portafoglio
    st.markdown("<div style='margin-top: 8px; margin-bottom: 3px; font-size: 0.77rem; font-weight: 700; color: #e2e8f0;'>💼 Posizioni in Portafoglio</div>", unsafe_allow_html=True)
    if pos:
        dir_pos = pos["direction"]
        dir_col = "#22c55e" if dir_pos == "LONG" else "#ef4444"
        dir_badge = f"<span style='color: {dir_col}; font-weight: 700;'>{'🟢' if dir_pos == 'LONG' else '🔴'} Core</span>"
        ts_target = round((pos["open_price"] + ts_trig) if dir_pos == "LONG" else (pos["open_price"] - ts_trig), 2)
        ts_sign = "+" if dir_pos == "LONG" else "-"
        ts_cell = f"<span style='color: #38bdf8; font-weight: 600;'>{ts_target:.2f}</span> <span style='font-size: 0.63rem; color: #94a3b8;'>({ts_sign}{ts_trig:.0f}{unit_lbl})</span>"

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
            f"<td style='text-align: right; color: {col_core_pnl}; font-weight: 700;'>{sign_core}{core_pnl_val:,.2f} €</td>"
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
            tp_cell = f"<span style='color: #38bdf8; font-weight: 700;'>{tp_val:.2f}</span>"

            p_rows.append(
                f"<tr>"
                f"<td><span style='color: #f59e0b; font-weight: 600;'>➕ Inc #{idx}</span></td>"
                f"<td style='text-align: center; font-weight: 700;'>{inc.get('contracts', inc_c)}c</td>"
                f"<td style='text-align: right; font-weight: 600;'>{inc['open_price']:.2f}</td>"
                f"<td style='text-align: right;'>{tp_cell}</td>"
                f"<td style='text-align: right; color: {col_inc_pnl}; font-weight: 700;'>{sign_inc}{inc_pnl_val:,.2f} €</td>"
                f"</tr>"
            )

        col_tot_pnl = "#22c55e" if float_pnl >= 0 else "#ef4444"
        sign_tot = "+" if float_pnl >= 0 else ""
        p_rows.append(
            f"<tr style='background: rgba(30, 41, 59, 0.9); border-top: 1px solid #475569; font-weight: 800; font-size: 0.71rem;'>"
            f"<td style='color: #f8fafc;'>TOT</td>"
            f"<td style='text-align: center; color: #38bdf8;'>{total_contracts}c</td>"
            f"<td style='text-align: right; color: #94a3b8;'>Live: {px_str}</td>"
            f"<td style='text-align: right; color: #64748b;'>--</td>"
            f"<td style='text-align: right; color: {col_tot_pnl};'>{sign_tot}{float_pnl:,.2f} €</td>"
            f"</tr>"
        )

        st.markdown(f"""
        <table class='table-compact-hyper'>
            <thead>
                <tr><th>Pos</th><th style='text-align: center;'>Size</th><th style='text-align: right;'>Open</th><th style='text-align: right;'>TP/TS</th><th style='text-align: right;'>P&L</th></tr>
            </thead>
            <tbody>{''.join(p_rows)}</tbody>
        </table>
        """, unsafe_allow_html=True)
    else:
        st.markdown("<div style='background: rgba(15, 23, 42, 0.3); border: 1px dashed #334155; border-radius: 5px; padding: 5px 8px; font-size: 0.69rem; color: #64748b; text-align: center;'>⚪ Nessuna posizione aperta (Flat)</div>", unsafe_allow_html=True)

    # Storico Operazioni Recenti
    st.markdown("<div style='margin-top: 8px; margin-bottom: 3px; font-size: 0.77rem; font-weight: 700; color: #e2e8f0;'>📋 Storico Operazioni Recenti (5M)</div>", unsafe_allow_html=True)
    if history_inst:
        rows_h = []
        for t in history_inst[:6]:
            pnl_val = float(t.get("pnl_eur", 0.0) or 0.0)
            col_p = "#22c55e" if pnl_val > 0 else ("#ef4444" if pnl_val < 0 else "#94a3b8")
            sign_p = f"+{pnl_val:.2f}" if pnl_val > 0 else f"{pnl_val:.2f}"
            lbl = t.get("label", "Trade")
            rsn = t.get("reason", "")
            if "PARACADUTE" in rsn.upper():
                badge_act = f"<span style='color: #f87171; font-weight: bold;'>🪂 {lbl}</span>"
            elif "TP" in rsn.upper() or "TP" in lbl.upper():
                badge_act = f"<span style='color: #38bdf8; font-weight: bold;'>🎯 {lbl}</span>"
            elif "TRAILING" in rsn.upper() or "TS" in rsn.upper():
                badge_act = f"<span style='color: #4ade80; font-weight: bold;'>🏆 TS</span>"
            else:
                badge_act = f"<span style='color: #cbd5e1; font-weight: bold;'>⏹️ {lbl}</span>"

            t_str = t.get("time_close", "").split(" ")[-1] if " " in t.get("time_close", "") else t.get("time_close", "")

            rows_h.append(
                f"<tr>"
                f"<td style='white-space: nowrap;'>{t_str}</td>"
                f"<td style='white-space: nowrap;'>{badge_act}</td>"
                f"<td style='text-align: right; white-space: nowrap;'>{t['open_price']:.2f}</td>"
                f"<td style='text-align: right; white-space: nowrap;'>{t['close_price']:.2f}</td>"
                f"<td style='text-align: right; color: {col_p}; font-weight: 700; white-space: nowrap;'>{sign_p}&nbsp;€</td>"
                f"</tr>"
            )
        st.markdown(f"""
        <table class='table-compact-hyper'>
            <thead>
                <tr><th>Ora</th><th>Pos</th><th style='text-align: right;'>In</th><th style='text-align: right;'>Out</th><th style='text-align: right;'>P&L</th></tr>
            </thead>
            <tbody>{''.join(rows_h)}</tbody>
        </table>
        """, unsafe_allow_html=True)
    else:
        st.markdown("<div style='background: rgba(15, 23, 42, 0.3); border: 1px dashed #334155; border-radius: 5px; padding: 5px 8px; font-size: 0.69rem; color: #64748b; text-align: center;'>Nessuna operazione ancora chiusa in sessione.</div>", unsafe_allow_html=True)

    # Expander Regole M5
    with st.expander(f"⚙️ Assetto & Regole M5 {instr_name}", expanded=False):
        st.markdown(f"""
        <div style='background: rgba(15, 23, 42, 0.6); border: 1px solid #334155; border-radius: 5px; padding: 5px 8px; font-size: 0.70rem; line-height: 1.4;'>
            <div style='color: #f59e0b; font-weight: 700; margin-bottom: 2px;'>🎯 Parametri {instr_name}:</div>
            <div>• <b>Regime</b>: LONG se Chiusura > KJ55 | SHORT se Chiusura < KJ55</div>
            <div>• <b>Ingresso Core</b>: <span style='color: #4ade80; font-weight: 600;'>{core_c}c</span> su stacco Prezzo - KJ >= 2{unit_lbl}</div>
            <div>• <b>Incrementi Pullback</b>: fino a <b>{max_inc}</b> da <span style='color: #f59e0b; font-weight: 600;'>{inc_c}c</span> (distanza <= 5{unit_lbl}, TP +{inc_tp:.0f}{unit_lbl})</div>
            <div>• <b>Trailing Stop Core</b>: Trigger +{ts_trig:.0f}{unit_lbl}, Lock +{ts_lock:.0f}{unit_lbl}, Step {ts_stp:.0f}{unit_lbl}</div>
            <div>• <b>Protezioni</b>: Paracadute ±{parachute_p:.0f}{unit_lbl} • Candela Segnale ±{sig_offset:.0f}{unit_lbl}</div>
        </div>
        """, unsafe_allow_html=True)


@st.fragment(run_every=2)
def render_hyper_5m(conto_selezionato="DANY_DEMO", **kwargs):
    """Visualizzazione unificata e affiancata di Spot Gold 1€ e US 500 Cash 1€ su timeframe 5M."""
    conto_attivo = st.session_state.get("conto_selezionato") or conto_selezionato or "DANY_DEMO"
    nome_clean = conto_attivo.replace("_DEMO", "").replace("_REALE", "")

    # Motori dei due strumenti 5M
    engine_gold = HyperGoldM5Engine.get_instance(account_dir=conto_attivo)
    engine_us500 = HyperUS500M5Engine.get_instance(account_dir=conto_attivo)

    # Dati patrimoniali sincronizzati
    acc_data = get_sidebar_account_data(conto_attivo)

    # Flottanti live
    float_gold = engine_gold.get_floating_pnl()
    float_us500 = engine_us500.get_floating_pnl()
    tot_float = float_gold + float_us500

    # Order manager & Storico 5M Reale IG
    order_mgr = HyperOrderManager.get_instance(conto_attivo)
    hist_gold = order_mgr.get_trades_history(tf="5M", epic="CS.D.CFDGOLD.CFD.IP")
    hist_us500 = order_mgr.get_trades_history(tf="5M", epic="IX.D.SPTRD.IBE.IP")
    real_gold = sum(float(t.get("pnl_eur", 0.0) or 0.0) for t in hist_gold)
    real_us500 = sum(float(t.get("pnl_eur", 0.0) or 0.0) for t in hist_us500)
    tot_real = real_gold + real_us500
    tot_closed = len(hist_gold) + len(hist_us500)

    # Contratti ed esposizione aggregata
    with engine_gold.lock:
        pos_g = engine_gold.position
        inc_g = list(engine_gold.increments)
        c_gold = (pos_g.get("contracts", CORE_CONTRACTS_5M) + sum(i.get("contracts", INC_CONTRACTS_5M) for i in inc_g)) if pos_g else 0
        dir_gold = pos_g["direction"] if pos_g else "FLAT"

    with engine_us500.lock:
        pos_u = engine_us500.position
        inc_u = list(engine_us500.increments)
        c_us500 = (pos_u.get("contracts", 4) + sum(i.get("contracts", 2) for i in inc_u)) if pos_u else 0
        dir_us500 = pos_u["direction"] if pos_u else "FLAT"

    tot_hyper_margin = (c_gold * 220.0) + (c_us500 * 400.0)

    # Banner KPI di Sintesi Account (4 colonne proporzionate ed eleganti)
    k1, k2, k3, k4 = st.columns(4)
    with k1:
        st.markdown(f"""
        <div class='kpi-card-hyper' style='padding: 8px 12px;'>
            <div class='kpi-title-hyper'>Capitale Conto ({nome_clean})</div>
            <div class='kpi-val-hyper' style='color: #FFD700; font-size: 1.25rem;'>{acc_data['saldo_str']} €</div>
            <div class='kpi-sub-hyper' style='color: #94a3b8;'>Disp: <b style='color: #4ade80;'>{acc_data['disp_str']} €</b> | Marg: <b style='color: #f59e0b;'>{acc_data['marg_str']} €</b></div>
        </div>
        """, unsafe_allow_html=True)

    with k2:
        col_real = "#22c55e" if tot_real >= 0 else "#ef4444"
        sign_real = "+" if tot_real > 0 else ""
        pnl_real_str = f"{tot_real:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        st.markdown(f"""
        <div class='kpi-card-hyper' style='padding: 8px 12px;'>
            <div class='kpi-title-hyper'>P&L Sessione Hyper 5M</div>
            <div class='kpi-val-hyper' style='color: {col_real}; font-size: 1.25rem;'>{sign_real}{pnl_real_str} €</div>
            <div class='kpi-sub-hyper' style='color: #cbd5e1;'>Gold {real_gold:+.2f} € • US500 {real_us500:+.2f} €</div>
        </div>
        """, unsafe_allow_html=True)

    with k3:
        col_float = "#22c55e" if tot_float > 0 else ("#ef4444" if tot_float < 0 else "#94a3b8")
        sign_fl = "+" if tot_float > 0 else ""
        st.markdown(f"""
        <div class='kpi-card-hyper' style='padding: 8px 12px;'>
            <div class='kpi-title-hyper'>P&L Latente Hyper (Live)</div>
            <div class='kpi-val-hyper' style='color: {col_float}; font-size: 1.25rem;'>{sign_fl}{tot_float:,.2f} €</div>
            <div class='kpi-sub-hyper' style='color: #cbd5e1;'>Gold {float_gold:+.2f} € • US500 {float_us500:+.2f} €</div>
        </div>
        """, unsafe_allow_html=True)

    with k4:
        col_g = "#22c55e" if dir_gold == "LONG" else ("#ef4444" if dir_gold == "SHORT" else "#94a3b8")
        col_u = "#22c55e" if dir_us500 == "LONG" else ("#ef4444" if dir_us500 == "SHORT" else "#94a3b8")
        st.markdown(f"""
        <div class='kpi-card-hyper' style='padding: 8px 12px;'>
            <div class='kpi-title-hyper'>Esposizione Hyper 5M</div>
            <div class='kpi-val-hyper' style='font-size: 0.88rem; line-height: 1.25;'>
                <div style='white-space: nowrap;'><span style='color: #FFD700; font-weight: 700;'>Gold:</span> <span style='color: {col_g};'>{dir_gold} ({c_gold}c)</span></div>
                <div style='white-space: nowrap;'><span style='color: #FFD700; font-weight: 700;'>US500:</span> <span style='color: {col_u};'>{dir_us500} ({c_us500}c)</span></div>
            </div>
            <div class='kpi-sub-hyper' style='color: #94a3b8;'>Margine Hyper impegnato: <b style='color: #f59e0b;'>{tot_hyper_margin:,.0f} €</b></div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<div style='margin-bottom: 10px;'></div>", unsafe_allow_html=True)

    # Due Colonne Affiancate: Sinistra Spot Gold 1€, Destra US 500 Cash 1€
    col_gold, col_us500 = st.columns(2, gap="medium")
    with col_gold:
        _render_instrument_column(engine_gold, "GOLD", conto_attivo, order_mgr)

    with col_us500:
        _render_instrument_column(engine_us500, "US500", conto_attivo, order_mgr)


def render_sintesi_hyp(conto_selezionato="DANY_DEMO", is_us500=False, **kwargs):
    """Visualizza il riepilogo analitico delle operazioni reali chiuse su IG su Hyper 5M."""
    conto_attivo = st.session_state.get("conto_selezionato") or conto_selezionato or "DANY_DEMO"
    nome_clean = conto_attivo.replace("_DEMO", "").replace("_REALE", "")
    mgr = HyperOrderManager.get_instance(conto_attivo)

    trades_all = mgr.get_trades_history()
    # Filtriamo per 5M (escludendo eventuali residui 30S)
    trades_5m = [t for t in trades_all if t.get("tf") == "5M"]
    trades_active = trades_5m if trades_5m else [t for t in trades_all if t.get("tf") != "30S"]

    trades_us500 = [t for t in trades_active if ("SPTRD" in t.get("epic", "").upper() or "US500" in t.get("label", "").upper())]
    trades_gold = [t for t in trades_active if ("GOLD" in t.get("epic", "").upper() or "GOLD" in t.get("label", "").upper() or not ("SPTRD" in t.get("epic", "").upper() or "US500" in t.get("label", "").upper()))]

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

        # Raggruppa i giorni in ordine di apparizione per alternare i colori a giorni alterni
        unique_days = []
        for t in trade_list:
            tc = str(t.get("time_close", "")).strip()
            day = tc.split(" ")[0] if " " in tc else (tc[:10] if len(tc) >= 10 else tc)
            if day and day != "--" and day not in unique_days:
                unique_days.append(day)
        day_color_map = {day: ("#fb923c" if idx % 2 == 0 else "#f8fafc") for idx, day in enumerate(unique_days)}

        rows = []
        for t in trade_list:
            tc = str(t.get("time_close", "--")).strip()
            day = tc.split(" ")[0] if " " in tc else (tc[:10] if len(tc) >= 10 else tc)
            date_color = day_color_map.get(day, "#f8fafc")

            pnl = float(t.get("pnl_eur", 0.0) or 0.0)
            col_p = "#22c55e" if pnl > 0 else ("#ef4444" if pnl < 0 else "#94a3b8")
            sign = "+" if pnl > 0 else ""
            d_col = "#22c55e" if t.get("direction") == "LONG" else "#ef4444"
            is_us = ("SPTRD" in t.get("epic", "").upper() or "US500" in t.get("label", "").upper())
            inst_badge = "<span style='color: #38bdf8; font-weight: 700;'>🇺🇸 US500</span>" if is_us else "<span style='color: #FFD700; font-weight: 700;'>🪙 Gold</span>"
            rows.append(
                f"<tr>"
                f"<td style='white-space: nowrap; color: {date_color}; font-weight: 600;'>{t.get('time_close', '--')}</td>"
                f"<td style='white-space: nowrap;'>{inst_badge}</td>"
                f"<td style='text-align: center; color: {d_col}; font-weight: 700;'>{t.get('direction', '--')}</td>"
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
                    <th style='text-align: center;'>Direzione</th>
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

    engine_gold_5m = HyperGoldM5Engine.get_instance(account_dir=conto_attivo)
    engine_us500_5m = HyperUS500M5Engine.get_instance(account_dir=conto_attivo)
    is_5m_on = engine_gold_5m.trading_enabled or engine_us500_5m.trading_enabled

    tab_h5m, tab_sintesi = st.tabs([
        "📊 Hyper 5M (Trend Scalping)" + (" 🟢 ATTIVO" if is_5m_on else ""),
        "📋 Sintesi"
    ])

    with tab_h5m:
        render_hyper_5m(conto_selezionato=conto_attivo)

    with tab_sintesi:
        render_sintesi_hyp(conto_selezionato=conto_attivo)

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
                        }} else if (txt.includes("Sintesi") && !t._hyper_listener) {{
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
                            if (txt.includes("Sintesi")) {{
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
