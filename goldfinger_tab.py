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

def calcola_livello_chirurgico_gold(conto, px_live=None):
    """
    Calcola il livello chirurgico di partenza Short analizzando l'intera struttura delle 55 candele H1:
    - Asse di equilibrio: TK21 H1 (21 ore).
    - Pavimento dinamico (clustering): confronta i minimi a 9h, 21h e 55h. Se il minimo a 55h è vicino
      a quello delle 21h (entro 12 pip), assume il minimo a 55h come vero fondo; altrimenti usa il minimo a 21h.
    - Zero chiamate IG (solo file locali).
    """
    candidates = [
        os.path.join(ROOT_DIR, conto, "candele_Spot_Gold_HOUR.json"),
        os.path.join("/data", conto, "candele_Spot_Gold_HOUR.json"),
        os.path.join(ROOT_DIR, "candele_Spot_Gold_HOUR.json"),
        os.path.join("/data", "candele_Spot_Gold_HOUR.json"),
        os.path.join(ROOT_DIR, "FIORDOK_DEMO", "candele_Spot_Gold_HOUR.json"),
        os.path.join("/data", "FIORDOK_DEMO", "candele_Spot_Gold_HOUR.json"),
        os.path.join(ROOT_DIR, "DANY_DEMO", "candele_Spot_Gold_HOUR.json"),
        os.path.join("/data", "DANY_DEMO", "candele_Spot_Gold_HOUR.json"),
    ]
    candele = []
    for p in candidates:
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    d = json.load(f)
                    if isinstance(d, list) and len(d) >= 21:
                        candele = d
                        break
            except Exception:
                pass
                
    if not candele or len(candele) < 21:
        return None, None, None, None, None, None, None
        
    # Finestra 55 ore
    candele_55 = candele[-55:] if len(candele) >= 55 else candele
    lows_55 = [float(c.get('lowPrice', {}).get('bid') or c.get('lowPrice', {}).get('ask') or c.get('low')) for c in candele_55 if (c.get('lowPrice') or c.get('low'))]
    l55 = min(lows_55) if lows_55 else 0.0

    # Finestra 21 ore
    candele_21 = candele[-21:]
    highs_21 = [float(c.get('highPrice', {}).get('bid') or c.get('highPrice', {}).get('ask') or c.get('high')) for c in candele_21 if (c.get('highPrice') or c.get('high'))]
    lows_21 = [float(c.get('lowPrice', {}).get('bid') or c.get('lowPrice', {}).get('ask') or c.get('low')) for c in candele_21 if (c.get('lowPrice') or c.get('low'))]
    if not highs_21 or not lows_21:
        return None, None, None, None, None, None, None
    h21 = max(highs_21)
    l21 = min(lows_21)
    tk21 = (h21 + l21) / 2.0

    # Finestra 9 ore
    candele_9 = candele[-9:]
    lows_9 = [float(c.get('lowPrice', {}).get('bid') or c.get('lowPrice', {}).get('ask') or c.get('low')) for c in candele_9 if (c.get('lowPrice') or c.get('low'))]
    l9 = min(lows_9) if lows_9 else l21

    # Clustering intelligente dei Minimi:
    # Se il minimo a 55h dista meno di 12 pip dal minimo a 21h, il vero supporto solido è L55.
    # Se invece L55 è più lontano di 12 pip, il floor di riferimento operativo è L21.
    if (l21 - l55) <= 12.0:
        min_strutturale = l55
    else:
        min_strutturale = l21

    # Calcolo sintetico del Livello Chirurgico Consigliato:
    if px_live and float(px_live) > tk21:
        suggerito = round(tk21, 2)
    else:
        # Ponderazione concordata: 60% Floor strutturale selezionato + 40% TK21
        suggerito = round((min_strutturale * 0.60) + (tk21 * 0.40), 2)

    return suggerito, round(tk21, 2), round(min_strutturale, 2), round(h21, 2), round(l55, 2), round(l21, 2), round(l9, 2)

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

    # Metriche principali compatte
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        bid_str = f"{float(bid_live):.2f}" if bid_live else "--"
        ask_str = f"{float(ask_live):.2f}" if ask_live else "--"
        st.markdown(
            f"<div style='background: #0f172a; border: 1px solid #1e293b; border-radius: 6px; padding: 8px 12px; min-height: 64px;'>"
            f"<div style='color: #94a3b8; font-size: 0.72rem; font-weight: 600; text-transform: uppercase;'>🟡 Spot Gold Live</div>"
            f"<div style='color: #f8fafc; font-size: 1.05rem; font-weight: 700; margin-top: 3px;'>{bid_str} / {ask_str}</div>"
            f"<div style='color: #64748b; font-size: 0.68rem; margin-top: 2px;'>Prezzo Bid / Ask IG</div>"
            f"</div>",
            unsafe_allow_html=True
        )
    with c2:
        if not is_attivo:
            st_text = "🔴 INATTIVO"
            st_desc = "Robot fermo"
            st_col = "#ef4444"
        elif stato_operativo == "ARMED_ROLLOVER":
            st_text = "🟡 ARMATO (Rollover)"
            st_desc = "Pausa serale 22:55-00:15"
            st_col = "#eab308"
        else:
            st_text = "🟢 ATTIVO H24"
            st_desc = "Guardia a mercato"
            st_col = "#22c55e"
        st.markdown(
            f"<div style='background: #0f172a; border: 1px solid #1e293b; border-radius: 6px; padding: 8px 12px; min-height: 64px;'>"
            f"<div style='color: #94a3b8; font-size: 0.72rem; font-weight: 600; text-transform: uppercase;'>🛡️ Stato Guardia</div>"
            f"<div style='color: {st_col}; font-size: 1.05rem; font-weight: 700; margin-top: 3px;'>{st_text}</div>"
            f"<div style='color: #64748b; font-size: 0.68rem; margin-top: 2px;'>{st_desc}</div>"
            f"</div>",
            unsafe_allow_html=True
        )
    with c3:
        st.markdown(
            f"<div style='background: #0f172a; border: 1px solid #1e293b; border-radius: 6px; padding: 8px 12px; min-height: 64px;'>"
            f"<div style='color: #94a3b8; font-size: 0.72rem; font-weight: 600; text-transform: uppercase;'>⚖️ Delta Scoperto IG</div>"
            f"<div style='color: #38bdf8; font-size: 1.05rem; font-weight: 700; margin-top: 3px;'>{delta_calcolato} mini</div>"
            f"<div style='color: #64748b; font-size: 0.68rem; margin-top: 2px;'>+{tot_long} L / -{tot_short} S</div>"
            f"</div>",
            unsafe_allow_html=True
        )
    with c4:
        pnl_inc = stato.get("totale_incassato", 0.0)
        pnl_col = "#94a3b8" if pnl_inc == 0 else ("#22c55e" if pnl_inc > 0 else "#ef4444")
        st.markdown(
            f"<div style='background: #0f172a; border: 1px solid #1e293b; border-radius: 6px; padding: 8px 12px; min-height: 64px;'>"
            f"<div style='color: #94a3b8; font-size: 0.72rem; font-weight: 600; text-transform: uppercase;'>💰 Cash Incassato</div>"
            f"<div style='color: {pnl_col}; font-size: 1.05rem; font-weight: 700; margin-top: 3px;'>{pnl_inc:+.2f} €</div>"
            f"<div style='color: #64748b; font-size: 0.68rem; margin-top: 2px;'>Dai rimbalzi (+7 pip)</div>"
            f"</div>",
            unsafe_allow_html=True
        )

    st.markdown("<hr style='margin: 10px 0; border-color: #334155;'>", unsafe_allow_html=True)

    col_ctrl, col_ladder = st.columns([5, 7])

    with col_ctrl:
        st.markdown("<h4 style='color: #38bdf8; margin-bottom: 8px;'>⚙️ Parametri di Ingresso</h4>", unsafe_allow_html=True)
        
        # Calcolo Livello Chirurgico Consigliato (TK21 H1 + Minimi Multi-Orizzonte 9h/21h/55h)
        sugg_lvl, tk21_val, min_stru_val, h21_val, l55_val, l21_val, l9_val = calcola_livello_chirurgico_gold(conto, px_live=bid_live)
        
        if sugg_lvl is not None:
            st.markdown(f"""
                <div style='background: rgba(14, 165, 233, 0.08); border: 1px solid rgba(56, 189, 248, 0.3); border-radius: 8px; padding: 10px 14px; margin-bottom: 12px;'>
                    <div style='display: flex; justify-content: space-between; align-items: center;'>
                        <span style='color: #38bdf8; font-weight: 700; font-size: 0.84rem;'>🎯 LIVELLO CHIRURGICO CONSIGLIATO:</span>
                        <span style='color: #FFD700; font-weight: 800; font-size: 1.15rem;'>{sugg_lvl:.2f}</span>
                    </div>
                    <div style='color: #94a3b8; font-size: 0.74rem; margin-top: 4px;'>
                        Struttura H1: <b>TK21: {tk21_val:.2f}</b> | <b>Floor Operativo: {min_stru_val:.2f}</b> (Min55: {l55_val:.2f}, Min21: {l21_val:.2f}, Min9: {l9_val:.2f}) | <b>Max21: {h21_val:.2f}</b>
                    </div>
                </div>
            """, unsafe_allow_html=True)

        # Prezzo Livello 1 (Obbligatorio)
        def_pz1 = float(bid_live) if bid_live else 0.0
        saved_pz1 = cfg.get("livello_1_prezzo") or 0.0
        
        ss_key = f"gf_pz1_{conto}"
        val_default = st.session_state.get(ss_key)
        if val_default is None:
            if saved_pz1 > 0:
                val_default = float(saved_pz1)
            elif sugg_lvl is not None:
                val_default = float(sugg_lvl)
            elif def_pz1 > 0:
                val_default = float(round(def_pz1 - 5.0, 2))
            else:
                val_default = 0.0

        col_inp, col_btn_sugg = st.columns([7, 5], vertical_alignment="bottom")
        with col_inp:
            pz_l1 = st.number_input(
                "🎯 Prezzo Livello 1 (Partenza)",
                min_value=0.0,
                max_value=10000.0,
                value=float(val_default),
                step=1.0,
                format="%.2f",
                key=f"input_{ss_key}",
                help="Prezzo a cui scatterà il primo scaglione SHORT a mercato."
            )
        with col_btn_sugg:
            if sugg_lvl is not None:
                if st.button(f"🎯 Usa {sugg_lvl:.2f}", key=f"btn_sugg_{conto}", use_container_width=True, help="Applica il prezzo chirurgico consigliato al Livello 1"):
                    st.session_state[ss_key] = float(sugg_lvl)
                    st.rerun()

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
                tab_rows += (
                    f"<tr style='border-bottom: 1px solid #334155;'>"
                    f"<td style='padding: 6px; font-weight: bold;'>Scaglione {s.get('numero')}</td>"
                    f"<td style='padding: 6px; color: #f8fafc;'>{pz_tgt}</td>"
                    f"<td style='padding: 6px; color: #38bdf8; font-weight: bold;'>-{s.get('size')} mini</td>"
                    f"<td style='padding: 6px;'>{st_badge}</td>"
                    f"</tr>"
                )

            html_table = (
                "<table style='width: 100%; border-collapse: collapse; font-size: 0.85rem;'>"
                "<thead>"
                "<tr style='border-bottom: 2px solid #64748b; color: #94a3b8;'>"
                "<th style='text-align: left; padding: 6px;'>Scaglione</th>"
                "<th style='text-align: left; padding: 6px;'>Trigger Prezzo</th>"
                "<th style='text-align: left; padding: 6px;'>Size Short</th>"
                "<th style='text-align: left; padding: 6px;'>Stato</th>"
                "</tr>"
                "</thead>"
                f"<tbody>{tab_rows}</tbody>"
                "</table>"
            )
            st.markdown(html_table, unsafe_allow_html=True)
            
            min_disc = stato.get("minimo_discesa")
            if min_disc is not None:
                sgancio = round(min_disc + 7.0, 2)
                st.markdown(
                    f"<div style='margin-top: 10px; padding: 8px 12px; background-color: #0f172a; border-left: 3px solid #38bdf8; border-radius: 4px; font-size: 0.82rem;'>"
                    f"📉 <b>Minimo Discesa Corrente:</b> <span style='color: #f8fafc;'>{min_disc:.2f}</span> &nbsp;|&nbsp; "
                    f"💥 <b>Soglia Chiusura Rimbalzo (+7 pip):</b> <span style='color: #FFD700; font-weight: bold;'>{sgancio:.2f}</span>"
                    f"</div>",
                    unsafe_allow_html=True
                )
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
                r_html += (
                    f"<tr style='border-bottom: 1px solid #1e293b;'>"
                    f"<td style='padding: 5px; color: #94a3b8;'>{op.get('data')}</td>"
                    f"<td style='padding: 5px;'>Scaglione {op.get('scaglione')}</td>"
                    f"<td style='padding: 5px;'>{op.get('size')} mini</td>"
                    f"<td style='padding: 5px;'>{op.get('open'):.2f}</td>"
                    f"<td style='padding: 5px;'>{op.get('close'):.2f}</td>"
                    f"<td style='padding: 5px; color: {pnl_c}; font-weight: bold;'>{pnl:+.2f} €</td>"
                    f"<td style='padding: 5px; color: #94a3b8;'>{op.get('motivo')}</td>"
                    f"</tr>"
                )
            html_hist = (
                "<table style='width: 100%; border-collapse: collapse; font-size: 0.82rem;'>"
                "<thead>"
                "<tr style='border-bottom: 2px solid #475569; color: #94a3b8;'>"
                "<th style='text-align: left; padding: 5px;'>Data</th>"
                "<th style='text-align: left; padding: 5px;'>Scaglione</th>"
                "<th style='text-align: left; padding: 5px;'>Size</th>"
                "<th style='text-align: left; padding: 5px;'>Open</th>"
                "<th style='text-align: left; padding: 5px;'>Close</th>"
                "<th style='text-align: left; padding: 5px;'>PnL Netto</th>"
                "<th style='text-align: left; padding: 5px;'>Evento</th>"
                "</tr>"
                "</thead>"
                f"<tbody>{r_html}</tbody>"
                "</table>"
            )
            st.markdown(html_hist, unsafe_allow_html=True)
        else:
            st.caption("Nessuna operazione ancora chiusa in questa sessione.")
