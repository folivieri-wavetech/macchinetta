import os
import time
import json
import datetime
import streamlit as st
from dotenv import dotenv_values

try:
    from zoneinfo import ZoneInfo
    TZ_ITALIA = ZoneInfo("Europe/Rome")
except Exception:
    TZ_ITALIA = datetime.timezone(datetime.timedelta(hours=2))

def now_it():
    return datetime.datetime.now(TZ_ITALIA)

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))

def get_goldfinger_paths(conto):
    base = os.path.join(ROOT_DIR, conto)
    if not os.path.exists(base):
        base = os.path.join("/data", conto)
    return {
        "config": os.path.join(base, "config_goldfinger.json"),
        "stato": os.path.join(base, "stato_goldfinger.json"),
        "log": os.path.join(base, "goldfinger.log"),
        "stato_sistema": os.path.join(base, "stato_sistema.json"),
        "posizioni": os.path.join(base, "posizioni_aperte.json")
    }

def leggi_json_sicuro(path):
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def scrivi_json_sicuro(path, dati):
    try:
        tmp = f"{path}.tmp.{os.getpid()}"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(dati, f, indent=4)
        os.replace(tmp, path)
        return True
    except Exception:
        return False

def renderizza_tab_goldfinger(conto):
    paths = get_goldfinger_paths(conto)
    cfg = leggi_json_sicuro(paths["config"])
    stato = leggi_json_sicuro(paths["stato"])
    st_sys = leggi_json_sicuro(paths["stato_sistema"])
    pos_live = leggi_json_sicuro(paths["posizioni"])
    if not isinstance(pos_live, list):
        pos_live = []

    # 1. Calcolo Delta Live su Spot Gold
    tot_long = 0
    tot_short = 0
    for p in pos_live:
        inst = str(p.get("instrument", "")).upper()
        epic = str(p.get("epic", "")).upper()
        if "GOLD" in inst or "GOLD" in epic or "CFEGOLD" in epic:
            sz = int(float(p.get("size", 0)))
            d = p.get("direction", "").upper()
            if d in ("BUY", "LONG"):
                tot_long += sz
            elif d in ("SELL", "SHORT"):
                tot_short += sz

    delta_calcolato = max(0, tot_long - tot_short)

    # Prezzo Live Gold
    px_ba = st_sys.get("prezzi_bid_ask", {}).get("Spot Gold", {})
    bid_live = px_ba.get("bid")
    ask_live = px_ba.get("ask")
    if not bid_live and stato.get("ultimo_prezzo_bid"):
        bid_live = stato.get("ultimo_prezzo_bid")
        ask_live = stato.get("ultimo_prezzo_ask")

    # Stato del modulo
    is_attivo = cfg.get("attivo", False)
    stato_operativo = stato.get("stato_operativo", "IDLE")

    st.markdown("""
        <div style='display: flex; align-items: center; justify-content: space-between; margin-top: -10px; margin-bottom: 12px;'>
            <div>
                <h1 style='color: #FFD700; margin: 0; font-size: 1.8rem; font-weight: 800;'>🏆 Goldfinger - Paracadute e Copertura Spot Gold</h1>
                <p style='color: #94a3b8; margin: 2px 0 0 0; font-size: 0.88rem;'>Modulo chirurgico di difesa a scaglioni (Passo 6 pip) con incasso su rimbalzo e riarmo seconda ondata.</p>
            </div>
        </div>
    """, unsafe_allow_html=True)

    # Metriche principali
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        bid_str = f"{float(bid_live):.2f}" if bid_live else "--"
        ask_str = f"{float(ask_live):.2f}" if ask_live else "--"
        st.metric("🟡 Spot Gold Live", f"{bid_str} / {ask_str}")
    with c2:
        if not is_attivo:
            st.metric("🛡️ Stato Guardia", "🔴 INATTIVO", help="Il robot non è attivo e non effettua alcun ordine.")
        elif stato_operativo == "ARMED_ROLLOVER":
            st.metric("🛡️ Stato Guardia", "🟡 ARMATO (Rollover)", help="Pausa notturna prudenziale anti-spread (22:55 - 00:15). Operativo dalle 00:15.")
        else:
            st.metric("🛡️ Stato Guardia", "🟢 ATTIVO H24", help="Guardia attiva tick-by-tick a mercato.")
    with c3:
        st.metric("⚖️ Delta Scoperto IG", f"{delta_calcolato} mini", f"+{tot_long} L / -{tot_short} S")
    with c4:
        pnl_inc = stato.get("totale_incassato", 0.0)
        pnl_col = "normal" if pnl_inc == 0 else ("inverse" if pnl_inc < 0 else "off")
        st.metric("💰 Cash Incassato", f"{pnl_inc:+.2f} €", help="Totale liquidità netta incassata dai rimbalzi degli Short chiusi.")

    st.markdown("<hr style='margin: 10px 0; border-color: #334155;'>", unsafe_allow_html=True)

    col_ctrl, col_ladder = st.columns([5, 7])

    with col_ctrl:
        st.markdown("<h4 style='color: #38bdf8; margin-bottom: 8px;'>⚙️ Parametri di Ingresso</h4>", unsafe_allow_html=True)
        
        # Prezzo Livello 1 (Obbligatorio)
        def_pz1 = float(bid_live) if bid_live else 0.0
        saved_pz1 = cfg.get("livello_1_prezzo") or 0.0
        
        pz_l1 = st.number_input(
            "🎯 Prezzo Livello 1 (Partenza Discesa)",
            min_value=0.0,
            max_value=10000.0,
            value=float(saved_pz1) if saved_pz1 > 0 else (float(round(def_pz1 - 5.0, 2)) if def_pz1 > 0 else 0.0),
            step=1.0,
            format="%.2f",
            help="Prezzo a cui scatterà il primo scaglione SHORT a mercato."
        )

        cp, cs = st.columns(2)
        with cp:
            passo = st.number_input("Passo Scaglioni (pip)", min_value=1.0, max_value=50.0, value=float(cfg.get("passo_pip", 6.0)), step=1.0)
        with cs:
            size_u = st.number_input("Size Tranche (Interi)", min_value=1, max_value=20, value=int(cfg.get("size_scaglione", 3)), step=1)

        delta_input = st.number_input("Delta Contratti da Coprire", min_value=1, max_value=100, value=int(delta_calcolato if delta_calcolato > 0 else 15), step=1)

        st.markdown("<div style='margin-top: 15px;'></div>", unsafe_allow_html=True)

        if not is_attivo:
            if st.button("🚀 AVVIA GOLDFINGER", type="primary", use_container_width=True):
                # Blocco anti-errore
                if pz_l1 <= 0:
                    st.error("🛑 ERRORE DI SICUREZZA: Devi inserire un prezzo valido per il Livello 1 prima di avviare!")
                elif bid_live and abs(pz_l1 - float(bid_live)) > 200:
                    st.error(f"🛑 ERRORE: Il prezzo Livello 1 ({pz_l1:.2f}) è troppo distante dal prezzo attuale ({float(bid_live):.2f}). Verifica il valore!")
                else:
                    new_cfg = {
                        "attivo": True,
                        "livello_1_prezzo": float(pz_l1),
                        "passo_pip": float(passo),
                        "size_scaglione": int(size_u),
                        "delta_totale": int(delta_input),
                        "avviato_il": now_it().strftime("%Y-%m-%d %H:%M:%S")
                    }
                    scrivi_json_sicuro(paths["config"], new_cfg)
                    st.success(f"✅ GOLDFINGER AVVIATO: Guardia armata dal livello {pz_l1:.2f} in giù.")
                    time.sleep(0.5)
                    st.rerun()
        else:
            st.warning("⚠️ **GOLDFINGER È ATTIVO E OPERATIVO A MERCATO**")
            if st.button("🛑 STOP GOLDFINGER", type="secondary", use_container_width=True):
                new_cfg = cfg.copy()
                new_cfg["attivo"] = False
                new_cfg["fermato_il"] = now_it().strftime("%Y-%m-%d %H:%M:%S")
                scrivi_json_sicuro(paths["config"], new_cfg)
                st.info("🛑 GOLDFINGER ARRESTATO. Le posizioni aperte rimangono intatte sotto gestione manuale.")
                time.sleep(0.5)
                st.rerun()

    with col_ladder:
        st.markdown("<h4 style='color: #FFD700; margin-bottom: 8px;'>📋 Scaletta Scaglioni e Monitoraggio</h4>", unsafe_allow_html=True)
        
        scaglioni = stato.get("scaglioni", [])
        if not scaglioni and pz_l1 > 0:
            # Calcolo preview scala
            num_sc = max(1, int(delta_input) // int(size_u))
            sizes = [int(size_u)] * num_sc
            res = int(delta_input) - sum(sizes)
            if res > 0: sizes[-1] += res
            preview_sc = []
            for i, sz in enumerate(sizes):
                preview_sc.append({
                    "numero": i + 1,
                    "prezzo_target": round(pz_l1 - (i * passo), 2),
                    "size": sz,
                    "stato": "IN_ATTESA"
                })
            scaglioni = preview_sc

        if scaglioni:
            tab_rows = ""
            for s in scaglioni:
                st_code = s.get("stato", "IN_ATTESA")
                if st_code == "IN_ATTESA":
                    st_badge = "<span style='color: #94a3b8; font-weight: bold;'>⏳ In Attesa</span>"
                elif st_code == "APERTO":
                    st_badge = f"<span style='color: #38bdf8; font-weight: bold;'>🟢 APERTO @ {s.get('open_price', 0):.2f}</span>"
                elif st_code == "PROTETTO_BE":
                    st_badge = f"<span style='color: #22c55e; font-weight: bold;'>🛡️ BE+1 (SL: {s.get('sl_price', 0):.2f})</span>"
                elif st_code == "CHIUSO":
                    st_badge = "<span style='color: #FFD700; font-weight: bold;'>💰 Chiuso all'Incasso</span>"
                else:
                    st_badge = st_code
                
                pz_tgt = f"{s.get('prezzo_target', 0):.2f}"
                tab_rows += f"""
                    <tr style='border-bottom: 1px solid #334155;'>
                        <td style='padding: 6px; font-weight: bold;'>Scaglione {s.get('numero')}</td>
                        <td style='padding: 6px; color: #f8fafc;'>{pz_tgt}</td>
                        <td style='padding: 6px; color: #38bdf8; font-weight: bold;'>-{s.get('size')} mini</td>
                        <td style='padding: 6px;'>{st_badge}</td>
                    </tr>
                """

            st.markdown(f"""
                <table style='width: 100%; border-collapse: collapse; font-size: 0.85rem;'>
                    <thead>
                        <tr style='border-bottom: 2px solid #64748b; color: #94a3b8;'>
                            <th style='text-align: left; padding: 6px;'>Scaglione</th>
                            <th style='text-align: left; padding: 6px;'>Trigger Prezzo</th>
                            <th style='text-align: left; padding: 6px;'>Size Short</th>
                            <th style='text-align: left; padding: 6px;'>Stato</th>
                        </tr>
                    </thead>
                    <tbody>
                        {tab_rows}
                    </tbody>
                </table>
            """, unsafe_allow_html=True)
            
            min_disc = stato.get("minimo_discesa")
            if min_disc is not None:
                sgancio = round(min_disc + 7.0, 2)
                st.markdown(f"""
                    <div style='margin-top: 10px; padding: 8px 12px; background-color: #0f172a; border-left: 3px solid #38bdf8; border-radius: 4px; font-size: 0.82rem;'>
                        📉 <b>Minimo Discesa Corrente:</b> <span style='color: #f8fafc;'>{min_disc:.2f}</span> &nbsp;|&nbsp; 
                        💥 <b>Soglia Chiusura Rimbalzo (+7 pip):</b> <span style='color: #FFD700; font-weight: bold;'>{sgancio:.2f}</span>
                    </div>
                """, unsafe_allow_html=True)
        else:
            st.info("Imposta il Prezzo del Livello 1 a sinistra per visualizzare l'anteprima della scaletta.")

    # Storico Operazioni di Incasso
    st.markdown("<hr style='margin: 15px 0 10px 0; border-color: #334155;'>", unsafe_allow_html=True)
    with st.expander("📜 Registro Operazioni Chiuse da Goldfinger (Incassi e Stop)", expanded=False):
        storico = stato.get("storico_operazioni", [])
        if storico:
            r_html = ""
            for op in reversed(storico[-30:]):
                pnl = op.get("pnl", 0.0)
                pnl_c = "#22c55e" if pnl >= 0 else "#ef4444"
                r_html += f"""
                    <tr style='border-bottom: 1px solid #1e293b;'>
                        <td style='padding: 5px; color: #94a3b8;'>{op.get('data')}</td>
                        <td style='padding: 5px;'>Scaglione {op.get('scaglione')}</td>
                        <td style='padding: 5px;'>{op.get('size')} mini</td>
                        <td style='padding: 5px;'>{op.get('open'):.2f}</td>
                        <td style='padding: 5px;'>{op.get('close'):.2f}</td>
                        <td style='padding: 5px; color: {pnl_c}; font-weight: bold;'>{pnl:+.2f} €</td>
                        <td style='padding: 5px; color: #94a3b8;'>{op.get('motivo')}</td>
                    </tr>
                """
            st.markdown(f"""
                <table style='width: 100%; border-collapse: collapse; font-size: 0.82rem;'>
                    <thead>
                        <tr style='border-bottom: 2px solid #475569; color: #94a3b8;'>
                            <th style='text-align: left; padding: 5px;'>Data</th>
                            <th style='text-align: left; padding: 5px;'>Scaglione</th>
                            <th style='text-align: left; padding: 5px;'>Size</th>
                            <th style='text-align: left; padding: 5px;'>Open</th>
                            <th style='text-align: left; padding: 5px;'>Close</th>
                            <th style='text-align: left; padding: 5px;'>PnL Netto</th>
                            <th style='text-align: left; padding: 5px;'>Evento</th>
                        </tr>
                    </thead>
                    <tbody>
                        {r_html}
                    </tbody>
                </table>
            """, unsafe_allow_html=True)
        else:
            st.caption("Nessuna operazione ancora chiusa in questa sessione.")
