import streamlit as st
import json
import os
import time
import pandas as pd
import requests
import re
from datetime import datetime, timedelta, timezone
from dotenv import dotenv_values

# --- CONFIGURAZIONI CENTRALI ---
FILE_MEMORIA = "memoria_parametri.json"
FILE_TOKEN = "token_ig.json"
FILE_STORICO = "storico_operazioni.csv"
CONSOLE_LOG_FILE = "console_live.log"
STATO_SISTEMA = "stato_sistema.json"
CREDENTIALS = {"Marco": "Bolzano&1971"} 

# --- VOCABOLARIO ---
CONFIG_STRUMENTI = {
    "AUD/CAD": {"epic": "CS.D.AUDCAD.MINI.IP", "moltiplicatore": 0.0001, "decimali": 5, "valuta": "CAD", "valore_punto": 1},
    "AUD/NZD": {"epic": "CS.D.AUDNZD.MINI.IP", "moltiplicatore": 0.0001, "decimali": 5, "valuta": "NZD", "valore_punto": 1},
    "CAD/JPY": {"epic": "CS.D.CADJPY.MINI.IP", "moltiplicatore": 0.01, "decimali": 3, "valuta": "JPY", "valore_punto": 100},
    "EUR/GBP": {"epic": "CS.D.EURGBP.MINI.IP", "moltiplicatore": 0.0001, "decimali": 5, "valuta": "GBP", "valore_punto": 1},
    "GBP/USD": {"epic": "CS.D.GBPUSD.MINI.IP", "moltiplicatore": 0.0001, "decimali": 5, "valuta": "USD", "valore_punto": 1},
    "USD/CAD": {"epic": "CS.D.USDCAD.MINI.IP", "moltiplicatore": 0.0001, "decimali": 5, "valuta": "CAD", "valore_punto": 1},
    "USD/CHF": {"epic": "CS.D.USDCHF.MINI.IP", "moltiplicatore": 0.0001, "decimali": 5, "valuta": "CHF", "valore_punto": 1},
    "USD/JPY": {"epic": "CS.D.USDJPY.MINI.IP", "moltiplicatore": 0.01, "decimali": 3, "valuta": "JPY", "valore_punto": 100},
    "Spot Gold": {"epic": "CS.D.CFEGOLD.CBE.IP", "moltiplicatore": 1, "decimali": 1, "valuta": "EUR", "valore_punto": 1},
    "US 500 Cash": {"epic": "IX.D.SPTRD.IBE.IP", "moltiplicatore": 1, "decimali": 1, "valuta": "EUR", "valore_punto": 1}
}

st.set_page_config(page_title="Macchinetta IG", layout="wide")

# --- FUNZIONI HELPER MULTI-CONTO ---
def get_accounts():
    """Scansiona la root e trova tutte le cartelle conto valide."""
    return [d for d in os.listdir() if os.path.isdir(d) and (d.endswith("_DEMO") or d.endswith("_REALE"))]

def formatta_numero(valore, dec):
    if valore is None:
        return None
    r = round(float(valore), dec)
    return f"{r:.{dec}f}"

def formatta_eur(valore_str):
    try:
        val_float = float(valore_str)
        formattato = f"{val_float:,.2f}"
        return formattato.replace(",", "X").replace(".", ",").replace("X", ".")
    except (ValueError, TypeError):
        return "0,00"

def get_eur_rate(valuta, prezzi):
    if valuta == "EUR": return 1.0
    eur_gbp = prezzi.get("EUR/GBP")
    gbp_usd = prezzi.get("GBP/USD")
    if not eur_gbp or not gbp_usd: return 1.0
    eur_usd = eur_gbp * gbp_usd
    
    if valuta == "USD": return 1.0 / eur_usd
    if valuta == "GBP": return 1.0 / eur_gbp
    if valuta == "CAD":
        usd_cad = prezzi.get("USD/CAD")
        if usd_cad: return 1.0 / (eur_usd * usd_cad)
    if valuta == "CHF":
        usd_chf = prezzi.get("USD/CHF")
        if usd_chf: return 1.0 / (eur_usd * usd_chf)
    if valuta == "JPY":
        usd_jpy = prezzi.get("USD/JPY")
        if usd_jpy: return 1.0 / (eur_usd * usd_jpy)
    if valuta == "NZD":
        usd_cad = prezzi.get("USD/CAD")
        aud_cad = prezzi.get("AUD/CAD")
        aud_nzd = prezzi.get("AUD/NZD")
        if usd_cad and aud_cad and aud_nzd:
            eur_cad = eur_usd * usd_cad
            eur_aud = eur_cad / aud_cad
            eur_nzd = eur_aud * aud_nzd
            return 1.0 / eur_nzd
    return 1.0

def is_oltrepassato(tipo, direzione, livello_ideale, prezzo_live):
    if not prezzo_live or not livello_ideale: return False
    if tipo == "STOP":
        if direzione == "BUY": return prezzo_live > livello_ideale
        if direzione == "SELL": return prezzo_live < livello_ideale
    elif tipo == "LIMIT":
        if direzione == "BUY": return prezzo_live < livello_ideale
        if direzione == "SELL": return prezzo_live > livello_ideale
    return False

def piazza_restore(conto, nome, cmd_dict):
    mem = carica_memoria(conto)
    if nome in mem:
        mem[nome]["comando_restore"] = cmd_dict
        salva_memoria(conto, mem)
        st.success(f"Comando di RECOVERY inviato al Motore per {nome}! In attesa di esecuzione...")
        time.sleep(2)
        st.rerun()

@st.dialog("Diario di Bordo (WIP)")
def mostra_diario_wip(nome_strumento, storico):
    st.markdown(f"### 📈 Cronologia: {nome_strumento}")
    st.markdown("---")
    if storico:
        totale = 0.0
        html_str = "<div style='font-size: 0.85rem; line-height: 1.6;'>"
        for riga in storico:
            match = re.search(r"\[Parziale:\s*([+-]?\d+(?:\.\d+)?)\s*€\]", riga)
            if match:
                totale += float(match.group(1))
            
            riga_colorata = re.sub(r"(\[Parziale:.*?\])", r"<span style='color: #FFD700;'>\1</span>", riga)
            html_str += f"&bull; {riga_colorata}<br>"
        
        segno = "+" if totale > 0 else ""
        html_str += "<br>========================<br>"
        html_str += f"<span style='color: #FFD700;'><b>Totale aggiornato:</b> {segno}{totale:.2f} €</span></div>"
        
        st.markdown(html_str, unsafe_allow_html=True)
    else:
        st.info("Nessun evento registrato in questo ciclo.")
    st.markdown("---")

def get_ig_headers(conto_selezionato):
    token_path = os.path.join(conto_selezionato, FILE_TOKEN)
    env_path = os.path.join(conto_selezionato, ".env")
    if not os.path.exists(token_path):
        return None
    try:
        with open(token_path, "r") as f:
            t = json.load(f)
        config_env = dotenv_values(env_path)
        return {
            "X-IG-API-KEY": config_env.get("IG_API_KEY", ""),
            "CST": t.get("CST", ""),
            "X-SECURITY-TOKEN": t.get("X-SECURITY-TOKEN", ""),
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Version": "2"
        }
    except:
        return None

@st.dialog("Configurazione Avvio Sincrono Multiconto", width="large")
def dialog_sync_start(conto_partenza, nome_strumento):
    conti_disponibili = [d for d in os.listdir(".") if os.path.isdir(d) and (d.endswith("_DEMO") or d.endswith("_REALE"))]
    if len(conti_disponibili) < 2:
        st.error("⚠️ Sono necessari almeno due conti (Demo o Reali) per utilizzare l'Avvio Sincrono Multiconto.")
        return
        
    st.markdown(f"### ⚖️ Avvio Sincrono per {nome_strumento}")
    st.write("Seleziona i conti su cui avviare le due gambe dell'operazione (una LONG e una SHORT).")
    
    mem_partenza = carica_memoria(conto_partenza)
    dati_partenza = mem_partenza.get(nome_strumento, {})
    
    is_asset = nome_strumento in ["Spot Gold", "US 500 Cash"]
    def_tp = 100 if is_asset else 50
    def_opp = 20 if is_asset else 10
    def_dts = 10 if is_asset else 5
    
    tp_val = dati_partenza.get("tp", def_tp)
    opp_val = dati_partenza.get("opp", def_opp)
    dts_val = dati_partenza.get("dts", def_dts)
    size_val = dati_partenza.get("size", 4)
    
    st.info(f"**Parametri di base (dal conto attuale):** TP = {tp_val} | OPP = {opp_val} | DTS = {dts_val} | Size = {size_val}")
    
    idx_long = conti_disponibili.index(conto_partenza) if conto_partenza in conti_disponibili else 0
    idx_short = (idx_long + 1) % len(conti_disponibili) if len(conti_disponibili) > 1 else 0
    
    col1, col2 = st.columns(2)
    with col1:
        conto_l = st.selectbox("🟢 Conto Lato LONG", conti_disponibili, index=idx_long, key=f"sync_l_{nome_strumento}")
    with col2:
        conto_s = st.selectbox("🔴 Conto Lato SHORT", conti_disponibili, index=idx_short, key=f"sync_s_{nome_strumento}")
        
    if conto_l == conto_s:
        st.error("⚠️ Devi selezionare due conti differenti per l'Avvio Sincrono!")
        if st.button("❌ ANNULLA", key=f"sync_annulla_err_{nome_strumento}"):
            st.session_state[f"sync_open_{nome_strumento}"] = False
            st.rerun()
        return
        
    # Controllo Congruità Parametri
    mem_l = carica_memoria(conto_l).get(nome_strumento, {})
    mem_s = carica_memoria(conto_s).get(nome_strumento, {})
    
    p_l = (mem_l.get("tp", def_tp), mem_l.get("opp", def_opp), mem_l.get("dts", def_dts), mem_l.get("size", 4))
    p_s = (mem_s.get("tp", def_tp), mem_s.get("opp", def_opp), mem_s.get("dts", def_dts), mem_s.get("size", 4))
    
    if p_l != p_s:
        st.warning(f"⚠️ **Attenzione: i parametri salvati sui due conti non coincidono.**\n\n- **{conto_l} (LONG):** TP={p_l[0]}, OPP={p_l[1]}, DTS={p_l[2]}, Size={p_l[3]}\n- **{conto_s} (SHORT):** TP={p_s[0]}, OPP={p_s[1]}, DTS={p_s[2]}, Size={p_s[3]}\n\nAssicurati di salvarli identici nella Dashboard di entrambi i conti prima di avviare il Sincrono per mantenere un hedging perfetto.")
        if st.button("❌ ANNULLA", key=f"sync_annulla_warn_{nome_strumento}"):
            st.session_state[f"sync_open_{nome_strumento}"] = False
            st.rerun()
        return
        
    c_btn1, c_btn2 = st.columns(2)
    with c_btn1:
        if st.button("⚡ CONFERMA AVVIO SINCRONO", type="primary", use_container_width=True, key=f"sync_conf_{nome_strumento}"):
            full_mem_l = carica_memoria(conto_l)
            full_mem_s = carica_memoria(conto_s)
            
            full_mem_l[nome_strumento] = {"attivo": True, "direzione": "LONG", "tp": p_l[0], "opp": p_l[1], "dts": p_l[2], "size": p_l[3], "stato": "IN_ATTESA", "storico_wip": [], "errore_avvio": False, "errore_ripristino": False, "comando_manuale": False, "msg_manuale": ""}
            salva_memoria(conto_l, full_mem_l)
            
            full_mem_s[nome_strumento] = {"attivo": True, "direzione": "SHORT", "tp": p_s[0], "opp": p_s[1], "dts": p_s[2], "size": p_s[3], "stato": "IN_ATTESA", "storico_wip": [], "errore_avvio": False, "errore_ripristino": False, "comando_manuale": False, "msg_manuale": ""}
            salva_memoria(conto_s, full_mem_s)
            
            st.session_state[f"sync_open_{nome_strumento}"] = False
            st.rerun()
    with c_btn2:
        if st.button("❌ ANNULLA", use_container_width=True, key=f"sync_annulla_{nome_strumento}"):
            st.session_state[f"sync_open_{nome_strumento}"] = False
            st.rerun()


