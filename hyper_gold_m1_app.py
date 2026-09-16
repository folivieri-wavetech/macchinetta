import streamlit as st
import time
import datetime
from hyper_gold_m1_engine import HyperGoldM1Engine, CANDLE_SECONDS, WARMUP_BARS_KJ, WARMUP_BARS_TK, CORE_CONTRACTS, INC_CONTRACTS, MAX_INCREMENTS, INC_TP_PIPS, CORE_TP_PIPS

# Configurazione Pagina Streamlit
st.set_page_config(
    page_title="Hyper-Trading Spot Gold 1€ (M5)",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Istanza Engine Singleton
engine = HyperGoldM1Engine.get_instance()

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
    c_title, c_badges = st.columns([2.5, 1.5])
    with c_title:
        st.markdown("## ⚡ Hyper-Trading Spot Gold 1€ (Barre 5m • TK144 / KJ55)")
        st.caption("Filtro Macro TK 144 • Trigger KJ 55 • Core 5c + Max 5 Incr x 3c (TP +4 pip) • Totale max 20c • Porta 8505")

    with c_badges:
        st.markdown("<div style='display: flex; justify-content: flex-end; gap: 10px; align-items: center; margin-top: 8px;'>", unsafe_allow_html=True)
        if is_conn:
            st.markdown(f"<span class='badge-live' style='background: rgba(34, 197, 94, 0.15); color: #22c55e; border: 1px solid #22c55e;'>🟢 Lightstreamer LIVE ({total_ticks} tick)</span>", unsafe_allow_html=True)
        else:
            st.markdown("<span class='badge-live' style='background: rgba(239, 68, 68, 0.15); color: #ef4444; border: 1px solid #ef4444;'>🔴 In Connessione...</span>", unsafe_allow_html=True)

        if trading_on:
            st.markdown("<span class='badge-live' style='background: rgba(34, 197, 94, 0.2); color: #4ade80; border: 1px solid #4ade80;'>⚡ TRADING ATTIVO</span>", unsafe_allow_html=True)
        else:
            st.markdown("<span class='badge-live' style='background: rgba(148, 163, 184, 0.2); color: #cbd5e1; border: 1px solid #64748b;'>⏸️ IN PAUSA</span>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<hr style='margin: 10px 0 16px 0; border-color: #334155;' />", unsafe_allow_html=True)

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
            tp_core_val = pos.get("tp_price")
            if not tp_core_val:
                tp_core_val = round(pos["open_price"] + (CORE_TP_PIPS if pos["direction"] == "LONG" else -CORE_TP_PIPS), 2)
            sub_text = f"Core: {CORE_CONTRACTS}c @ {pos['open_price']:.2f} (TP: {tp_core_val:.2f}) | Incr: {num_inc}/{MAX_INCREMENTS}"
            st.markdown(f"""
            <div class='kpi-card'>
                <div class='kpi-title'>Esposizione a Mercato</div>
                <div class='kpi-val' style='color: {dir_col};'>{dir_icon} {pos['direction']} ({total_contracts}/20 Contr.)</div>
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

    # 2. INDICATORI DI MERCATO M5 (TK144 & KJ55)
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
        tk_str = f"{tk:.2f}" if tk else "--"
        kj_str = f"{kj:.2f}" if kj else "--"
        if live_mid and tk:
            regime = "🟢 BULLISH (SOLO LONG)" if live_mid > tk else "🔴 BEARISH (SOLO SHORT)"
            col_reg = "#22c55e" if live_mid > tk else "#ef4444"
        else:
            regime = "Inizializzazione..."
            col_reg = "#94a3b8"

        st.markdown(f"""
        <div class='kpi-card' style='padding: 8px 14px;'>
            <div class='kpi-title' style='display: flex; justify-content: space-between; align-items: center;'>
                <span>Livelli Chiave (M5)</span>
                <span style='color: {col_reg}; font-weight: 700; font-size: 0.76rem;'>{regime}</span>
            </div>
            <div style='display: flex; justify-content: space-around; align-items: center; margin-top: 5px;'>
                <div style='text-align: center;'>
                    <div style='font-size: 0.68rem; color: #94a3b8; font-weight: 600; text-transform: uppercase;'>MID LIVE</div>
                    <div style='font-size: 1.15rem; font-weight: 800; color: #22c55e;'>{px_str} €</div>
                </div>
                <div style='border-left: 1px solid #334155; height: 28px;'></div>
                <div style='text-align: center;'>
                    <div style='font-size: 0.68rem; color: #94a3b8; font-weight: 600; text-transform: uppercase;'>KJ 55</div>
                    <div style='font-size: 1.15rem; font-weight: 800; color: #FFD700;'>{kj_str}</div>
                </div>
                <div style='border-left: 1px solid #334155; height: 28px;'></div>
                <div style='text-align: center;'>
                    <div style='font-size: 0.68rem; color: #94a3b8; font-weight: 600; text-transform: uppercase;'>TK 144</div>
                    <div style='font-size: 1.15rem; font-weight: 800; color: #f97316;'>{tk_str}</div>
                </div>
            </div>
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
            sec_elapsed = min(300, int(time.time() - curr_bar_t))
        st.markdown(f"""
        <div class='kpi-card' style='padding: 10px 14px;'>
            <div class='kpi-title'>Timer Barra M5 (300s)</div>
            <div style='font-size: 1.30rem; font-weight: 700; color: #cbd5e1;'>{sec_elapsed}s / 300s</div>
            <div style='font-size: 0.75rem; color: #94a3b8;'>Chiusura barra: {300 - sec_elapsed}s</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<div style='margin-bottom: 14px;'></div>", unsafe_allow_html=True)

    # 3. STATO DATI STORICI M5
    if candles_count < WARMUP_BARS_TK:
        st.warning(f"⏳ **Caricamento storico M5 in corso:** {candles_count} / {WARMUP_BARS_TK} barre.")
    else:
        st.success(f"✅ **Dati M5 e Livelli Pronti:** {candles_count} barre storiche M5 caricate da IG REST. Kijun 55 ({kj_str}) e Tenkan 144 ({tk_str}) calcolate in tempo reale.")

    st.markdown("<div style='margin-bottom: 10px;'></div>", unsafe_allow_html=True)

    # 4. PANNELLO CONTROLLI (AVVIA / STOP / RESET)
    col_btn1, col_btn2, col_btn3 = st.columns([1.5, 1.5, 2])
    with col_btn1:
        if st.button("🟢 AVVIA TRADING M5", use_container_width=True, type="primary" if not trading_on else "secondary"):
            engine.set_trading(True)
            st.rerun()

    with col_btn2:
        if st.button("🛑 STOP TRADING M5", use_container_width=True, type="primary" if trading_on else "secondary"):
            engine.set_trading(False)
            st.rerun()

    with col_btn3:
        if st.button("🔄 RESET SALDO A 10.000 €", use_container_width=True):
            engine.reset_portfolio()
            st.rerun()

    st.markdown("<div style='margin-bottom: 18px;'></div>", unsafe_allow_html=True)

    # 5. TABELLA STORICO ESEGUITI E LOG OPERAZIONI
    col_t1, col_t2 = st.columns([2, 1.2])

    with col_t1:
        st.markdown("### 📋 Storico Operazioni Eseguite (M5)")
        if trades:
            rows_html = []
            for t in trades[:30]:
                col_pnl = "#22c55e" if t["pnl"] > 0 else ("#ef4444" if t["pnl"] < 0 else "#94a3b8")
                sign_p = f"+{t['pnl']:.2f}" if t["pnl"] > 0 else f"{t['pnl']:.2f}"
                if "🎯 TP" in t["action"]:
                    action_badge = "<span style='color: #38bdf8; font-weight: bold;'>🎯 " + t["action"] + "</span>"
                elif "➕ OPEN INC" in t["action"]:
                    action_badge = "<span style='color: #f59e0b; font-weight: bold;'>➕ " + t["action"] + "</span>"
                elif "CLOSE INC" in t["action"]:
                    action_badge = "<span style='color: #cbd5e1; font-weight: bold;'>⏹️ " + t["action"] + "</span>"
                elif "LONG" in t["action"]:
                    action_badge = "<span style='color: #22c55e; font-weight: bold;'>🟢 " + t["action"] + "</span>"
                elif "SHORT" in t["action"]:
                    action_badge = "<span style='color: #ef4444; font-weight: bold;'>🔴 " + t["action"] + "</span>"
                else:
                    action_badge = t["action"]

                close_str = f"{t['close_price']:.2f}" if t.get("close_price") else "--"
                rows_html.append(
                    f"<tr><td>{t['time']}</td><td>{action_badge}</td><td>{t['open_price']:.2f}</td><td>{close_str}</td><td style='color: {col_pnl}; font-weight: bold;'>{sign_p} €</td><td style='font-weight: 600;'>{t['balance']:,.2f} €</td><td style='color: #94a3b8; font-size: 0.78rem;'>{t['reason']}</td></tr>"
                )
            tbl_t = (
                "<table class='table-dark'>"
                "<thead><tr><th>Orario</th><th>Azione</th><th>Prezzo In</th><th>Prezzo Out</th><th>P&L</th><th>Saldo</th><th>Trigger</th></tr></thead>"
                f"<tbody>{''.join(rows_html)}</tbody>"
                "</table>"
            )
            st.markdown(tbl_t, unsafe_allow_html=True)
        else:
            st.info("Nessuna operazione ancora eseguita. Al primo segnale conforme al filtro TK144 e trigger KJ55 verrà registrato l'ordine.")

    with col_t2:
        st.markdown("### ⏱️ Ultime Barre Concluse (M5)")
        if candles_recent:
            rows_c = []
            for c in reversed(candles_recent):
                is_green = c["close"] >= c["open"]
                col_c = "#22c55e" if is_green else "#ef4444"
                dir_txt = "🟢 Bull" if is_green else "🔴 Bear"
                kj_v = f"{c['kj55']:.2f}" if c.get("kj55") else "--"
                rows_c.append(
                    f"<tr><td>{c['time']}</td><td style='color: {col_c}; font-weight: bold;'>{dir_txt}</td><td>{c['open']:.2f}</td><td>{c['close']:.2f}</td><td style='color: #38bdf8;'>{kj_v}</td></tr>"
                )
            tbl_c = (
                "<table class='table-dark'>"
                "<thead><tr><th>Ora</th><th>Tipo</th><th>Open</th><th>Close</th><th>KJ55</th></tr></thead>"
                f"<tbody>{''.join(rows_c)}</tbody>"
                "</table>"
            )
            st.markdown(tbl_c, unsafe_allow_html=True)
        else:
            st.info("In attesa di candele M5...")

# Render del desk
render_live_desk()