@st.dialog("Modifica SL/TP su IG", width="large")
def dialog_sync(conto_selezionato, nome_strumento):
    st.markdown(f"### ⚙️ {nome_strumento} | Gestione Posizioni IG")
    epic = CONFIG_STRUMENTI.get(nome_strumento, {}).get("epic")
    h1 = get_ig_headers(conto_selezionato)
    
    if not h1 or not epic:
        st.error("Connessione API IG non disponibile o strumento non trovato. Avvia il Motore per generare il token.")
        return

    dec = CONFIG_STRUMENTI[nome_strumento]["decimali"]
    mult = CONFIG_STRUMENTI[nome_strumento]["moltiplicatore"]
    step_val = float(f"1e-{dec}")
    
    base_url = "https://api.ig.com/gateway/deal" if "_REALE" in conto_selezionato.upper() else "https://demo-api.ig.com/gateway/deal"

    pos_list = []
    r_pos = requests.get(f"{base_url}/positions", headers=h1)
    
    if r_pos.status_code == 200:
        for p in r_pos.json().get('positions', []):
            if p['market']['epic'] == epic:
                pos = p['position']
                lim_pos = pos.get('limitLevel')
                stop_pos = pos.get('stopLevel')
                
                if lim_pos is None and pos.get('limitDistance') is not None:
                    dist = float(pos['limitDistance'])
                    entry = float(pos.get('level', 0))
                    lim_pos = entry + (dist * mult) if pos['direction'] == 'BUY' else entry - (dist * mult)
                
                if stop_pos is None and pos.get('stopDistance') is not None:
                    dist = float(pos['stopDistance'])
                    entry = float(pos.get('level', 0))
                    stop_pos = entry - (dist * mult) if pos['direction'] == 'BUY' else entry + (dist * mult)
                
                if lim_pos is not None or stop_pos is not None:
                    p['_calc_limit'] = lim_pos
                    p['_calc_stop'] = stop_pos
                    pos_list.append(p)
                    
    if not pos_list:
        st.info("🟢 Nessuna posizione attiva con SL/TP associato è attualmente presente su IG per questo strumento.")
        return
    
    st.markdown("#### 🟢 Posizioni Attive")
    for p in pos_list:
        pos = p['position']
        deal_id = pos['dealId']
        dir_pos = pos['direction']
        size_pos = pos['size']
        lvl_pos = pos.get('level', 0)
        lim_pos = p.get('_calc_limit')
        stop_pos = p.get('_calc_stop')
        
        with st.container(border=True):
            st.markdown(f"**Posizione {dir_pos}** &nbsp;&nbsp;|&nbsp;&nbsp; Size: `{size_pos}` &nbsp;&nbsp;|&nbsp;&nbsp; Entry: `{lvl_pos}`")
            c1, c2, c3 = st.columns([2, 2, 1])
            with c1:
                new_tp = st.number_input("Take Profit", value=float(lim_pos) if lim_pos else 0.0, format=f"%.{dec}f", step=step_val, key=f"{conto_selezionato}_pos_tp_{deal_id}")
            with c2:
                new_sl = st.number_input("Stop Loss", value=float(stop_pos) if stop_pos else 0.0, format=f"%.{dec}f", step=step_val, key=f"{conto_selezionato}_pos_sl_{deal_id}")
            with c3:
                st.write("")
                if st.button("💾 Invia a IG", key=f"{conto_selezionato}_btn_pos_{deal_id}", width="stretch"):
                    payload = {}
                    if new_tp > 0:
                        payload["limitLevel"] = formatta_numero(new_tp, dec)
                    if new_sl > 0:
                        payload["stopLevel"] = formatta_numero(new_sl, dec)
                    
                    r_upd = requests.put(f"{base_url}/positions/otc/{deal_id}", headers=h1, json=payload)
                    if r_upd.status_code == 200:
                        st.success("Modificato!")
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error(f"Rifiutato da IG: {r_upd.text}")

st.markdown("""
    <style>
        div[data-testid="stButton"] > button[kind="secondary"] { min-height: 42px !important; height: 42px !important; white-space: nowrap !important; }
        div[data-testid="stButton"] > button[kind="primary"] { background-color: #198754 !important; border-color: #198754 !important; color: white !important; min-height: 32px !important; height: 32px !important; padding: 0px 5px !important; font-size: 0.95rem !important; font-weight: 600 !important; margin: 0px !important; }
        div[data-testid="stButton"] > button[kind="primary"]:hover { background-color: #146c43 !important; border-color: #146c43 !important; }
        .sintesi-testo { display: flex; align-items: center; height: 32px; margin: 0px !important; padding: 0px !important; font-size: 0.95rem; }
        .sintesi-testo p { margin: 0px !important; }
        div[data-testid="stMetricValue"] { font-size: 1.4rem !important; }
        section[data-testid="stSidebar"] { min-width: 220px !important; max-width: 220px !important; }
        button[data-testid="stNumberInputStepUp"], button[data-testid="stNumberInputStepDown"] { display: flex !important; }
        div[data-testid="stNumberInputContainer"] { padding-left: 0.2rem !important; padding-right: 0.2rem !important; }
        
        /* CSS per Tabelle Portafoglio IG */
        .ig-table { width: 90%; max-width: 1400px; margin: 0 auto; border-collapse: collapse; font-family: -apple-system, BlinkMacSystemFont, sans-serif; font-size: 0.85rem; color: #d1d4dc; margin-bottom: 20px; }
        .ig-table th { text-align: center; color: white; padding: 10px 8px; border-bottom: 1px solid rgba(255,255,255,0.1); font-weight: 600; font-size: 0.75rem; text-transform: uppercase; }
        .ig-table th:first-child { text-align: left; padding-left: 15px; color: #888; }
        
        /* Master Row in Grassetto e sottolineato */
        .ig-row { border-bottom: 1px solid rgba(255,255,255,0.05); font-weight: bold; }
        .ig-master-row td { text-decoration: underline; text-underline-offset: 3px; }
        .ig-master-row span.ig-dot { text-decoration: none; display: inline-block; }
        
        .ig-row:hover { background-color: rgba(255,255,255,0.02); }
        .ig-row td { padding: 10px 8px; text-align: center; }
        .ig-row td:first-child { text-align: left; padding-left: 15px; }
        
        /* Sub Row NON in Grassetto e con P/L colorato preservato */
        .ig-subrow { background-color: rgba(0,0,0,0.2); font-weight: normal !important; }
        .ig-subrow td { color: #aaa; font-size: 0.8rem; border-bottom: none; padding: 6px 8px; font-weight: normal !important; text-decoration: none !important; }
        .ig-subrow td:first-child { padding-left: 35px; text-align: left; }
        .ig-subrow td.pnl-pos { color: #3b82f6 !important; font-weight: bold !important; }
        .ig-subrow td.pnl-neg { color: #ef4444 !important; font-weight: bold !important; }

        .size-buy { color: #3b82f6; }
        .size-sell { color: #ef4444; }
        .ig-row .size-buy, .ig-row .size-sell { font-weight: bold; }
        
        /* Modifica per far ereditare correttamente il colore della size nei subrows */
        .ig-subrow td.size-buy { color: #3b82f6 !important; font-weight: normal !important; }
        .ig-subrow td.size-sell { color: #ef4444 !important; font-weight: normal !important; }

        .pnl-pos { color: #3b82f6; font-weight: bold; }
        .pnl-neg { color: #ef4444; font-weight: bold; }
        
        .ig-multiplo { font-style: italic; color: #888; font-weight: normal; text-decoration: none !important; }
        .ig-dot { height: 8px; width: 8px; background-color: #09ab3b; border-radius: 50%; display: inline-block; margin-right: 8px; }
        
        /* CSS per Tabelle Statistiche Aggiuntive */
        .stat-table { width: 100%; margin: 0 auto; border-collapse: collapse; font-family: -apple-system, BlinkMacSystemFont, sans-serif; font-size: 0.95rem; color: #d1d4dc; margin-bottom: 30px; }
        .stat-table th { text-align: center; color: white; padding: 8px 10px; border-bottom: 2px solid rgba(255,255,255,0.2); font-weight: bold; font-size: 0.85rem; text-transform: uppercase; background-color: rgba(255,255,255,0.02); }
        .stat-table td { text-align: center; padding: 8px 10px; border-bottom: 1px solid rgba(255,255,255,0.05); }
        .stat-table tr:hover { background-color: rgba(255,255,255,0.04); }
        .text-green { color: #4ade80 !important; }
        .text-red { color: #f87171 !important; }
        .text-bold { font-weight: bold !important; }
    </style>
""", unsafe_allow_html=True)

def leggi_stato_sistema(conto_selezionato):
    path = os.path.join(conto_selezionato, STATO_SISTEMA)
    if os.path.exists(path):
        try:
            with open(path, "r") as f: return json.load(f)
        except: pass
    return {"saldo": "0.00", "disponibile": "0.00", "margine": "0.00", "drawdown": "0.00", "messaggio": "In attesa...", "durata_sessione": "0h 00m", "ultimo_aggiornamento": "--", "prezzi_live": {}, "distanze_minime": {}}

def carica_memoria(conto_selezionato):
    path = os.path.join(conto_selezionato, FILE_MEMORIA)
    if os.path.exists(path):
        try:
            with open(path, "r") as f: return json.load(f)
        except: return {}
    return {}

def salva_memoria(conto_selezionato, dati):
    path = os.path.join(conto_selezionato, FILE_MEMORIA)
    with open(path, "w") as f:
        json.dump(dati, f, indent=4)

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if not st.session_state.logged_in:
    st.title("🔐 Fiordok Trading")
    st.subheader("Accedi al pannello di controllo")
    with st.form("login_form"):
        user = st.text_input("Account")
        pw = st.text_input("Password", type="password")
        if st.form_submit_button("Accedi"):
            if CREDENTIALS.get(user) == pw:
                st.session_state.logged_in = True
                st.session_state.user = user
                st.rerun()
            else:
                st.error("Credenziali errate")
else:
    conti_disponibili = get_accounts()
    if not conti_disponibili:
        st.warning("⚠️ Nessun conto trovato. Crea una cartella (es. ROSSI_DEMO) e inserisci al suo interno il file .env per cominciare.")
        st.stop()

    with st.sidebar:
        st.markdown(f"### 👤 Utente: {st.session_state.user}")
        conto_selezionato = st.selectbox("🔌 Seleziona Conto", conti_disponibili)
        is_reale = "_REALE" in conto_selezionato.upper()
        if is_reale: st.error(f"**CONTO:** 🔴 REALE")
        else: st.info(f"**CONTO:** 🔵 DEMO")
        if st.button("Logout"):
            st.session_state.logged_in = False
            st.rerun()
            
        # --- AGGIUNTA MARGINE E DRAWDOWN IN SIDEBAR (LIVE) ---
        @st.fragment(run_every=15)
        def renderizza_sidebar_stats():
            stato_side = leggi_stato_sistema(conto_selezionato)
            
            motore_attivo_side = False
            path_stato_side = os.path.join(conto_selezionato, STATO_SISTEMA)
            if os.path.exists(path_stato_side) and (time.time() - os.path.getmtime(path_stato_side)) < 60: 
                motore_attivo_side = True
            badge_motore_side = "🟢 Connesso" if motore_attivo_side else "🔴 Offline"

            val_capitale = formatta_eur(stato_side.get('saldo', '0'))
            val_margine = formatta_eur(stato_side.get('margine', '0'))
            val_residuo = formatta_eur(stato_side.get('disponibile', '0'))
            val_dd = formatta_eur(stato_side.get('drawdown', '0'))
            
            try:
                dd_num = float(stato_side.get('drawdown', '0'))
                col_dd = "#ef4444" if dd_num < 0 else ("#09ab3b" if dd_num > 0 else "inherit")
            except:
                col_dd = "inherit"

            st.markdown("---")
            st.markdown(f"**Stato Sistema:** {badge_motore_side}")
            st.markdown("---")
            st.markdown(f"<div style='font-size: 0.9rem; color: #aaa;'>Capitale Totale</div><div style='font-size: 1.2rem; font-weight: bold;'>{val_capitale} €</div>", unsafe_allow_html=True)
            st.markdown(f"<div style='font-size: 0.9rem; color: #aaa; margin-top: 10px;'>Margine Utilizzato</div><div style='font-size: 1.2rem; font-weight: bold;'>{val_margine} €</div>", unsafe_allow_html=True)
            st.markdown(f"<div style='font-size: 0.9rem; color: #aaa; margin-top: 10px;'>Margine Residuo</div><div style='font-size: 1.2rem; font-weight: bold;'>{val_residuo} €</div>", unsafe_allow_html=True)
            st.markdown(f"<div style='font-size: 0.9rem; color: #aaa; margin-top: 10px;'>Drawdown (P/L)</div><div style='font-size: 1.2rem; font-weight: bold; color: {col_dd};'>{val_dd} €</div>", unsafe_allow_html=True)
        
        renderizza_sidebar_stats()

    # TABS RIORDINATI (Portafoglio IG per primo)
    tab_portafoglio, tab_sintesi, tab_operativa, tab_restore, tab_statistiche, tab_console = st.tabs([
        "💼 Portafoglio IG", "📈 Sintesi", "🛡️ Operatività", "🛑 Recovery", "📊 Statistiche", "💻 Console"
    ])

    with tab_portafoglio:
        @st.fragment(run_every=15)
        def renderizza_portafoglio():
            st.markdown("<h1 style='color: #FFD700; text-align: center;'>💼 Portafoglio IG (Live)</h1>", unsafe_allow_html=True)
            st.markdown("<p style='text-align: center;'>Visualizzazione speculare in sola lettura delle tue posizioni e ordini sui server IG.</p>", unsafe_allow_html=True)
            
            h = get_ig_headers(conto_selezionato)
            if not h:
                st.error("Connessione IG mancante. Avvia il Motore per generare il token.")
                return

            base_url = "https://api.ig.com/gateway/deal" if "_REALE" in conto_selezionato.upper() else "https://demo-api.ig.com/gateway/deal"
            
            # Fetch dati
            r_pos = requests.get(f"{base_url}/positions", headers=h)
            pos_data = r_pos.json().get('positions', []) if r_pos.status_code == 200 else []
            
            r_ord = requests.get(f"{base_url}/workingorders", headers=h)
            ord_data = r_ord.json().get('workingOrders', []) if r_ord.status_code == 200 else []

            epic_to_name = {v['epic']: k for k, v in CONFIG_STRUMENTI.items()}
            stato = leggi_stato_sistema(conto_selezionato)
            prezzi_live = stato.get("prezzi_live", {})
            memoria_attuale = carica_memoria(conto_selezionato)
            
            # --- HELPER: Riconoscimento Ruolo Chirurgico ---
            def get_role_pos(nome_strum, dir_pos, sz_pos, param_memoria, pos_dict):
                s_c = float(param_memoria.get("size", 0))
                if s_c <= 0: return "-"
                stato_sys = param_memoria.get("stato", "")
                s_m = max(1.0, s_c / 2)
                s_q = max(0.1, s_c / 4)
                
                has_limits = bool(pos_dict.get('limitLevel') or pos_dict.get('limitDistance') or pos_dict.get('stopLevel') or pos_dict.get('stopDistance'))
                
                dir_label = "LONG" if dir_pos == "BUY" else "SHORT"
                
                if abs(sz_pos - s_c) < 0.001: 
                    return f"Core ({dir_label})"
                elif abs(sz_pos - s_m) < 0.001:
                    if "FASE_1" in stato_sys: 
                        return "Micro" if has_limits else "Assicurazione"
                    if "TICKET1" in stato_sys: return "Ticket1"
                    if param_memoria.get("ticket2_active") and dir_pos == param_memoria.get("ticket2_dir") and not pos_dict.get('stopLevel'):
                        return "Ticket2"
                    if "SATELLITE" in stato_sys: return "SAT1" if dir_pos == param_memoria.get("sat_dir", "") else "OverGain"
                    if "FASE_3" in stato_sys: return "Ultima"
                    return "SAT1" if "FASE_2" in stato_sys else ("Micro" if has_limits else "Assicurazione")
                elif abs(sz_pos - s_q) < 0.001: 
                    if "SATELLIT" in stato_sys:
                        return "SAT2"
                    return "Posizione (1/4)"
                elif abs(sz_pos - s_c * 0.15) < 0.001: return "Ultima"
                elif abs(sz_pos - s_c * 0.35) < 0.001: return f"Core ({dir_label}) (Taglio 1)"
                elif abs(sz_pos - s_c * 0.50) < 0.001: return f"Core ({dir_label}) (Taglio 2)"
                return "Posizione Orfana"

            def get_role_ord(nome_strum, dir_pos, sz_pos, param_memoria, ord_dict):
                s_c = float(param_memoria.get("size", 0))
                if s_c <= 0: return "-"
                stato_sys = param_memoria.get("stato", "")
                s_m = max(1.0, s_c / 2)
                s_q = max(0.1, s_c / 4)
                
                dir_label = "LONG" if dir_pos == "BUY" else "SHORT"
                
                if abs(sz_pos - s_c) < 0.001: 
                    return f"Core ({dir_label})"
                elif abs(sz_pos - s_m) < 0.001:
                    if "FASE_1" in stato_sys: return "Micro"
                    if param_memoria.get("ticket2_active") and dir_pos == param_memoria.get("ticket2_dir") and not ord_dict.get('stopDistance') and not ord_dict.get('stopLevel'):
                        return "Ticket2"
                    if "SATELLIT" in stato_sys or "STANDBY" in stato_sys or "TICKET1" in stato_sys:
                        if "OG" in stato_sys or "OL" in stato_sys or "(OG-OL)" in stato_sys:
                            return "OverGain"
                        return "SAT1 OCO"
                    if "FASE_3" in stato_sys: return "Taglio"
                    return "SAT1 OCO" if "FASE_2" in stato_sys else "Micro"
                elif abs(sz_pos - s_q) < 0.001: 
                    return "OverLoss"
                elif abs(sz_pos - s_c * 0.15) < 0.001: 
                    return "Taglio"
                return "Ordine Manuale"

            # --- ELABORAZIONE POSIZIONI ---
            gruppi_pos = {}
            for p in pos_data:
                epic = p['market']['epic']
                nome = epic_to_name.get(epic, epic)
                dir = p['position']['direction']
                key = (nome, dir)
                if key not in gruppi_pos:
                    gruppi_pos[key] = []
                gruppi_pos[key].append(p)
            
            # Intestazioni centrate e bianche
            html_pos = "<h4 style='margin-top: 20px; text-align: center;'><u>Posizioni Aperte</u></h4>\n<table class='ig-table'>\n<thead><tr><th style='text-align: left; color: #888; padding-left: 15px;'><u>MERCATO</u></th><th style='text-align: center; color: white;'><u>SIZE</u></th><th style='text-align: center; color: white;'><u>APERTURA</u></th><th style='text-align: center; color: white;'><u>ULTIMO</u></th><th style='text-align: center; color: white;'><u>STOP</u></th><th style='text-align: center; color: white;'><u>LIMITE</u></th><th style='text-align: center; color: white;'><u>TIPO</u></th><th style='text-align: center; color: white;'><u>P/L (EUR)</u></th></tr></thead>\n<tbody>\n"
            
            totale_pnl_portafoglio = 0.0
            
            # Ordinamento Master Rows: Nome alfabetico, poi size totale (assoluto) decrescente
            # Garantisce che la Core (-4) venga stampata sempre PRIMA della Assicurazione (+2)
            def get_group_total_size(posizioni):
                return sum(float(p['position']['size']) for p in posizioni)
                
            items_pos = sorted(gruppi_pos.items(), key=lambda item: (item[0][0], -abs(get_group_total_size(item[1]))))
            
            for i, ((nome, dir), posizioni) in enumerate(items_pos):
                c = CONFIG_STRUMENTI.get(nome, {})
                dec = c.get("decimali", 2)
                mult = c.get("moltiplicatore", 1)
                valore_punto = c.get("valore_punto", 1)
                valuta = c.get("valuta", "USD")
                
                tot_size = 0.0
                sum_level_size = 0.0
                tot_pnl_eur = 0.0
                stops = set()
                limits = set()
                ruoli_master = set()
                
                prezzo_attuale = prezzi_live.get(nome)
                rate = get_eur_rate(valuta, prezzi_live)
                
                for p in posizioni:
                    sz = float(p['position']['size'])
                    lvl = float(p['position']['level'])
                    
                    tot_size += sz
                    sum_level_size += (sz * lvl)
                    
                    if p['position'].get('stopLevel'): 
                        stops.add(round(float(p['position']['stopLevel']), dec))
                    elif p['position'].get('stopDistance'): 
                        dist = float(p['position']['stopDistance']) * mult
                        stops.add(round(lvl - dist if dir == 'BUY' else lvl + dist, dec))
                    else:
                        stops.add("NONE")
                        
                    if p['position'].get('limitLevel'): 
                        limits.add(round(float(p['position']['limitLevel']), dec))
                    elif p['position'].get('limitDistance'):
                        dist = float(p['position']['limitDistance']) * mult
                        limits.add(round(lvl + dist if dir == 'BUY' else lvl - dist, dec))
                    else:
                        limits.add("NONE")
                    
                    if prezzo_attuale:
                        pts = (prezzo_attuale - lvl)/mult if dir == 'BUY' else (lvl - prezzo_attuale)/mult
                        tot_pnl_eur += (pts * sz * valore_punto * rate)
                        
                    ruoli_master.add(get_role_pos(nome, dir, sz, memoria_attuale.get(nome, {}), p['position']))
                
                totale_pnl_portafoglio += tot_pnl_eur
                avg_entry = sum_level_size / tot_size
                
                sign = "+" if dir == "BUY" else "-"
                size_class = "size-buy" if dir == "BUY" else "size-sell"
                
                stop_str = "-"
                if len(stops) > 1: stop_str = "<span class='ig-multiplo'>Multiplo</span>"
                elif len(stops) == 1:
                    val = list(stops)[0]
                    stop_str = formatta_numero(val, dec) if val != "NONE" else "-"
                
                lim_str = "-"
                if len(limits) > 1: lim_str = "<span class='ig-multiplo'>Multiplo</span>"
                elif len(limits) == 1:
                    val = list(limits)[0]
                    lim_str = formatta_numero(val, dec) if val != "NONE" else "-"
                
                pnl_class = "pnl-pos" if tot_pnl_eur >= 0 else "pnl-neg"
                pnl_str = f"{tot_pnl_eur:.2f} €"
                
                if len(posizioni) > 1:
                    ruolo_master_str = ""
                else:
                    ruolo_master_str = list(ruoli_master)[0] if ruoli_master else "-"
                
                is_last_of_instrument = True
                if i < len(items_pos) - 1:
                    next_nome = items_pos[i+1][0][0]
                    if next_nome == nome:
                        is_last_of_instrument = False
                        
                has_subrows = len(posizioni) > 1
                master_style = "border-bottom: 2px solid rgba(255,255,255,0.3);" if (is_last_of_instrument and not has_subrows) else ""
                
                is_first_of_instrument = True
                if i > 0:
                    prev_nome = items_pos[i-1][0][0]
                    if prev_nome == nome:
                        is_first_of_instrument = False
                        
                prezzo_str = f"<u>{formatta_numero(prezzo_attuale, dec)}</u>" if prezzo_attuale else "<u>-</u>"
                if not is_first_of_instrument:
                    prezzo_str = ""

                html_pos += f"<tr class='ig-row ig-master-row' style='{master_style}'><td><span class='ig-dot'></span><u style='color: #FFD700;'>{nome}</u></td><td class='{size_class}'><u>{sign}{tot_size:g}</u></td><td class='{size_class}'><u>{formatta_numero(avg_entry, dec)}</u></td><td style='color: #00E676;'>{prezzo_str}</td><td><u>{stop_str}</u></td><td><u>{lim_str}</u></td><td><span class='{size_class}' style='font-weight: bold;'><u>{ruolo_master_str}</u></span></td><td class='{pnl_class}'><u>{pnl_str}</u></td></tr>\n"
                
                if has_subrows:
                    for idx, p in enumerate(posizioni):
                        sz = float(p['position']['size'])
                        lvl = float(p['position']['level'])
                        
                        dt_utc = datetime.strptime(p['position']['createdDateUTC'], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
                        data_str = dt_utc.astimezone().strftime("%d/%m/%y %H:%M")
                        
                        s_str = "-"
                        if p['position'].get('stopLevel'): s_str = formatta_numero(p['position']['stopLevel'], dec)
                        elif p['position'].get('stopDistance'): s_str = "Stop" 
                        
                        l_str = "-"
                        if p['position'].get('limitLevel'): l_str = formatta_numero(p['position']['limitLevel'], dec)
                        elif p['position'].get('limitDistance'): l_str = "Limite"
                        
                        pnl_child_eur = 0.0
                        if prezzo_attuale:
                            pts = (prezzo_attuale - lvl)/mult if dir == 'BUY' else (lvl - prezzo_attuale)/mult
                            pnl_child_eur = pts * sz * valore_punto * rate
                            
                        pnl_c_class = "pnl-pos" if pnl_child_eur >= 0 else "pnl-neg"
                        ruolo_child = get_role_pos(nome, dir, sz, memoria_attuale.get(nome, {}), p['position'])
                        
                        is_last_subrow = (idx == len(posizioni) - 1)
                        subrow_style = "border-bottom: 2px solid rgba(255,255,255,0.3);" if (is_last_of_instrument and is_last_subrow) else ""
                        
                        html_pos += f"<tr class='ig-row ig-subrow' style='{subrow_style}'><td>{data_str}</td><td class='{size_class}'>{sign}{sz:g}</td><td class='{size_class}'>{formatta_numero(lvl, dec)}</td><td></td><td>{s_str}</td><td>{l_str}</td><td><span class='{size_class}' style='font-weight: normal;'>{ruolo_child}</span></td><td class='{pnl_c_class}'>{pnl_child_eur:.2f} €</td></tr>\n"
            
            totale_class = "pnl-pos" if totale_pnl_portafoglio >= 0 else "pnl-neg"
            html_pos += f"<tr class='ig-row' style='background-color: rgba(255,255,255,0.05); border-top: 2px solid #888;'><td style='font-weight: bold;'>Totale</td><td></td><td></td><td></td><td></td><td></td><td></td><td class='{totale_class}' style='font-size: 1rem;'>{totale_pnl_portafoglio:.2f} €</td></tr>\n</tbody></table>"
            
            if not pos_data: html_pos = "<h4 style='margin-top: 20px; text-align: center;'><u>Posizioni Aperte</u></h4><p style='color: #888; font-style: italic; text-align: center;'>Nessuna posizione aperta al momento.</p>"

            st.markdown(html_pos, unsafe_allow_html=True)
            
            # --- ELABORAZIONE ORDINI PENDENTI ---
            html_ord = "<h4 style='margin-top: 40px; text-align: center;'><u>Ordini di Apertura</u></h4>\n<table class='ig-table'>\n<thead><tr><th style='text-align: left; color: #888; padding-left: 15px;'><u>MERCATO</u></th><th style='text-align: center; color: white;'><u>SIZE</u></th><th style='text-align: center; color: white;'><u>LIVELLO</u></th><th style='text-align: center; color: white;'><u>STOP</u></th><th style='text-align: center; color: white;'><u>LIMITE</u></th><th style='text-align: center; color: white;'><u>TIPO</u></th></tr></thead>\n<tbody>\n"
            
            # Ordino i pendenti per nome e poi per size
            ord_data_sorted = sorted(ord_data, key=lambda x: (
                epic_to_name.get(x['marketData']['epic'], x['marketData']['epic']),
                -float(x['workingOrderData'].get('orderSize', x['workingOrderData'].get('size', 0)))
            ))
            
            for i, o in enumerate(ord_data_sorted):
                epic = o['marketData']['epic']
                nome = epic_to_name.get(epic, epic)
                c = CONFIG_STRUMENTI.get(nome, {})
                dec = c.get("decimali", 2)
                mult = c.get("moltiplicatore", 1)
                
                wo = o['workingOrderData']
                dir = wo['direction']
                sz = float(wo.get('orderSize', wo.get('size', 0)))
                lvl = float(wo['orderLevel'])
                
                prezzo_attuale = prezzi_live.get(nome)
                sign = "+" if dir == "BUY" else "-"
                size_class = "size-buy" if dir == "BUY" else "size-sell"
                
                s_str = "-"
                if wo.get('stopDistance'): s_str = f"{int(float(wo['stopDistance']))}"
                
                l_str = "-"
                if wo.get('limitDistance'): l_str = f"{int(float(wo['limitDistance']))}"
                
                ruolo_ord = get_role_ord(nome, dir, sz, memoria_attuale.get(nome, {}), wo)
                
                is_last_of_instrument = True
                if i < len(ord_data_sorted) - 1:
                    next_epic = ord_data_sorted[i+1]['marketData']['epic']
                    next_nome = epic_to_name.get(next_epic, next_epic)
                    if next_nome == nome:
                        is_last_of_instrument = False
                        
                row_style = "border-bottom: 2px solid rgba(255,255,255,0.3);" if is_last_of_instrument else ""
                
                html_ord += f"<tr class='ig-row' style='{row_style}'><td><span class='ig-dot'></span><span style='color: #FFD700; font-weight: bold;'>{nome}</span></td><td class='{size_class}'>{sign}{sz:g}</td><td class='{size_class}'>{formatta_numero(lvl, dec)}</td><td>{s_str}</td><td>{l_str}</td><td><span class='{size_class}' style='font-weight: bold;'>{ruolo_ord}</span></td></tr>\n"
                
            html_ord += "</tbody></table>"
            
            if not ord_data: html_ord = "<h4 style='margin-top: 40px; text-align: center;'><u>Ordini di Apertura</u></h4><p style='color: #888; font-style: italic; text-align: center;'>Nessun ordine pendente al momento.</p>"

            st.markdown(html_ord, unsafe_allow_html=True)
            
        renderizza_portafoglio()

    with tab_sintesi:
        @st.fragment(run_every=15)
        def renderizza_sintesi():
            memoria = carica_memoria(conto_selezionato)
            stato_sys = leggi_stato_sistema(conto_selezionato)
            prezzi_live = stato_sys.get("prezzi_live", {})
            
            motore_attivo = False
            path_stato = os.path.join(conto_selezionato, STATO_SISTEMA)
            if os.path.exists(path_stato):
                if (time.time() - os.path.getmtime(path_stato)) < 60: motore_attivo = True
            
            badge_motore = "🟢 Connesso" if motore_attivo else "🔴 Offline"
            saldo_val = formatta_eur(stato_sys.get('saldo', '0'))
            dd_val = formatta_eur(stato_sys.get('drawdown', '0'))
            
            try:
                color_dd = "#ff4b4b" if float(stato_sys.get('drawdown', '0')) < 0 else ("#09ab3b" if float(stato_sys.get('drawdown', '0')) > 0 else "inherit")
            except: color_dd = "inherit"

            st.markdown(f"""
            <div style='display: flex; justify-content: space-between; align-items: flex-end; margin-top: -15px; margin-bottom: 20px;'>
                <h3 style='margin: 0; font-size: 1.6rem;'>📋 Sintesi Strumenti</h3>
                <div style='font-size: 1.05rem; font-weight: 500; display: flex; gap: 20px; align-items: center;'>
                    <span style='background-color: rgba(255,255,255,0.05); padding: 4px 10px; border-radius: 6px; border: 1px solid rgba(255,255,255,0.1);'><b>Stato Sistema:</b> {badge_motore}</span>
                    <span><span style='color: #888;'>Saldo:</span> {saldo_val} €</span>
                    <span><span style='color: #888;'>P/L:</span> <span style='color: {color_dd};'>{dd_val} €</span></span>
                </div>
            </div>
            """, unsafe_allow_html=True)
            
            with st.container(border=True):
                c1, c2, c3, c4 = st.columns([1.5, 3.5, 1.8, 3.2])
                c1.markdown("<div style='color: #888; font-size: 0.85rem; font-weight: 700; text-transform: uppercase; margin-top: 5px; margin-bottom: -5px;'>Strumento (WIP)</div>", unsafe_allow_html=True)
                c2.markdown("<div style='color: #888; font-size: 0.85rem; font-weight: 700; text-transform: uppercase; margin-top: 5px; margin-bottom: -5px;'>Fase Attuale</div>", unsafe_allow_html=True)
                c3.markdown("<div style='color: #888; font-size: 0.85rem; font-weight: 700; text-transform: uppercase; margin-top: 5px; margin-bottom: -5px;'>LIVE</div>", unsafe_allow_html=True)
                c4.markdown("<div style='color: #888; font-size: 0.85rem; font-weight: 700; text-transform: uppercase; margin-top: 5px; margin-bottom: -5px;'>Ultimo Evento</div>", unsafe_allow_html=True)
                st.markdown("<hr style='margin-top: 15px; margin-bottom: 15px; border-top: 1px solid rgba(255, 255, 255, 0.1);'>", unsafe_allow_html=True)
                
                tutti_strumenti = ["AUD/CAD", "AUD/NZD", "CAD/JPY", "EUR/GBP", "GBP/USD", "USD/CAD", "USD/CHF", "USD/JPY", "Spot Gold", "US 500 Cash"]
                # Ordina portando in cima gli strumenti attivi (True -> 0, False -> 1) preservando l'ordine originale per i parimerito
                tutti_strumenti.sort(key=lambda x: not memoria.get(x, {}).get("attivo", False))
                
                for nome in tutti_strumenti:
                    dati = memoria.get(nome, {})
                    stato = dati.get("stato", "IN_ATTESA")
                    is_attivo = dati.get("attivo", False)
                    storico = dati.get("storico_wip", [])
                    prezzo = prezzi_live.get(nome, "In aggiornamento...")
                    spia = ""
                    stato_display = stato.replace("OverGain", "OG").replace("OverLoss", "OL")
                    
                    if is_attivo and isinstance(prezzo, (int, float)):
                        mult = 1 if nome in ["Spot Gold", "US 500 Cash", "Ethereum"] else (0.01 if "JPY" in nome else 0.0001)
                        if stato == "FASE_1 + Micro":
                            dir_core = dati.get("direzione")
                            base = dati.get("prezzo_base")
                            tp = dati.get("tp", 50)
                            if dir_core and base is not None:
                                stato_display = f"FASE_1 + Micro ({'SHORT' if dir_core == 'LONG' else 'LONG'})"
                                spia = " 🟢" if (prezzo < base + (tp/4)*mult if dir_core == 'LONG' else prezzo > base - (tp/4)*mult) else " 🔴"
                        elif stato == "FASE_2_TICKET1":
                            t_dir, t_entry = dati.get("ticket1_dir"), dati.get("ticket1_entry", dati.get("ticket1_base")) 
                            if t_dir and t_entry is not None:
                                spia = " 🟢" if (prezzo > t_entry if t_dir == "BUY" else prezzo < t_entry) else " 🔴"
                        elif stato in ["FASE_2_SATELLITE_OG", "FASE_2_SATELLITE_OL"]:
                            s_dir, s_base = dati.get("sat_dir"), dati.get("sat_price")
                            if s_dir and s_base is not None:
                                spia = " 🟢" if (prezzo > s_base if s_dir == "BUY" else prezzo < s_base) else " 🔴"
                        elif stato == "FASE_3 + Ultima":
                            f3_dir, f3_base = dati.get("fase3_dir"), dati.get("fase3_current_base")
                            if f3_dir and f3_base is not None:
                                spia = " 🟢" if (prezzo < f3_base + (dati.get("tp", 50)/4)*mult if f3_dir == "BUY" else prezzo > f3_base - (dati.get("tp", 50)/4)*mult) else " 🔴"
                    
                    if dati.get("ticket2_active"):
                        t2_dir, t2_entry = dati.get("ticket2_dir"), dati.get("ticket2_entry")
                        if t2_dir and t2_entry is not None:
                            spia_t2 = " 🟢" if (prezzo > t2_entry if t2_dir == "BUY" else prezzo < t2_entry) else " 🔴"
                            stato_display += f" [+ TICKET2 {spia_t2}]"

                    if not is_attivo and stato == "IN_ATTESA":
                        stato_visivo = f"<span style='background-color: rgba(108, 117, 125, 0.15); color: #abb2bf; padding: 4px 8px; border-radius: 4px; font-weight: bold; font-size: 0.82rem;'>{'⚪ Ciclo Concluso (Spenta)' if storico else '⚪ Spenta / In Attesa'}</span>"
                    elif not is_attivo:
                        stato_visivo = f"<span style='background-color: rgba(220, 53, 69, 0.15); color: #ff4b4b; padding: 4px 8px; border-radius: 4px; font-weight: bold; font-size: 0.82rem;'>🔴 SPENTA ({stato_display})</span>"
                    elif stato == "FASE_2_STANDBY":
                        stato_visivo = f"<span style='background-color: #FFD700; color: #000000; padding: 4px 8px; border-radius: 4px; font-weight: bold; font-size: 0.82rem;'>⏳ STANDBY (Attesa Rientro)</span>"
                    else:
                        stato_visivo = f"<span style='background-color: rgba(40, 167, 69, 0.15); color: #09ab3b; padding: 4px 8px; border-radius: 4px; font-weight: bold; font-size: 0.82rem;'>⚡ ATTIVA ({stato_display}{spia})</span>"
                    
                    has_anomalia = bool(dati.get("alert_falso_allarme") or dati.get("errore_avvio") or dati.get("errore_ripristino") or dati.get("msg_manuale"))
                    
                    if has_anomalia:
                        bg_color = "#FFC107" # Giallo
                        text_color = "black"
                    elif is_attivo:
                        bg_color = "#198754" # Verde
                        text_color = "white"
                    else:
                        bg_color = "#E97451" # Salmone
                        text_color = "white"
                        
                    marker_class = f"btn-marker-{nome.replace('/', '').replace(' ', '')}"
                    css_marker = f"""<style>
                    div[data-testid="stHorizontalBlock"]:has(.{marker_class}) {{
                        margin-bottom: -15px !important;
                    }}
                    div[data-testid="stColumn"]:has(.{marker_class}) div[data-testid="stButton"] > button {{
                        background-color: {bg_color} !important; border-color: {bg_color} !important; color: {text_color} !important;
                    }}
                    </style>"""
                    
                    c1, c2, c3, c4 = st.columns([1.5, 3.5, 1.8, 3.2], vertical_alignment="center")
                    with c1:
                        st.markdown(f"<span class='{marker_class}'></span>{css_marker}", unsafe_allow_html=True)
                        if st.button(nome, key=f"wip_{conto_selezionato}_{nome}", type="primary", use_container_width=True):
                            mostra_diario_wip(nome, storico)
                    
                    c2.markdown(f"<div style='height: 32px; display: flex; align-items: center;'>{stato_visivo}</div>", unsafe_allow_html=True)
                    c3.markdown(f"<div style='height: 32px; display: flex; align-items: center; font-family: monospace; font-size: 1.1rem; color: #FFD700; letter-spacing: 0.5px;'>{prezzo}</div>", unsafe_allow_html=True)
                    ultimo_evento = storico[-1] if storico else "Nessun evento registrato in questo ciclo."
                    c4.markdown(f"<div style='font-size: 0.85rem; color: white; font-style: italic; line-height: 1.3; display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden;'>{ultimo_evento}</div>", unsafe_allow_html=True)
                    st.markdown("<div style='margin-bottom: 12px;'></div>", unsafe_allow_html=True)
                    
        renderizza_sintesi()

    with tab_operativa:
        @st.fragment(run_every=15)
        def renderizza_dati_live():
            memoria_attuale = carica_memoria(conto_selezionato) 
            stato = leggi_stato_sistema(conto_selezionato)
            distanze_minime = stato.get("distanze_minime", {})
            prezzi_live = stato.get("prezzi_live", {})
            prezzi_bid_ask = stato.get("prezzi_bid_ask", {})
            
            col_titolo_main, col_btn_restart = st.columns([4, 1])
            with col_titolo_main:
                st.markdown("<h1 style='color: #FFD700; margin-top: -15px;'>⚙️ Dashboard Macchinetta IG</h1>", unsafe_allow_html=True)
            with col_btn_restart:
                st.write("") 
                if st.button("🔄 RESTART VM", help="Elimina il token attuale e forza il rinnovo della sessione IG", width="stretch", key=f"RESTART_{conto_selezionato}"):
                    path_token = os.path.join(conto_selezionato, FILE_TOKEN)
                    if os.path.exists(path_token): os.remove(path_token) 
                    st.rerun()

            motore_attivo = False
            path_stato = os.path.join(conto_selezionato, STATO_SISTEMA)
            if os.path.exists(path_stato) and (time.time() - os.path.getmtime(path_stato)) < 60: motore_attivo = True

            col_head1, col_head2 = st.columns([1.6, 2])
            with col_head1:
                with st.container(border=True):
                    st.markdown(f"**Stato Sistema:** {'🟢 Connesso' if motore_attivo else '🔴 Motore Offline'}")
                    st.markdown(f"📶 **IG API:** {'OK' if motore_attivo else 'SCONNESSO'} &nbsp;&nbsp; | &nbsp;&nbsp; 📈 **Stream:** {'Live' if motore_attivo else 'FERMO'}")
                    st.markdown(f"<div style='white-space: nowrap;'>🕒 <b>LAST:</b> {stato['ultimo_aggiornamento']} &nbsp;|&nbsp; ⏱️ <b>Sessione:</b> {stato['durata_sessione']}</div>", unsafe_allow_html=True)
                    st.markdown("<div style='margin-top: 15px;'></div>", unsafe_allow_html=True)
                    if st.button("🔄 Aggiorna dati Dashboard", width="stretch", key=f"REFRESH_{conto_selezionato}"): st.rerun()

            with col_head2:
                with st.container(border=True):
                    c_bal1, c_bal2 = st.columns(2)
                    c_bal1.metric("CAPITALE TOTALE", f"{formatta_eur(stato.get('saldo', '0'))} EUR")
                    c_bal2.metric("CAPITALE DISPONIBILE", f"{formatta_eur(stato.get('disponibile', '0'))} EUR")
                    c_bal3, c_bal4 = st.columns(2)
                    c_bal3.metric("MARGINE UTILIZZATO", f"{formatta_eur(stato.get('margine', '0'))} EUR")
                    c_bal4.metric("DRAWDOWN (P/L)", f"{formatta_eur(stato.get('drawdown', '0'))} EUR")
                    st.caption(stato.get('messaggio', ''))

            st.markdown("---")

            def crea_riquadro_strumento(nome, tipo, tp_default, opp_default, dts_default, size_default=4):
                with st.container(border=True):
                    dati_salvati = memoria_attuale.get(nome, {})
                    stato_corrente = dati_salvati.get("stato", "IN_ATTESA")
                    stato_attivo = dati_salvati.get("attivo", False)
                    direzione = dati_salvati.get("direzione", "")
                    modalita_manuale = dati_salvati.get("modalita_manuale", False)
                    is_sospeso_wk = dati_salvati.get("sospeso_weekend", False)
                    msg_weekend = dati_salvati.get("msg_weekend", "")
                    msg_manuale = dati_salvati.get("msg_manuale", "")
                    errore_avvio, errore_ripristino = dati_salvati.get("errore_avvio", False), dati_salvati.get("errore_ripristino", False)
                    stato_corrente_disp = stato_corrente.replace("OverGain", "OG").replace("OverLoss", "OL")
                    
                    tp_val, opp_val, dts_val = dati_salvati.get("tp", tp_default), dati_salvati.get("opp", opp_default), dati_salvati.get("dts", dts_default)
                    min_impostato = min(opp_val, dts_val, tp_val / 4)
                    min_richiesto_ig = distanze_minime.get(nome, 0)
                    is_distanza_pericolosa = min_richiesto_ig > 0 and min_impostato <= min_richiesto_ig

                    col_titolo, col_salva, col_pulisci = st.columns([2.7, 0.9, 1.2], vertical_alignment="center")
                    with col_titolo:
                        badge = "🟢 <b>[ Auto ]</b>" if not modalita_manuale else "🟠 <b>[ Manuale ]</b>"
                        st.markdown(f"<div style='font-size: 1.4rem; font-weight: bold; white-space: nowrap; margin-bottom: -5px;'><span style='color: #FFD700;'>{nome}</span> <span style='font-size: 0.85rem; padding-left: 4px; vertical-align: middle; color: #abb2bf;'>{badge}</span></div>", unsafe_allow_html=True)
                        prezzi_ba = prezzi_bid_ask.get(nome, {})
                        bid_ask_str = f"Bid: <span style='color:#ff4b4b;'>{prezzi_ba.get('bid', '-')}</span> | Ask: <span style='color:#09ab3b;'>{prezzi_ba.get('ask', '-')}</span>" if prezzi_ba else "<span style='color: #666;'>In aggiornamento...</span>"
                        st.markdown(f"<div style='font-size: 0.8rem; color: #888; margin-top: -2px; margin-bottom: 5px;'>{tipo} &nbsp;•&nbsp; {bid_ask_str}</div>", unsafe_allow_html=True)
                        
                    with col_salva:
                        if st.button("💾 Salva", key=f"SAVE_{conto_selezionato}_{nome}", help="Conferma e salva TP, OPP, DTS e Size", width="stretch"):
                            memoria_attuale[nome] = {
                                **dati_salvati, 
                                "tp": st.session_state.get(f"{conto_selezionato}_{nome}_tp", tp_val), 
                                "opp": st.session_state.get(f"{conto_selezionato}_{nome}_opp", opp_val), 
                                "dts": st.session_state.get(f"{conto_selezionato}_{nome}_dts", dts_val), 
                                "size": st.session_state.get(f"{conto_selezionato}_{nome}_size", dati_salvati.get("size", size_default)),
                                "errore_avvio": False, "errore_ripristino": False, "msg_manuale": ""
                            }
                            salva_memoria(conto_selezionato, memoria_attuale)
                            st.rerun() 
                            
                    with col_pulisci:
                        if st.button("🧹 Pulisci DB", key=f"CLN_{conto_selezionato}_{nome}", help="Forza pulizia su IG e resetta a zero", width="stretch"):
                            memoria_attuale[nome] = {**dati_salvati, "comando_reset": True, "errore_avvio": False, "errore_ripristino": False, "msg_manuale": ""}
                            salva_memoria(conto_selezionato, memoria_attuale)
                            st.rerun()
                    
                    if errore_avvio: st.error("🛑 **AVVIO BLOCCATO:** IG ha rifiutato la griglia.")
                    elif errore_ripristino: st.error("🛑 **RIPRISTINO BLOCCATO:** 4 tentativi falliti. Passaggio in **MANUALE**.")
                    elif is_distanza_pericolosa: st.error(f"⚠️ **ATTENZIONE:** Stop Minimo IG: **{min_richiesto_ig} pt**. Impostato: **{min_impostato} pt**.")
                    else: st.caption(f"📏 Distanza richiesta da IG: **{min_richiesto_ig} pt** | Minimo Griglia: **{min_impostato} pt**")

                    if msg_weekend: st.error(f"🛑 {msg_weekend}")
                    if msg_manuale: st.error(msg_manuale)
                    
                    alert_falso = dati_salvati.get("alert_falso_allarme")
                    if alert_falso:
                        st.error(f"🛑 **{alert_falso}**")
                        if st.button("✅ OK, Ho capito", key=f"ACK_{conto_selezionato}_{nome}"):
                            memoria_attuale[nome] = {**dati_salvati, "alert_falso_allarme": ""}
                            salva_memoria(conto_selezionato, memoria_attuale)
                            st.rerun()
                    
                    c_in1, c_in2 = st.columns(2)
                    with c_in1: tp = st.number_input("TP", value=int(tp_val), step=5, format="%d", key=f"{conto_selezionato}_{nome}_tp")
                    with c_in2: opp = st.number_input("OPP", value=int(opp_val), step=1, format="%d", key=f"{conto_selezionato}_{nome}_opp")
                        
                    c_in3, c_in4 = st.columns(2)
                    with c_in3: dts = st.number_input("DTS", value=int(dts_val), step=1, format="%d", key=f"{conto_selezionato}_{nome}_dts")
                    with c_in4: size = st.number_input("Size", value=int(dati_salvati.get("size", size_default)), min_value=1, step=1, format="%d", key=f"{conto_selezionato}_{nome}_size")
                    
                    if modalita_manuale:
                        st.warning("⚠️ STRUMENTO IN MANUALE. Gestiscilo su IG.")
                        col_m1, col_m2 = st.columns(2, vertical_alignment="center")
                        with col_m1:
                            if st.button("🛰️ RIATTIVA AUTO (Fase 2)", key=f"RIATT_{conto_selezionato}_{nome}", width="stretch"):
                                memoria_attuale[nome] = {**dati_salvati, "comando_riattiva_fase2": True, "msg_manuale": ""}
                                salva_memoria(conto_selezionato, memoria_attuale)
                                st.rerun()
                        with col_m2:
                            if st.button("🔄 Restart Fase 1", key=f"RES_{conto_selezionato}_{nome}", width="stretch"):
                                memoria_attuale[nome] = {"attivo": False, "direzione": "", "tp": tp, "opp": opp, "dts": dts, "size": size, "stato": "IN_ATTESA", "modalita_manuale": False, "comando_manuale": False, "errore_avvio": False, "errore_ripristino": False, "msg_manuale": ""}
                                salva_memoria(conto_selezionato, memoria_attuale)
                                st.rerun()
                    elif not stato_attivo:
                        col_l, col_s = st.columns(2)
                        with col_l:
                            if st.button("🚀AVVIA LONG", key=f"L_{conto_selezionato}_{nome}", width="stretch"):
                                memoria_attuale[nome] = {"attivo": True, "direzione": "LONG", "tp": tp, "opp": opp, "dts": dts, "size": size, "stato": "IN_ATTESA", "storico_wip": [], "errore_avvio": False, "errore_ripristino": False, "comando_manuale": False, "msg_manuale": ""}
                                salva_memoria(conto_selezionato, memoria_attuale)
                                st.rerun()
                        with col_s:
                            if st.button("🚀AVVIA SHORT", key=f"S_{conto_selezionato}_{nome}", width="stretch"):
                                memoria_attuale[nome] = {"attivo": True, "direzione": "SHORT", "tp": tp, "opp": opp, "dts": dts, "size": size, "stato": "IN_ATTESA", "storico_wip": [], "errore_avvio": False, "errore_ripristino": False, "comando_manuale": False, "msg_manuale": ""}
                                salva_memoria(conto_selezionato, memoria_attuale)
                                st.rerun()
                        if st.button("⚖️ AVVIO SINCRONO MULTICONTO", key=f"SYNC_BTN_{conto_selezionato}_{nome}", use_container_width=True):
                            st.session_state[f"sync_open_{nome}"] = True
                            st.rerun()
                            
                        if st.session_state.get(f"sync_open_{nome}", False):
                            dialog_sync_start(conto_selezionato, nome)
                    else:
                        c_stop, c_man, c_wk, c_sync = st.columns([1.7, 2.3, 2.3, 1.7], vertical_alignment="center")
                        with c_stop:
                            if st.button("⏹️ STOP", key=f"STOP_{conto_selezionato}_{nome}", help="Chiude tutto e resetta a zero", width="stretch"):
                                pl = prezzi_live.get(nome, "")
                                vecchio_wip = dati_salvati.get("storico_wip", [])
                                vecchio_wip.append(f"[{datetime.now().strftime('%d/%m %H:%M:%S')}] 🛑 Tasto STOP premuto. Macchinetta spenta.")
                                memoria_attuale[nome] = {**dati_salvati, "attivo": False, "direzione": "", "stato": "IN_ATTESA", "kill_switch": True, "sospeso_weekend": False, "tp": tp, "opp": opp, "dts": dts, "size": size, "storico_wip": vecchio_wip, "errore_avvio": False, "errore_ripristino": False, "comando_manuale": False, "msg_manuale": ""}
                                salva_memoria(conto_selezionato, memoria_attuale)
                                st.rerun()
                        with c_man:
                            if st.button("👤 MANUALE", key=f"MAN_{conto_selezionato}_{nome}", width="stretch"):
                                memoria_attuale[nome] = {**dati_salvati, "comando_manuale": True, "errore_avvio": False, "errore_ripristino": False, "msg_manuale": ""}
                                salva_memoria(conto_selezionato, memoria_attuale)
                                st.rerun()
                        with c_wk:
                            if "FASE_2" in stato_corrente or is_sospeso_wk:
                                if st.button("▶️ RIPRENDI" if is_sospeso_wk else "🌴 WEEKEND", key=f"WK_{conto_selezionato}_{nome}", width="stretch"):
                                    memoria_attuale[nome] = {**dati_salvati, "comando_riprendi": True if is_sospeso_wk else False, "comando_weekend": False if is_sospeso_wk else True, "msg_weekend": "", "tp": tp, "opp": opp, "dts": dts, "size": size, "errore_avvio": False, "errore_ripristino": False, "msg_manuale": ""}
                                    salva_memoria(conto_selezionato, memoria_attuale)
                                    st.rerun()
                        with c_sync:
                            if st.button("🔄 SYNC", key=f"SYNC_{conto_selezionato}_{nome}", width="stretch"):
                                dialog_sync(conto_selezionato, nome)

                    if not modalita_manuale:
                        if stato_attivo:
                            if is_sospeso_wk: st.warning(f"🌴 IN PAUSA WEEKEND ({direzione}) | In attesa di ripresa")
                            elif stato_corrente == "FASE_2_STANDBY": st.markdown("<div style='background-color: #FFD700; color: #000000; padding: 10px; border-radius: 6px; font-weight: bold; margin-bottom: 1rem;'>⏳ IN ATTESA DI RIENTRO | Motore in Stand-By</div>", unsafe_allow_html=True)
                            else: st.success(f"🟢 ATTIVO ({direzione}) | Motore: {stato_corrente_disp}")
                        else: st.error(f"🔴 SPENTO | Motore: {stato_corrente_disp}")

            tutti_strumenti = ["AUD/CAD", "AUD/NZD", "CAD/JPY", "EUR/GBP", "GBP/USD", "USD/CAD", "USD/CHF", "USD/JPY", "Spot Gold", "US 500 Cash"]
            for i in range(0, len(tutti_strumenti), 2):
                c1, c2 = st.columns(2)
                with c1:
                    crea_riquadro_strumento(tutti_strumenti[i], "Asset" if tutti_strumenti[i] in ["Spot Gold", "US 500 Cash"] else "Forex Mini", *( (100, 20, 10) if tutti_strumenti[i] in ["Spot Gold", "US 500 Cash"] else (50, 10, 5) ), 4)
                with c2:
                    if i + 1 < len(tutti_strumenti):
                        crea_riquadro_strumento(tutti_strumenti[i+1], "Asset" if tutti_strumenti[i+1] in ["Spot Gold", "US 500 Cash"] else "Forex Mini", *( (100, 20, 10) if tutti_strumenti[i+1] in ["Spot Gold", "US 500 Cash"] else (50, 10, 5) ), 4)

        renderizza_dati_live()

    with tab_restore:
        st.title("🛠️ Strumento di Recovery")
        st.markdown("Wizard guidato per l'inserimento manuale o la correzione tattica di un ordine mancante. Calcolato in tempo reale in base alla tua strategia.")

        col1, col2, col3 = st.columns(3)
        with col1:
            tutti_strumenti = ["AUD/CAD", "AUD/NZD", "CAD/JPY", "EUR/GBP", "GBP/USD", "USD/CAD", "USD/CHF", "USD/JPY", "Spot Gold", "US 500 Cash"]
            r_nome = st.selectbox("1. Seleziona Strumento", tutti_strumenti)
        with col2:
            r_fase = st.selectbox("2. Seleziona Fase", ["FASE 1", "FASE 2", "FASE 3"])

        memoria_attuale = carica_memoria(conto_selezionato)
        dati = memoria_attuale.get(r_nome, {})
        stato = leggi_stato_sistema(conto_selezionato)
        prezzi_live = stato.get("prezzi_live", {})
        prezzo_live = prezzi_live.get(r_nome)
        
        opzioni = []
        if r_fase == "FASE 1": 
            opzioni = ["Ordine MICRO (Pendente)"]
        elif r_fase == "FASE 2": 
            opzioni = ["Posizione TICKET1 (A Mercato)", "Ordine TICKET2 (Pendente)", "Ordini SAT1 OCO (Entrambi)", "Ordine SAT1 OCO (Solo BUY)", "Ordine SAT1 OCO (Solo SELL)", "Posizione SAT2 (A Mercato)", "Ordine OVERGAIN (Pendente)", "Ordine OVERLOSS (Pendente)"]
        else: 
            opzioni = ["Ordine ULTIMA (Pendente)"]

        with col3:
            r_anom = st.selectbox("3. Seleziona Elemento Mancante", opzioni)

        st.markdown("---")
        st.subheader("🩺 Diagnosi & Recovery")

        if not dati:
            st.warning("Lo strumento non ha dati in memoria. Impossibile calcolare il Recovery.")
        elif not prezzo_live:
            st.warning("Prezzo live non disponibile. Attendi la connessione con IG.")
        else:
            c = CONFIG_STRUMENTI[r_nome]
            dec = c["decimali"]
            mult = c["moltiplicatore"]
            s_core = float(dati.get("size", 4))
            s_mezzo = max(1.0, s_core / 2)
            s_quarto = max(0.1, s_core / 4)
            tp4_val = round((dati.get("tp", 50) / 4) * mult, dec)
            opp_val = round(dati.get("opp", 20) * mult, dec)
            dir_core = dati.get("direzione")
            
            # --- TENTATIVO DI RECUPERO DATI SAT1 DA LIVE ---
            s_dir = dati.get("sat_dir")
            s_price = dati.get("sat_price")
            if not s_dir or not s_price:
                pos_live = stato.get("posizioni", [])
                t_epic = c.get("epic")
                core_ids = [p['position']['dealId'] for p in pos_live if p['market']['epic'] == t_epic and float(p['position']['size']) == s_core]
                sat1_live = [p for p in pos_live if p['market']['epic'] == t_epic and float(p['position']['size']) == s_mezzo and p['position']['dealId'] not in core_ids]
                if sat1_live:
                    if not s_dir: s_dir = sat1_live[0]['position']['direction']
                    if not s_price: s_price = float(sat1_live[0]['position']['level'])
            # -----------------------------------------------
            
            cmd_data = None
            
            if "MICRO" in r_anom:
                p_base = dati.get("prezzo_base")
                if not p_base:
                    st.error("Prezzo base Core mancante in memoria. Impossibile calcolare la Micro.")
                else:
                    m_dir = "SELL" if dir_core == "LONG" else "BUY"
                    lvl = round(p_base + tp4_val if m_dir == "SELL" else p_base - tp4_val, dec)
                    lim = p_base
                    stop = round(p_base + 2*tp4_val if m_dir == "SELL" else p_base - 2*tp4_val, dec)
                    cmd_data = {"azione": "PENDENTE", "dir": m_dir, "size": s_mezzo, "livello": lvl, "tipo": "LIMIT", "lim": lim, "stop": stop, "etichetta": "[RECOVERY MICRO]"}

            elif "TICKET1" in r_anom:
                t_dir = "BUY" if dir_core == "LONG" else "SELL"
                st.info("Il Ticket (post-assicurazione) è una POSIZIONE A MERCATO. Cliccando il bottone, la macchina entrerà immediatamente al prezzo live e ricalcolerà Stop e Limit in base all'OPP.")
                
                t_base = dati.get("ticket1_base") or prezzo_live
                lim = round(t_base + opp_val if t_dir == "BUY" else t_base - opp_val, dec)
                stop = round(t_base - opp_val if t_dir == "BUY" else t_base + opp_val, dec)
                cmd_data = {"azione": "MERCATO", "dir": t_dir, "size": s_mezzo, "lim": lim, "stop": stop, "etichetta": "[RECOVERY TICKET1]"}

            elif "TICKET2" in r_anom:
                t2_dir = dati.get("ticket2_dir")
                t2_entry = dati.get("ticket2_entry")
                if not t2_dir or not t2_entry:
                    st.error("Dati TICKET2 non trovati in memoria. Verifica che il Ticket2 sia stato attivato dal Motore.")
                else:
                    st.info("Il Ticket2 (Ping-Pong) è un ORDINE PENDENTE LIMIT. Sarà reinserito al livello originale.")
                    lim_lvl_t2 = round(t2_entry + tp4_val if t2_dir == "BUY" else t2_entry - tp4_val, dec)
                    cmd_data = {"azione": "PENDENTE", "dir": t2_dir, "size": s_mezzo, "livello": t2_entry, "tipo": "LIMIT", "lim": lim_lvl_t2, "stop": None, "etichetta": "[RECOVERY TICKET2]"}

            elif "SAT1 OCO" in r_anom:
                p_base = dati.get("prezzo_base")
                if not p_base:
                    st.error("Prezzo base Core mancante in memoria. Impossibile calcolare i Satelliti OCO.")
                else:
                    tp2_val = round((dati.get("tp", 50) / 2) * mult, dec)
                    if dir_core == "LONG":
                        lvl_l = round(p_base + tp2_val, dec)
                        lvl_s = round((p_base - opp_val) - tp2_val, dec)
                    else:
                        lvl_l = round((p_base + opp_val) + tp2_val, dec)
                        lvl_s = round(p_base - tp2_val, dec)
                        
                    lim_l = round(lvl_l + tp2_val, dec)
                    stop_l = round(lvl_l - tp2_val, dec)
                    lim_s = round(lvl_s - tp2_val, dec)
                    stop_s = round(lvl_s + tp2_val, dec)
                    
                    if "Solo BUY" in r_anom:
                        st.info("Verrà reinserito SOLO l'ordine SAT1 OCO lato BUY.")
                        cmd_data = {"azione": "PENDENTE", "dir": "BUY", "size": s_mezzo, "livello": lvl_l, "tipo": "STOP", "lim": lim_l, "stop": stop_l, "etichetta": "[RECOVERY SAT1 OCO BUY]"}
                    elif "Solo SELL" in r_anom:
                        st.info("Verrà reinserito SOLO l'ordine SAT1 OCO lato SELL.")
                        cmd_data = {"azione": "PENDENTE", "dir": "SELL", "size": s_mezzo, "livello": lvl_s, "tipo": "STOP", "lim": lim_s, "stop": stop_s, "etichetta": "[RECOVERY SAT1 OCO SELL]"}
                    else:
                        st.info("Verranno ricalcolati e inseriti ENTRAMBI gli ordini SAT1 OCO (Buy e Sell).")
                        cmd_data = {
                            "azione": "SAT1_OCO", "size": s_mezzo, 
                            "lvl_l": lvl_l, "lim_l": lim_l, "stop_l": stop_l,
                            "lvl_s": lvl_s, "lim_s": lim_s, "stop_s": stop_s,
                            "etichetta": "[RECOVERY SAT1 OCO]"
                        }

            elif "SAT2" in r_anom:
                if not s_dir:
                    st.error("Dati direzionali del SAT1 innescato mancanti in memoria e non rilevabili tra le posizioni aperte.")
                else:
                    i_dir = "SELL" if s_dir == "BUY" else "BUY"
                    st.info("SAT2 è una POSIZIONE A MERCATO. Cliccando il bottone, la macchina entrerà immediatamente al prezzo live calcolando 1/4 della size Core.")
                    cmd_data = {"azione": "MERCATO", "dir": i_dir, "size": s_quarto, "lim": None, "stop": None, "etichetta": "[RECOVERY SAT2]"}

            elif "OVERGAIN" in r_anom:
                if not s_dir or not s_price:
                    st.error("Dati direzionali del SAT1 innescato mancanti in memoria e non rilevabili tra le posizioni aperte.")
                else:
                    i_dir = "SELL" if s_dir == "BUY" else "BUY"
                    lvl = round(s_price + tp4_val if i_dir == "SELL" else s_price - tp4_val, dec)
                    lim = s_price
                    cmd_data = {"azione": "PENDENTE", "dir": i_dir, "size": s_mezzo, "livello": lvl, "tipo": "LIMIT", "lim": lim, "stop": None, "etichetta": "[RECOVERY OVERGAIN]"}

            elif "OVERLOSS" in r_anom:
                if not s_dir or not s_price:
                    st.error("Dati direzionali del SAT1 innescato mancanti in memoria e non rilevabili tra le posizioni aperte.")
                else:
                    i_dir = "SELL" if s_dir == "BUY" else "BUY"
                    lvl = round(s_price - tp4_val if i_dir == "SELL" else s_price + tp4_val, dec)
                    stop = s_price
                    cmd_data = {"azione": "PENDENTE", "dir": i_dir, "size": s_quarto, "livello": lvl, "tipo": "STOP", "lim": None, "stop": stop, "etichetta": "[RECOVERY OVERLOSS]"}

            elif "ULTIMA" in r_anom:
                f3_dir = dati.get("fase3_dir")
                f3_current_base = dati.get("fase3_current_base")
                f3_step = dati.get("fase3_step", 1)
                if not f3_dir or not f3_current_base:
                    st.error("Dati Fase 3 mancanti in memoria.")
                else:
                    d_contro = "SELL" if f3_dir == "BUY" else "BUY"
                    s_last = s_mezzo if f3_step == 1 else (s_core * 0.15)
                    lvl = round(f3_current_base + tp4_val if d_contro == "SELL" else f3_current_base - tp4_val, dec)
                    lim = f3_current_base
                    cmd_data = {"azione": "PENDENTE", "dir": d_contro, "size": s_last, "livello": lvl, "tipo": "LIMIT", "lim": lim, "stop": None, "etichetta": "[RECOVERY ULTIMA]"}

            if cmd_data:
                with st.container(border=True):
                    if cmd_data["azione"] == "PENDENTE":
                        oltrepassato = is_oltrepassato(cmd_data["tipo"], cmd_data["dir"], cmd_data["livello"], prezzo_live)
                        
                        st.markdown(f"**Direzione Calcolata:** `{cmd_data['dir']}` &nbsp;&nbsp;|&nbsp;&nbsp; **Size:** `{cmd_data['size']}` &nbsp;&nbsp;|&nbsp;&nbsp; **Tipo Ottimale:** `{cmd_data['tipo']}`")
                        st.markdown(f"**Livello Matematico Ideale:** <span style='font-size: 1.2rem; color: #FFD700;'>{formatta_numero(cmd_data['livello'], dec)}</span> &nbsp;&nbsp;|&nbsp;&nbsp; *(Prezzo Live attuale: {prezzo_live})*", unsafe_allow_html=True)
                        
                        st.write("")
                        
                        if oltrepassato:
                            st.error(f"⚠️ **ATTENZIONE: MERCATO SCAVALCATO.** Il prezzo attuale ({prezzo_live}) ha oltrepassato il livello ideale ({formatta_numero(cmd_data['livello'], dec)}). I server IG rifiuteranno l'inserimento di un ordine {cmd_data['tipo']}.")
                            
                            st.markdown("### Azioni di Ripristino Disponibili:")
                            st.markdown(f"**1️⃣ ATTESA TATTICA:** Piazza un ordine inverso (`LIMIT` a `{formatta_numero(cmd_data['livello'], dec)}`). Non paghi slippage. Ripristini l'esatta geometria della strategia attendendo che il prezzo faccia pullback (ritracci). Rischio: se il prezzo non torna indietro, resti scoperto.")
                            st.markdown(f"**2️⃣ COPERTURA IMMEDIATA:** Entra a `MERCATO` al prezzo attuale (`{prezzo_live}`). Chiudi subito la falla di sicurezza, ma accetti uno slippage pari alla differenza tra il prezzo ideale e quello attuale.")
                            st.markdown(f"**3️⃣ TENTATIVO STANDARD:** Prova a forzare l'ordine originale (`{cmd_data['tipo']}` a `{formatta_numero(cmd_data['livello'], dec)}`). Da usare SOLO se vedi che il prezzo sta fluttuando e potrebbe rientrare nei limiti concessi da IG proprio mentre clicchi.")
                            
                            st.write("")
                            colA, colB, colC = st.columns(3)
                            
                            trap_type = "LIMIT" if cmd_data["tipo"] == "STOP" else "STOP"
                                
                            with colA:
                                if st.button(f"1️⃣ Tattica: {trap_type} a {formatta_numero(cmd_data['livello'], dec)}", use_container_width=True, help="Piazza la trappola attendendo il rimbalzo del mercato."):
                                    cmd_trap = cmd_data.copy()
                                    cmd_trap["tipo"] = trap_type
                                    cmd_trap["etichetta"] += " (LIMIT TATTICO)"
                                    piazza_restore(conto_selezionato, r_nome, cmd_trap)
                            with colB:
                                if st.button(f"2️⃣ Copertura: MERCATO a {prezzo_live}", use_container_width=True, help="Copri la posizione istantaneamente al prezzo di adesso."):
                                    cmd_mkt = cmd_data.copy()
                                    cmd_mkt["azione"] = "MERCATO"
                                    cmd_mkt["etichetta"] += " (FORZATURA MERCATO)"
                                    piazza_restore(conto_selezionato, r_nome, cmd_mkt)
                            with colC:
                                if st.button(f"3️⃣ Forza: {cmd_data['tipo']} a {formatta_numero(cmd_data['livello'], dec)}", use_container_width=True, help="Tenta di inviare la richiesta originale a IG."):
                                    piazza_restore(conto_selezionato, r_nome, cmd_data)
                        else:
                            st.success(f"🟢 **Condizioni nei parametri.** Il livello {formatta_numero(cmd_data['livello'], dec)} è piazzabile in sicurezza senza incorrere in rifiuti di IG.")
                            if st.button(f"🚀 Invia Ordine a {formatta_numero(cmd_data['livello'], dec)}", use_container_width=True, type="primary"):
                                piazza_restore(conto_selezionato, r_nome, cmd_data)
                    elif cmd_data["azione"] == "SAT1_OCO":
                        st.markdown(f"**Ordini da Inviare:** `BUY` a {formatta_numero(cmd_data['lvl_l'], dec)} &nbsp;&nbsp;|&nbsp;&nbsp; `SELL` a {formatta_numero(cmd_data['lvl_s'], dec)} &nbsp;&nbsp;|&nbsp;&nbsp; **Size:** `{cmd_data['size']}`")
                        st.success("🟢 **Ordini Simultanei Pronti.** I livelli teorici sono stati calcolati in base alla strategia in corso.")
                        if st.button("🚀 Invia Entrambi gli Ordini (OCO SAT1)", use_container_width=True, type="primary"):
                            piazza_restore(conto_selezionato, r_nome, cmd_data)

                    else: # MERCATO (Es. Ticket o SAT2)
                        st.markdown(f"**Direzione:** `{cmd_data.get('dir', 'N/D')}` &nbsp;&nbsp;|&nbsp;&nbsp; **Size:** `{cmd_data['size']}` &nbsp;&nbsp;|&nbsp;&nbsp; **Azione Reale:** `INGRESSO A MERCATO`")
                        if st.button(f"🚀 Entra a MERCATO adesso (Prezzo Live: {prezzo_live})", use_container_width=True, type="primary"):
                            piazza_restore(conto_selezionato, r_nome, cmd_data)

    with tab_statistiche:
        st.title("📊 Analisi Operazioni & Profitti (EUR)")
        path_storico = os.path.join(conto_selezionato, FILE_STORICO)
        if os.path.exists(path_storico):
            # Cerca prima data
            prima_data_db = None
            try:
                df_temp = pd.read_csv(path_storico)
                if not df_temp.empty:
                    df_temp['Data_Op'] = pd.to_datetime(df_temp['Data'], format='%Y-%m-%d %H:%M:%S').dt.date
                    prima_data_db = df_temp['Data_Op'].min()
            except:
                pass
                
            if prima_data_db:
                st.markdown(f"<div style='font-size: 0.9rem; color: #888; margin-bottom: 15px;'>ℹ️ <b>Prima data disponibile nel database attuale:</b> {prima_data_db.strftime('%d/%m/%Y')}</div>", unsafe_allow_html=True)
                
            pref_file = os.path.join(conto_selezionato, "preferenze_ui.json")
            prefs = {}
            if os.path.exists(pref_file):
                try:
                    with open(pref_file, "r") as f: prefs = json.load(f)
                except: pass
                
            saved_inizio_str = prefs.get("data_inizio", (datetime.today() - timedelta(days=30)).strftime("%Y-%m-%d"))
            saved_fine_str = prefs.get("data_fine", datetime.today().strftime("%Y-%m-%d"))
            try:
                def_inizio = datetime.strptime(saved_inizio_str, "%Y-%m-%d").date()
                def_fine = datetime.strptime(saved_fine_str, "%Y-%m-%d").date()
            except:
                def_inizio = (datetime.today() - timedelta(days=30)).date()
                def_fine = datetime.today().date()

            c_data1, c_data2 = st.columns(2)
            with c_data1:
                data_inizio = st.date_input("📅 Data iniziale:", def_inizio, key="date_inizio")
            with c_data2:
                data_fine = st.date_input("📅 Data finale:", def_fine, key="date_fine")
                
            if data_inizio != def_inizio or data_fine != def_fine:
                prefs["data_inizio"] = data_inizio.strftime("%Y-%m-%d")
                prefs["data_fine"] = data_fine.strftime("%Y-%m-%d")
                with open(pref_file, "w") as f: json.dump(prefs, f, indent=4)
                
            st.write("")
            with st.expander("🗄️ Archiviazione Storico"):
                st.markdown("Usa questo strumento per alleggerire la Dashboard spostando i dati vecchi in un file di archivio (`storico_archiviato.csv`), rimuovendoli dalla vista principale ma senza perderli definitivamente.")
                prima_data_str = prima_data_db.strftime('%d/%m/%Y') if prima_data_db else "inizio"
                max_date = datetime.today().date() - timedelta(days=1)
                
                data_archiviazione = st.date_input(f"Archivia tutte le operazioni dal giorno {prima_data_str} al giorno (incluso):", value=max_date, max_value=max_date, format="DD/MM/YYYY", key="archivia_date")
                if st.button("🗄️ Archivia Ora", type="primary"):
                    try:
                        df_arch = pd.read_csv(path_storico)
                        df_arch['Data_Op'] = pd.to_datetime(df_arch['Data'], format='%Y-%m-%d %H:%M:%S').dt.date
                        mask_arch = df_arch['Data_Op'] <= data_archiviazione
                        
                        df_to_archive = df_arch.loc[mask_arch].copy()
                        df_to_keep = df_arch.loc[~mask_arch].copy()
                        
                        if not df_to_archive.empty:
                            df_to_archive = df_to_archive.drop(columns=['Data_Op'])
                            df_to_keep = df_to_keep.drop(columns=['Data_Op'])
                            
                            path_archivio = os.path.join(conto_selezionato, "storico_archiviato.csv")
                            if os.path.exists(path_archivio):
                                df_to_archive.to_csv(path_archivio, mode='a', header=False, index=False)
                            else:
                                df_to_archive.to_csv(path_archivio, index=False)
                                
                            df_to_keep.to_csv(path_storico, index=False)
                            st.success(f"✅ Archiviate {len(df_to_archive)} operazioni! Il database principale ora contiene {len(df_to_keep)} operazioni.")
                            time.sleep(1.5)
                            st.rerun()
                        else:
                            st.info("Non ci sono operazioni precedenti a questa data da archiviare.")
                    except Exception as e:
                        st.error(f"Errore durante l'archiviazione: {e}")
            st.write("")
            
            try:
                df = pd.read_csv(path_storico)
                df['Data_Operazione'] = pd.to_datetime(df['Data'], format='%Y-%m-%d %H:%M:%S').dt.date
                mask = (df['Data_Operazione'] >= data_inizio) & (df['Data_Operazione'] <= data_fine)
                df_filtrato = df.loc[mask].copy()
                
                if not df_filtrato.empty:
                    st.markdown("---")
                    st.metric("💰 TOTALONE P/L NEL PERIODO", f"€ {df_filtrato['Profitto_EUR'].sum():.2f}")
                    st.markdown("---")
                    
                    def categorizza_fase(fase_str):
                        f = str(fase_str).upper()
                        if "1" in f or "MICRO" in f or "ASSICURAZIONE" in f: return "F1"
                        if "2" in f or "TICKET1" in f or "SAT" in f or "OVERGAIN" in f or "OVERLOSS" in f or "OG" in f or "OL" in f: return "F2"
                        if "3" in f or "ULTIMA" in f or "TAGLIO" in f or "VITTORIA" in f: return "F3"
                        return "Altro"

                    df_filtrato['MacroFase'] = df_filtrato['Fase'].apply(categorizza_fase)

                    # --- RENDIMENTO PER STRUMENTO (Sopra) ---
                    st.subheader("Rendimento per Strumento")
                    
                    pivot_strum = pd.pivot_table(df_filtrato, values='Profitto_EUR', index='Strumento', columns='MacroFase', aggfunc='sum', fill_value=0)
                    
                    for col in ['F1', 'F2', 'F3', 'Altro']:
                        if col not in pivot_strum.columns:
                            pivot_strum[col] = 0.0
                            
                    pivot_strum['P/L Tot.'] = pivot_strum[['F1', 'F2', 'F3', 'Altro']].sum(axis=1)
                    pivot_strum = pivot_strum.reset_index()
                    pivot_strum = pivot_strum[['Strumento', 'P/L Tot.', 'F1', 'F2', 'F3', 'Altro']]
                    
                    html_t1 = "<table class='stat-table'><thead><tr><th>STRUMENTO</th><th>P/L TOT.</th><th>F1</th><th>F2</th><th>F3</th><th>ALTRO</th></tr></thead><tbody>"
                    for _, row in pivot_strum.iterrows():
                        strum = row['Strumento']
                        
                        def format_td(val, is_bold=False):
                            if abs(val) < 0.001: return "<td></td>"
                            color_class = "text-green" if val > 0 else "text-red"
                            bold_class = "text-bold" if is_bold else ""
                            return f"<td class='{color_class} {bold_class}'>€ {val:.2f}</td>"
                            
                        td_pl = format_td(row['P/L Tot.'], is_bold=True)
                        td_f1 = format_td(row['F1'])
                        td_f2 = format_td(row['F2'])
                        td_f3 = format_td(row['F3'])
                        td_alt = format_td(row['Altro'])
                        
                        html_t1 += f"<tr><td>{strum}</td>{td_pl}{td_f1}{td_f2}{td_f3}{td_alt}</tr>"
                    html_t1 += "</tbody></table>"
                    
                    st.markdown(html_t1, unsafe_allow_html=True)
                    st.markdown("<br>", unsafe_allow_html=True)
                    
                    # --- RENDIMENTO PER FASE (Sotto) ---
                    st.subheader("Rendimento per Fase")
                    df_fase = df_filtrato.groupby('Fase').agg(
                        Pnl_Totale=('Profitto_EUR', 'sum'),
                        Tot_Op=('Profitto_EUR', 'count'),
                        Vincenti=('Profitto_EUR', lambda x: (x > 0).sum()),
                        Perdenti=('Profitto_EUR', lambda x: (x <= 0).sum())
                    ).reset_index()
                    
                    html_t2 = "<table class='stat-table'><thead><tr><th>FASE</th><th>P/L TOT.</th><th>TOT. OP.</th><th>WIN</th><th>LOSS</th><th>WIN RATE %</th></tr></thead><tbody>"
                    for _, row in df_fase.iterrows():
                        fase = row['Fase']
                        pnl = row['Pnl_Totale']
                        tot_op = row['Tot_Op']
                        win = row['Vincenti']
                        loss = row['Perdenti']
                        wr = (win / tot_op * 100) if tot_op > 0 else 0
                        
                        pnl_class = "text-green text-bold" if pnl > 0 else ("text-red text-bold" if pnl < 0 else "text-bold")
                        pnl_str = f"€ {pnl:.2f}" if abs(pnl) >= 0.001 else "€ 0.00"
                        
                        win_class = "text-green" if win > 0 else ""
                        loss_class = "text-red" if loss > 0 else ""
                        wr_class = "text-green" if wr >= 50 else ("text-red" if wr > 0 else "")
                        
                        html_t2 += f"<tr><td>{fase}</td><td class='{pnl_class}'>{pnl_str}</td><td>{tot_op}</td><td class='{win_class}'>{win}</td><td class='{loss_class}'>{loss}</td><td class='{wr_class}'>{wr:.1f}%</td></tr>"
                    html_t2 += "</tbody></table>"
                    
                    st.markdown(html_t2, unsafe_allow_html=True)
                    

                    
                else:
                    st.info("Nessuna operazione registrata nel periodo selezionato.")
            except Exception as e:
                st.error(f"Errore nella lettura del file storico: {e}")
        else:
            st.warning("Nessun dato statistico disponibile. Il file storico verrà creato alla prima operazione chiusa.")

    with tab_console:
        @st.fragment(run_every=2)
        def renderizza_console():
            st.markdown("### 💻 Terminale di Bordo (Live)")
            st.markdown("Monitoraggio in tempo reale del Motore. Auto-aggiornamento ogni 2 secondi.")
            
            try:
                path_log = os.path.join(conto_selezionato, CONSOLE_LOG_FILE)
                with open(path_log, "r", encoding="utf-8") as f:
                    logs = f.read()
            except FileNotFoundError:
                logs = f"> In attesa di connessione col Motore per {conto_selezionato}..."
                
            st.code(logs, language="bash")
            
        renderizza_console()
