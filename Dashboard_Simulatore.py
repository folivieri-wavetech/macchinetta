import streamlit as st
import json
import os
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
import time
import pandas as pd
import requests
import re
from datetime import datetime, timedelta, timezone
from dotenv import dotenv_values
import plotly.graph_objects as go
import numpy as np

# --- CONFIGURAZIONI CENTRALI ---
FILE_MEMORIA = "memoria_parametri.json"
FILE_TOKEN = "token_ig.json"
FILE_STORICO = "storico_operazioni.csv"
CONSOLE_LOG_FILE = "console_live.log"
STATO_SISTEMA = "stato_sistema.json"
CREDENTIALS = {os.getenv("DASHBOARD_USER", "Marco"): os.getenv("DASHBOARD_PASSWORD", "Bolzano&1971")} 

# --- VOCABOLARIO ---
CONFIG_STRUMENTI = {
    "AUD/CAD": {"epic": "CS.D.AUDCAD.MINI.IP", "moltiplicatore": 0.0001, "decimali": 5, "valuta": "CAD", "valore_punto": 1, "margine_unitario": 310},
    "AUD/NZD": {"epic": "CS.D.AUDNZD.MINI.IP", "moltiplicatore": 0.0001, "decimali": 5, "valuta": "NZD", "valore_punto": 1, "margine_unitario": 310},
    "CAD/JPY": {"epic": "CS.D.CADJPY.MINI.IP", "moltiplicatore": 0.01, "decimali": 3, "valuta": "JPY", "valore_punto": 100, "margine_unitario": 210},
    "EUR/GBP": {"epic": "CS.D.EURGBP.MINI.IP", "moltiplicatore": 0.0001, "decimali": 5, "valuta": "GBP", "valore_punto": 1, "margine_unitario": 335},
    "GBP/USD": {"epic": "CS.D.GBPUSD.MINI.IP", "moltiplicatore": 0.0001, "decimali": 5, "valuta": "USD", "valore_punto": 1, "margine_unitario": 400},
    "USD/CAD": {"epic": "CS.D.USDCAD.MINI.IP", "moltiplicatore": 0.0001, "decimali": 5, "valuta": "CAD", "valore_punto": 1, "margine_unitario": 300},
    "USD/CHF": {"epic": "CS.D.USDCHF.MINI.IP", "moltiplicatore": 0.0001, "decimali": 5, "valuta": "CHF", "valore_punto": 1, "margine_unitario": 290},
    "USD/JPY": {"epic": "CS.D.USDJPY.MINI.IP", "moltiplicatore": 0.01, "decimali": 3, "valuta": "JPY", "valore_punto": 100, "margine_unitario": 290},
    "Spot Gold": {"epic": "CS.D.CFEGOLD.CBE.IP", "moltiplicatore": 1, "decimali": 1, "valuta": "EUR", "valore_punto": 1, "margine_unitario": 220},
    "US 500 Cash": {"epic": "IX.D.SPTRD.IBE.IP", "moltiplicatore": 1, "decimali": 1, "valuta": "EUR", "valore_punto": 1, "margine_unitario": 400}
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
        righe_eventi = []
        for riga in storico:
            match = re.search(r"\[Parziale:\s*([+-]?\d+(?:\.\d+)?)\s*€\]", riga)
            if match:
                totale += float(match.group(1))
            
            riga_colorata = re.sub(r"(\[Parziale:.*?\])", r"<span style='color: #FFD700;'>\1</span>", riga)
            righe_eventi.append(f"&bull; {riga_colorata}<br>")
        
        segno = "+" if totale > 0 else ""
        col_tot = "#09ab3b" if totale > 0 else ("#ff4b4b" if totale < 0 else "#FFD700")
        
        html_str = f"<div style='margin-bottom: 12px; padding-bottom: 8px; border-bottom: 1px dashed rgba(255,255,255,0.2); font-size: 1.05rem;'>"
        html_str += f"<span style='color: #FFD700;'><b>Totale aggiornato:</b> <span style='color: {col_tot}; font-weight: bold;'>{segno}{totale:.2f} €</span></span></div>"
        html_str += "<div style='font-size: 0.85rem; line-height: 1.6; max-height: 350px; overflow-y: auto; padding-right: 5px;'>"
        html_str += "".join(righe_eventi)
        html_str += "</div>"
        
        st.html(html_str)
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
        @media (min-width: 769px) {
            section[data-testid="stSidebar"] { min-width: 220px !important; max-width: 220px !important; }
        }
        button[data-testid="stNumberInputStepUp"], button[data-testid="stNumberInputStepDown"] { display: flex !important; }
        div[data-testid="stNumberInputContainer"] { padding-left: 0.2rem !important; padding-right: 0.2rem !important; }
        
        .table-responsive {
            width: 100% !important;
            overflow-x: auto !important;
            -webkit-overflow-scrolling: touch !important;
            margin-bottom: 20px !important;
            display: block !important;
        }

        /* CSS per Tabelle Portafoglio IG */
        .ig-table { width: 90%; max-width: 1400px; margin: 0 auto; border-collapse: collapse; font-family: -apple-system, BlinkMacSystemFont, sans-serif; font-size: 0.85rem; color: #d1d4dc; margin-bottom: 20px; }
        .ig-table th { text-align: center; color: white; padding: 10px 8px; border-bottom: 1px solid rgba(255,255,255,0.1); font-weight: 600; font-size: 0.75rem; text-transform: uppercase; }
        .ig-table th:first-child { text-align: left; padding-left: 15px; color: #888; }
        
        /* Master Row in Grassetto e sottolineato */
        .ig-row { border-bottom: 1px solid rgba(255,255,255,0.05); font-weight: normal; }
        .ig-master-row td { text-decoration: underline; text-underline-offset: 3px; }
        .ig-master-row span.ig-dot { text-decoration: none; display: inline-block; }
        
        .ig-row:hover { background-color: rgba(255,255,255,0.02); }
        .ig-row td { padding: 10px 8px; text-align: center; }
        .col-mercato { text-align: left !important; padding-left: 15px !important; }
        
        /* Sub Row NON in Grassetto e con P/L colorato preservato */
        .ig-subrow { background-color: rgba(0,0,0,0.2); font-weight: normal !important; }
        .ig-subrow td { color: #aaa; font-size: 0.8rem; border-bottom: none; padding: 6px 8px; font-weight: normal !important; text-decoration: none !important; }
        .ig-subrow td.pnl-pos { color: #3b82f6 !important; font-weight: bold !important; }
        .ig-subrow td.pnl-neg { color: #ef4444 !important; font-weight: bold !important; }

        .size-buy { color: #3b82f6; }
        .size-sell { color: #ef4444; }
        .ig-row .size-buy, .ig-row .size-sell { font-weight: normal; text-align: center !important; }
        
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

        @media (max-width: 1024px) {
            .ig-table { width: 100% !important; font-size: 0.82rem !important; }
            .ig-table th, .ig-table td { padding: 7px 5px !important; }
            .stat-table { font-size: 0.85rem !important; }
            .stat-table th, .stat-table td { padding: 7px 5px !important; }
            section[data-testid="stSidebar"] { min-width: 200px !important; max-width: 250px !important; }
        }

        @media (max-width: 768px) {
            .main .block-container {
                padding-top: 1.5rem !important;
                padding-left: 0.5rem !important;
                padding-right: 0.5rem !important;
                padding-bottom: 2rem !important;
                max-width: 100% !important;
            }
            h1 { font-size: 1.4rem !important; text-align: center !important; margin-bottom: 0.5rem !important; }
            h2 { font-size: 1.2rem !important; }
            h3 { font-size: 1.05rem !important; }
            h4 { font-size: 0.95rem !important; }
            div[data-testid="stMetricValue"] { font-size: 1.15rem !important; }
            div[data-testid="stMetricLabel"] { font-size: 0.75rem !important; }

            .ig-table { min-width: 580px !important; width: 100% !important; font-size: 0.75rem !important; margin-bottom: 10px !important; }
            .ig-table th, .ig-table td { padding: 5px 3px !important; font-size: 0.72rem !important; }
            .stat-table { min-width: 520px !important; width: 100% !important; font-size: 0.75rem !important; margin-bottom: 15px !important; }
            .stat-table th, .stat-table td { padding: 5px 3px !important; font-size: 0.72rem !important; }

            div[data-testid="stButton"] > button { padding: 4px 6px !important; font-size: 0.82rem !important; min-height: 38px !important; }
            div[data-testid="stButton"] > button[kind="primary"] { min-height: 34px !important; height: auto !important; font-size: 0.82rem !important; padding: 4px 8px !important; }
            div[data-testid="stButton"] > button[kind="secondary"] { min-height: 38px !important; height: auto !important; font-size: 0.82rem !important; }

            div[data-baseweb="tab-list"] {
                display: flex !important;
                overflow-x: auto !important;
                white-space: nowrap !important;
                -webkit-overflow-scrolling: touch !important;
                scrollbar-width: thin !important;
                padding-bottom: 4px !important;
            }
            div[data-baseweb="tab"] { flex-shrink: 0 !important; padding: 8px 12px !important; font-size: 0.85rem !important; }
            section[data-testid="stSidebar"] { min-width: 250px !important; max-width: 85vw !important; }
            .sintesi-testo { font-size: 0.82rem !important; height: auto !important; }
            div[data-testid="stModal"] > div { width: 95vw !important; max-width: 95vw !important; padding: 10px !important; }
        }
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

def carica_preferenze(conto_selezionato):
    path = os.path.join(conto_selezionato, "preferenze_ui.json")
    if os.path.exists(path):
        try:
            with open(path, "r") as f: return json.load(f)
        except: return {}
    return {}

def salva_preferenze(conto_selezionato, prefs):
    path = os.path.join(conto_selezionato, "preferenze_ui.json")
    try:
        with open(path, "w") as f: json.dump(prefs, f, indent=4)
    except: pass

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

    if "conto_selezionato" not in st.session_state or st.session_state.conto_selezionato not in conti_disponibili:
        st.session_state.conto_selezionato = conti_disponibili[0]
        
    conto_selezionato = st.session_state.conto_selezionato
    is_reale = "_REALE" in conto_selezionato.upper()

    with st.sidebar:
        st.markdown(f"### 👤 Utente: {st.session_state.user}")
        
        conti_reali = [c for c in conti_disponibili if "_REALE" in c.upper()]
        conti_demo = [c for c in conti_disponibili if "_REALE" not in c.upper()]
        
        if conti_reali:
            st.markdown("<p style='font-size: 0.78rem; font-weight: 700; color: #ff4b4b; margin: 10px 0 4px 0; letter-spacing: 0.8px;'>🔴 CONTI REALI</p>", unsafe_allow_html=True)
            for cr in conti_reali:
                nome_cr_clean = cr.replace("_REALE", "")
                st_cr = leggi_stato_sistema(cr)
                cap_cr = formatta_eur(st_cr.get('saldo', '0'))
                is_sel = (cr == conto_selezionato)
                label_cr = f"🔴 {nome_cr_clean}: :orange[{cap_cr} €]"
                if st.button(label_cr, key=f"side_acc_{cr}", type="primary" if is_sel else "secondary", use_container_width=True):
                    if not is_sel:
                        st.session_state.conto_selezionato = cr
                        st.rerun()
            st.markdown("<div style='margin: 8px 0;'></div>", unsafe_allow_html=True)
            
        if conti_demo:
            st.markdown("<p style='font-size: 0.78rem; font-weight: 700; color: #1E88E5; margin: 10px 0 4px 0; letter-spacing: 0.8px;'>🔵 CONTI DEMO</p>", unsafe_allow_html=True)
            for cd in conti_demo:
                nome_cd_clean = cd.replace("_DEMO", "")
                st_cd = leggi_stato_sistema(cd)
                cap_cd = formatta_eur(st_cd.get('saldo', '0'))
                is_sel = (cd == conto_selezionato)
                label_cd = f"🔵 {nome_cd_clean}: :orange[{cap_cd} €]"
                if st.button(label_cd, key=f"side_acc_{cd}", type="primary" if is_sel else "secondary", use_container_width=True):
                    if not is_sel:
                        st.session_state.conto_selezionato = cd
                        st.rerun()
                        
        st.markdown("<div style='margin-bottom: 12px;'></div>", unsafe_allow_html=True)
        if st.button("🚪 Logout", key="btn_logout_side", use_container_width=True):
            st.session_state.logged_in = False
            st.rerun()
            
        # --- AGGIUNTA MARGINE E DRAWDOWN IN SIDEBAR (LIVE) ---
        @st.fragment(run_every=15)
        def renderizza_sidebar_stats():
            stato_side = leggi_stato_sistema(conto_selezionato)
            prefs_side = carica_preferenze(conto_selezionato)
            
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
            
            # --- INVESTIMENTO INIZIALE ---
            inv_iniziale_saved = float(prefs_side.get("investimento_iniziale", 0.0))
            def salva_inv_side():
                key_k = f"side_inv_input_sim_{conto_selezionato}"
                if key_k in st.session_state:
                    p = carica_preferenze(conto_selezionato)
                    p["investimento_iniziale"] = float(st.session_state[key_k])
                    salva_preferenze(conto_selezionato, p)

            st.number_input(
                "💰 Investimento Iniziale (€)",
                min_value=0.0,
                value=inv_iniziale_saved,
                step=500.0,
                format="%.2f",
                key=f"side_inv_input_sim_{conto_selezionato}",
                on_change=salva_inv_side
            )

            # Calcolo Delta assoluto e percentuale rispetto a Capitale Totale
            delta_html = ""
            inv_attuale = float(st.session_state.get(f"side_inv_input_sim_{conto_selezionato}", inv_iniziale_saved))
            if inv_attuale > 0:
                try:
                    saldo_float = float(stato_side.get('saldo', 0.0))
                    diff_val = saldo_float - inv_attuale
                    diff_pct = (diff_val / inv_attuale) * 100.0
                    col_diff = "#4ade80" if diff_val > 0 else ("#ef4444" if diff_val < 0 else "#aaa")
                    sign_diff = "+" if diff_val > 0 else ""
                    sign_pct = "+" if diff_pct > 0 else ""
                    diff_eur_str = formatta_eur(diff_val)
                    delta_html = f"<div style='font-size: 0.85rem; font-weight: bold; color: {col_diff}; margin-top: 2px;'>({sign_diff}{diff_eur_str} {sign_pct}{diff_pct:.2f}%)</div>"
                except Exception:
                    pass

            st.markdown(f"<div style='font-size: 0.85rem; color: #aaa; margin-top: 6px;'>Capitale Totale</div><div style='font-size: 1.05rem; font-weight: bold; color: #FFD700;'>{val_capitale} €</div>{delta_html}", unsafe_allow_html=True)
            st.markdown(f"<div style='font-size: 0.85rem; color: #aaa; margin-top: 10px;'>Margine Utilizzato</div><div style='font-size: 1.05rem; font-weight: bold; color: #ef4444;'>{val_margine} €</div>", unsafe_allow_html=True)
            st.markdown(f"<div style='font-size: 0.85rem; color: #aaa; margin-top: 10px;'>Margine Residuo</div><div style='font-size: 1.05rem; font-weight: bold; color: #4ade80;'>{val_residuo} €</div>", unsafe_allow_html=True)
            st.markdown(f"<div style='font-size: 0.85rem; color: #aaa; margin-top: 10px;'>Drawdown (P/L)</div><div style='font-size: 1.05rem; font-weight: bold; color: {col_dd};'>{val_dd} €</div>", unsafe_allow_html=True)
        
        renderizza_sidebar_stats()

    # TABS RIORDINATI (Portafoglio IG per primo)
    tab_simulatore, tab_ottimizzazione = st.tabs(["🔬 Simulatore", "🧪 Backtest"])

    with tab_simulatore:
        st.markdown("<h2 style='text-align: center; color: #00FFCC;'>🔬 Simulatore Avanzato (Moviola Hedge Sincrono)</h2>", unsafe_allow_html=True)
        st.markdown("Simula l'esecuzione del **Motore.py originale** senza alterarne il codice, tramite una staffetta sequenziale che riproduce fedelmente una partenza multiconto parallela.", unsafe_allow_html=True)
        
        st.markdown("---")
        
        sm1, sm2 = st.columns(2)
        # --- Ristrutturazione Simulatore ---
        
        # 1. Generatore Base Dati
        st.markdown("<h3 style='color: #FFD700;'>1. Generatore Base Dati</h3>", unsafe_allow_html=True)
        
        g1, g2, g3 = st.columns(3)
        with g1:
            gen_strum = st.selectbox("Strumento", list(CONFIG_STRUMENTI.keys()), key="gen_strum")
        with g2:
            gen_scen = st.selectbox("Scenario Mercato", ["LATERALE", "TREND_UP", "TREND_DOWN", "CRASH", "RANDOM"], key="gen_scen")
        with g3:
            _gen_ticks = st.text_input("Durata", value="250", key="gen_ticks")
            gen_ticks = int(_gen_ticks) if _gen_ticks.isdigit() else 250
            
        g4, g6 = st.columns(2)
        with g4:
            _gen_base_price = st.text_input("Prezzo di Partenza", value="2400.0", key="gen_base_price")
            try: gen_base_price = float(_gen_base_price.replace(',', '.'))
            except: gen_base_price = 2400.0
        with g6:
            _gen_size = st.text_input("Size", value="10", key="gen_size")
            gen_size = int(_gen_size) if _gen_size.isdigit() else 10
            
        import Simulatore_Avanzato
        import importlib
        importlib.reload(Simulatore_Avanzato)
        import os
        
        if st.button("🛠️ Crea Base Dati", use_container_width=True):
            with st.spinner(f"Generazione file dati per {gen_strum} in corso..."):
                molt = CONFIG_STRUMENTI.get(gen_strum, {}).get("moltiplicatore", 1.0)
                dec = CONFIG_STRUMENTI.get(gen_strum, {}).get("decimali", 5)
                
                if molt == 1.0:
                    real_tick = 1.0
                else:
                    real_tick = 2.5 * molt
                    
                f_path = Simulatore_Avanzato.genera_base_dati(gen_strum, gen_scen, gen_base_price, real_tick, gen_ticks, gen_size, decimali=dec)
                st.success(f"Base dati generata e salvata: `{os.path.basename(f_path)}`")
                
        st.markdown("---")
        
        # 2. Esecutore Simulazione
        st.markdown("<h3 style='color: #00FFCC;'>2. Esecutore Simulazione</h3>", unsafe_allow_html=True)
        
        e1, e2, e3 = st.columns(3)
        with e1:
            eseg_strum = st.selectbox("Seleziona Strumento", list(CONFIG_STRUMENTI.keys()), key="eseg_strum")
        with e2:
            eseg_dir = st.selectbox("Direzione", ["LONG", "SHORT"], index=0, key="eseg_dir")
        with e3:
            strum_pulito = Simulatore_Avanzato.pulisci_nome_strumento(eseg_strum)
            dir_path = os.path.join(os.getcwd(), "Simulatore", strum_pulito)
            file_list = []
            if os.path.exists(dir_path):
                file_list = [f for f in os.listdir(dir_path) if f.endswith(".csv")]
                # Metti in cima i file di Backtest
                file_list.sort(key=lambda x: (not x.startswith("Backtest"), x))
            
            eseg_file = st.selectbox("Seleziona Base Dati", file_list if file_list else ["Nessun file trovato"], key="eseg_file")
            
        # Rilevamento automatico parametri dal nome file o CSV
        import re
        def_sim_tp = 80
        def_sim_opp = 20
        def_sim_dts = 10
        def_sim_size = 10
        
        if eseg_file and eseg_file != "Nessun file trovato":
            m_params = re.search(r"TP(\d+(?:\.\d+)?)\.OPP(\d+(?:\.\d+)?)\.DTS(\d+(?:\.\d+)?)", eseg_file)
            if m_params:
                def_sim_tp = int(float(m_params.group(1))) if float(m_params.group(1)).is_integer() else float(m_params.group(1))
                def_sim_opp = int(float(m_params.group(2))) if float(m_params.group(2)).is_integer() else float(m_params.group(2))
                def_sim_dts = int(float(m_params.group(3))) if float(m_params.group(3)).is_integer() else float(m_params.group(3))
            
            try:
                f_check_size = os.path.join(dir_path, eseg_file)
                if os.path.exists(f_check_size):
                    df_chk = pd.read_csv(f_check_size, nrows=1)
                    if "Size" in df_chk.columns:
                        def_sim_size = int(df_chk["Size"].iloc[0])
            except:
                pass
                
        st.markdown("**Parametri Griglia (Applicati a runtime)**")
        e4, e5, e6, e7 = st.columns(4)
        with e4:
            sim_tp = st.number_input("Take Profit (TP)", value=def_sim_tp, step=5, key=f"eseg_tp_{eseg_strum}_{eseg_file}")
        with e5:
            sim_opp = st.number_input("Opposto (OPP)", value=def_sim_opp, step=5, key=f"eseg_opp_{eseg_strum}_{eseg_file}")
        with e6:
            sim_dts = st.number_input("Distanza Sicurezza (DTS)", value=def_sim_dts, step=5, key=f"eseg_dts_{eseg_strum}_{eseg_file}")
        with e7:
            sim_size = st.number_input("Size Contratti", min_value=4, value=def_sim_size, step=1, key=f"eseg_size_{eseg_strum}_{eseg_file}")
            
        btn_disabled = (eseg_file == "Nessun file trovato")
        
        st.markdown("---")
        import pandas as pd
        if not btn_disabled:
            try:
                f_path_full = os.path.join(dir_path, eseg_file)
                df_temp = pd.read_csv(f_path_full)
                p_start = float(df_temp['Price'].iloc[0])
            except:
                p_start = 0.0
        else:
            p_start = 0.0
            
        molt = CONFIG_STRUMENTI.get(eseg_strum, {}).get("moltiplicatore", 1.0)
        dec = CONFIG_STRUMENTI.get(eseg_strum, {}).get("decimali", 5)
        v_punto = CONFIG_STRUMENTI.get(eseg_strum, {}).get("valore_punto", 1.0)
        v_valuta = CONFIG_STRUMENTI.get(eseg_strum, {}).get("valuta", "EUR")
        
        real_tp = sim_tp * molt
        
        if eseg_dir == "LONG":
            p_target = p_start + real_tp
        else:
            p_target = p_start - real_tp
            
        st.info(f"**Verifica Parametri:** {sim_tp} punti per **{eseg_strum}** partendo da **{p_start:.{dec}f}** -> Target a **{p_target:.{dec}f}** (Variazione di {real_tp:.{dec}f})")
        
        if st.button("▶️ Avvia Simulazione", use_container_width=True, disabled=btn_disabled):
            with st.spinner(f"Elaborazione strategia su {eseg_file} in corso..."):
                try:
                    f_path_full = os.path.join(dir_path, eseg_file)
                    
                    # Esecuzione del Motore simulato (Forzato a Singolo)
                    ris = Simulatore_Avanzato.esegui_hedge_sincrono(
                        f_path_full, eseg_strum,
                        sim_tp, sim_opp, sim_dts, sim_size,
                        "Singolo", eseg_dir,
                        mult=1.0,
                        valore_punto=v_punto,
                        valuta=v_valuta,
                        molt_strum=molt
                    )
                    
                    if not ris:
                        st.error("Errore durante la simulazione. Controlla il terminale.")
                        st.stop()
                        
                    st.success("Simulazione completata con successo!")
                    
                    st.markdown(f"### 📖 Diario di Bordo della Simulazione (WS) - {eseg_strum}")
                    
                    def renderizza_storico(conto_key):
                        storico = ris["risultati"].get(conto_key, {}).get("log_ws", [])
                        if storico:
                            html_str = "<div style='font-size: 0.85rem; line-height: 1.6; margin-bottom: 20px;'>"
                            for riga in storico:
                                import re
                                riga_colorata = re.sub(r"(\[EVENTO\]:.*)", r"<span style='color: #00FFFF;'>\1</span>", riga)
                                
                                def colora_parziale(match):
                                    val = float(match.group(1))
                                    colore = "#00FF00" if val >= 0 else "#FF4500"
                                    return f"<span style='color: {colore};'>[Parziale: {val:+.0f} €]</span>"
                                    
                                riga_colorata = re.sub(r"\[Parziale:\s*([+-]?\d+(?:\.\d+)?)\s*€\]", colora_parziale, riga_colorata)
                                riga_colorata = re.sub(r"(\[Totale:.*?\])", r"<span style='color: #FFD700;'><b>\1</b></span>", riga_colorata)
                                html_str += f"&bull; {riga_colorata}<br>"
                                
                            html_str += "</div>"
                            st.markdown(html_str, unsafe_allow_html=True)
                            return True
                        return False
                        
                    trovato_f = renderizza_storico("SIM_FIORDOK")
                        
                    if not trovato_f:
                        st.warning("Nessun evento registrato durante questa simulazione.")
                    
                except Exception as e:
                    st.error(f"Errore durante la simulazione: {e}")
                    import traceback
                    st.code(traceback.format_exc())


    # --- TAB OTTIMIZZAZIONE GLOBALE ---
    with tab_ottimizzazione:
        st.title("🧪 Backtest (Simulazione Monte Carlo)")
        st.markdown("Cerca i parametri migliori simulando migliaia di scenari (Laterali e Randomici).")
        
        import glob
        cartella_salvataggi = os.path.join("Simulatore", "ottimizzazioni_salvate")
        if not os.path.exists(cartella_salvataggi):
            os.makedirs(cartella_salvataggi)
            
        def renderizza_risultati_ottimizzazione(df_full, modo_dati, nome_strumento=""):
            # Raggruppamento Globale e Medie
            groupby_cols = ["TP", "OPP", "DTS"]
            numeric_cols = df_full.select_dtypes(include=[np.number]).columns.tolist()
            for col in groupby_cols:
                if col not in numeric_cols and col in df_full.columns:
                    numeric_cols.append(col)
                    
            df_global = df_full[numeric_cols].groupby(groupby_cols).mean().reset_index()
            
            if "Median_CSV" in df_full.columns:
                median_map = df_full.groupby(groupby_cols)["Median_CSV"].first().reset_index()
                df_global = df_global.merge(median_map, on=groupby_cols, how="left")
                
            n_files = 10 if modo_dati == "Generazione Batch (LATERALE + RANDOM)" else 1
            if "N_Simulazioni" not in df_full.columns:
                df_global["N_Simulazioni"] = df_full.groupby(groupby_cols).size().reset_index(drop=True) * n_files
            else:
                df_global["N_Simulazioni"] = df_full.groupby(groupby_cols).size().reset_index(drop=True) * n_files
            
            # Calcolo Score RoMD e Win
            df_global["Score RoMD"] = df_global["PNL Totale"] / df_global["Max Drawdown"].replace(0, 1)
            df_global["Score Win"] = df_global["PNL Totale"] * (df_global["Win Rate %"] / 100.0)
            
            # Rinomino colonne per compattezza visiva
            df_global = df_global.rename(columns={"Max Drawdown": "Max DD", "N_Simulazioni": "N. Test", "Score RoMD": "RoMD"})
            
            # Ordinamento per RoMD
            df_global = df_global.sort_values(by="RoMD", ascending=False).reset_index(drop=True)
            
            # Formattazione per visualizzazione
            col_display = ["TP", "OPP", "DTS", "PNL Long", "PNL Short", "PNL Totale", "Max DD", "Win Rate %", "RoMD", "Score Win", "N. Test"]
            df_display = df_global[col_display].copy()
            
            # Stile per colorare la colonna Max DD di rosso salmone
            def colora_max_dd(val):
                return 'color: #FA8072; font-weight: bold;'
            
            if nome_strumento:
                st.markdown(f"### 🏆 Classifica Globale {nome_strumento} - Parametri Migliori (Ordinata per RoMD)")
            else:
                st.markdown("### 🏆 Classifica Globale Parametri Migliori (Ordinata per RoMD)")
            
            # Applico stili: gradiente, colore Max DD
            styled_df = df_display.style.background_gradient(subset=["RoMD", "PNL Totale"], cmap="RdYlGn")\
                .map(colora_max_dd, subset=["Max DD"])\
                .format({
                "PNL Long": "{:.0f} €", "PNL Short": "{:.0f} €", "PNL Totale": "{:.0f} €", 
                "Max DD": "-{:.0f} €", "RoMD": "{:.2f}", "Score Win": "{:.2f}"
            })
            
            st.dataframe(styled_df, use_container_width=True)
            
            if "Median_CSV" in df_global.columns:
                st.markdown("### 💾 Top 5 Scenari Mediani (Pronti nel Simulatore)")
                
                nome_strum_clean = Simulatore_Avanzato.pulisci_nome_strumento(nome_strumento) if nome_strumento else "Generico"
                dest_dir = os.path.join(os.getcwd(), "Simulatore", nome_strum_clean)
                os.makedirs(dest_dir, exist_ok=True)
                
                top_5 = df_global.head(5)
                cols = st.columns(min(5, len(top_5)))
                numeri_romani = ["I", "II", "III", "IV", "V"]
                
                salvati_in_cartella = 0
                for i, row in top_5.iterrows():
                    csv_path = row.get("Median_CSV", "")
                    suffisso = numeri_romani[i] if i < 5 else str(i+1)
                    tp_val = int(row['TP']) if float(row['TP']).is_integer() else row['TP']
                    opp_val = int(row['OPP']) if float(row['OPP']).is_integer() else row['OPP']
                    dts_val = int(row['DTS']) if float(row['DTS']).is_integer() else row['DTS']
                    
                    file_name = f"Backtest.{nome_strum_clean}.{suffisso}.TP{tp_val}.OPP{opp_val}.DTS{dts_val}.csv"
                    
                    if pd.notna(csv_path) and os.path.exists(str(csv_path)):
                        import shutil
                        dest_file_path = os.path.join(dest_dir, file_name)
                        shutil.copy2(str(csv_path), dest_file_path)
                        salvati_in_cartella += 1
                        
                        with open(csv_path, "rb") as f:
                            csv_data = f.read()
                        
                        with cols[i]:
                            st.download_button(
                                label=f"↓ {suffisso} (TP:{tp_val} DTS:{dts_val})",
                                data=csv_data,
                                file_name=file_name,
                                mime="text/csv",
                                use_container_width=True
                            )
                
                if salvati_in_cartella > 0:
                    st.info(f"✅ I Top {salvati_in_cartella} scenari sono stati **salvati automaticamente** nella cartella `Simulatore/{nome_strum_clean}/`. Li trovi già pronti nel menu a tendina del **Simulatore** con tutti i parametri preimpostati!")
                    # Pulizia automatica dei file intermedi temporanei
                    mediani_dir = os.path.join(os.getcwd(), "Simulatore", "salvataggi", "csv_mediani")
                    if os.path.exists(mediani_dir):
                        try:
                            import shutil
                            shutil.rmtree(mediani_dir, ignore_errors=True)
                        except Exception:
                            pass
                            
            st.markdown("### 🗺️ Mappa di Calore Globale (Robustezza RoMD)")
            try:
                import plotly.express as px
                pivot_df = df_global.pivot_table(values="RoMD", index="DTS", columns="TP", aggfunc="mean")
                fig = px.imshow(pivot_df, text_auto=".2f", color_continuous_scale="RdYlGn", aspect="auto", origin='lower')
                fig.update_layout(title="RoMD Globale per Combinazione (TP vs DTS)", xaxis_title="Take Profit (TP)", yaxis_title="Distanza Sicurezza (DTS)")
                st.plotly_chart(fig, use_container_width=True)
            except Exception as e:
                st.warning(f"Impossibile renderizzare la Heatmap: {e}")

        # --- CARICAMENTO SALVATAGGI ---
        st.markdown("### 📂 Carica Tabella Ottimizzazioni Salvate")
        file_salvati = [f for f in os.listdir(cartella_salvataggi) if f.endswith(".csv")]
        if file_salvati:
            col_sel, col_btn = st.columns([3, 1])
            with col_sel:
                file_selezionato = st.selectbox("Seleziona un file salvato", ["-- Nessuno --"] + file_salvati, key="sel_file_ott_salvato")
            with col_btn:
                st.write("") # padding
                st.write("")
                btn_carica = st.button("Mostra Classifica", use_container_width=True)
                
            if btn_carica and file_selezionato != "-- Nessuno --":
                st.markdown("---")
                try:
                    percorso_load = os.path.join(cartella_salvataggi, file_selezionato)
                    df_loaded = pd.read_csv(percorso_load)
                    st.success(f"Risultati caricati da {file_selezionato}")
                    
                    import re
                    match = re.search(r"Ott\.(.+?)_\d+test", file_selezionato)
                    strum_name = match.group(1).replace("_", " ") if match else file_selezionato.replace(".csv", "")
                    
                    renderizza_risultati_ottimizzazione(df_loaded, "Generazione Batch (LATERALE + RANDOM)", strum_name)
                except Exception as e:
                    st.error(f"Errore caricamento: {e}")
                st.markdown("---")
        else:
            st.info("Nessun salvataggio presente.")
            
        st.markdown("---")
        
        st.markdown("### 1. Seleziona Strumento da Ottimizzare")
        
        tutti_strumenti = list(CONFIG_STRUMENTI.keys())
        stato = leggi_stato_sistema(conto_selezionato)
        prezzi_live = stato.get("prezzi_live", {})
        
        r_nome_ott = st.selectbox("Seleziona lo Strumento per agganciare le quotazioni Live e i moltiplicatori reali:", tutti_strumenti, key="ott_r_nome")
        
        # Recupero config base per lo strumento selezionato
        c_ott = CONFIG_STRUMENTI.get(r_nome_ott, {})
        def_tick = c_ott.get("tick_size", c_ott.get("moltiplicatore", 1.0))
        def_mult = c_ott.get("moltiplicatore_dts", 1.0)
        
        # Gestione prezzo live se disponibile, altrimenti default
        prezzo_live_ott = prezzi_live.get(r_nome_ott, 0.0)
        if prezzo_live_ott > 0:
            def_part = float(prezzo_live_ott)
            lbl_partenza = f"Prezzo START (Live) su {r_nome_ott}"
        else:
            def_part = 2400.0 if "Gold" in r_nome_ott or "Cash" in r_nome_ott else (1.1000 if "USD" in r_nome_ott else 160.0)
            lbl_partenza = f"Prezzo START (Default) su {r_nome_ott}"
            
        # Default per le griglie
        if "USD" in r_nome_ott and "Gold" not in r_nome_ott and "Cash" not in r_nome_ott:
            # Forex Major
            def_tp_min, def_tp_max, def_tp_step = 20.0, 60.0, 20.0
            def_dts_min, def_dts_max, def_dts_step = 30.0, 80.0, 10.0
            def_tic_tot = 10000
        elif "JPY" in r_nome_ott:
            # Forex JPY
            def_tp_min, def_tp_max, def_tp_step = 20.0, 60.0, 20.0
            def_dts_min, def_dts_max, def_dts_step = 30.0, 80.0, 10.0
            def_tic_tot = 10000
        else:
            # Oro / Indici
            def_tp_min, def_tp_max, def_tp_step = 40.0, 100.0, 20.0
            def_dts_min, def_dts_max, def_dts_step = 30.0, 80.0, 10.0
            def_tic_tot = 5000
            
        def_size = 10.0
        def_val_punto = 1.0
        def_target_sim = 50
        
        # Caricamento memorie parametri
        file_memoria_ott = os.path.join(cartella_salvataggi, "memoria_parametri_ott.json")
        import json
        if os.path.exists(file_memoria_ott):
            try:
                with open(file_memoria_ott, "r") as f:
                    memoria_ott = json.load(f)
                memoria_strumento = memoria_ott.get(r_nome_ott, {})
                if memoria_strumento:
                    def_tp_min = memoria_strumento.get("tp_min", def_tp_min)
                    def_tp_max = memoria_strumento.get("tp_max", def_tp_max)
                    def_tp_step = memoria_strumento.get("tp_step", def_tp_step)
                    def_dts_min = memoria_strumento.get("dts_min", def_dts_min)
                    def_dts_max = memoria_strumento.get("dts_max", def_dts_max)
                    def_dts_step = memoria_strumento.get("dts_step", def_dts_step)
                    def_size = memoria_strumento.get("size", def_size)
                    def_val_punto = memoria_strumento.get("val_punto", def_val_punto)
                    def_target_sim = memoria_strumento.get("target_sim", def_target_sim)
                    def_tic_tot = memoria_strumento.get("tic_tot", def_tic_tot)
            except Exception as e:
                pass
            
        fmt = "%.4f" if def_tick < 0.01 else "%.2f"
        
        safe_nome = r_nome_ott.replace(" ", "_").replace("/", "")
        ott_modo_dati = st.radio("Modalità Dati", ["Generazione Batch (LATERALE + RANDOM)", "File Singolo Esistente"], key=f"ott_modo_{safe_nome}")
        
        import pandas as pd
        file_paths_ott = []
        ott_partenza = def_part
        ott_tick_size = def_tick
        ott_tic_tot = def_tic_tot
        
        st.markdown("### 2. Dati di Partenza")
        if ott_modo_dati == "File Singolo Esistente":
            file_upload_ott = st.file_uploader("Carica Storico CSV", type=['csv'], key=f"ott_up_{safe_nome}")
            if file_upload_ott is not None:
                tmp_path = "temp_ottimizzazione.csv"
                with open(tmp_path, "wb") as f: f.write(file_upload_ott.getbuffer())
                file_paths_ott.append(tmp_path)
        else:
            c_g1, c_g2 = st.columns(2)
            with c_g1: ott_partenza = st.number_input(lbl_partenza, value=def_part, step=def_tick*10, format=fmt, key=f"ott_part_{safe_nome}")
            with c_g2: ott_tic_tot = st.number_input("Numero di Tick per file", value=def_tic_tot, step=1000, key=f"ott_tic_tot_{safe_nome}")
            
        st.markdown("### 3. Configura la Griglia dei Parametri")
        c1, c2, c3 = st.columns(3)
        with c1:
            st.markdown("#### TP (Take Profit)")
            tp_min = st.number_input("TP Minimo", value=def_tp_min, step=def_tp_step, format=fmt, key=f"ott_tp_min_{safe_nome}")
            tp_max = st.number_input("TP Massimo", value=def_tp_max, step=def_tp_step, format=fmt, key=f"ott_tp_max_{safe_nome}")
            tp_step = st.number_input("TP Step", value=def_tp_step, step=def_tp_step, format=fmt, key=f"ott_tp_step_{safe_nome}")
        with c2:
            st.markdown("#### DTS (Distanza Sicurezza)")
            dts_min = st.number_input("DTS Minimo", value=def_dts_min, step=def_dts_step, format=fmt, key=f"ott_dts_min_{safe_nome}")
            dts_max = st.number_input("DTS Massimo", value=def_dts_max, step=def_dts_step, format=fmt, key=f"ott_dts_max_{safe_nome}")
            dts_step = st.number_input("DTS Step", value=def_dts_step, step=def_dts_step, format=fmt, key=f"ott_dts_step_{safe_nome}")
        with c3:
            st.markdown("#### Variabili Fisse")
            ott_size = st.number_input("Size Iniziale", value=def_size, step=1.0, key=f"ott_size_{safe_nome}")
            ott_val_punto = CONFIG_STRUMENTI.get(r_nome_ott, {}).get("valore_punto", 1.0)
            
        st.markdown("#### Automazione")
        def_target_sim = min(def_target_sim, 1000) # Assicuriamoci che non superi il nuovo massimo
        ott_target_sim = st.number_input("Target Simulazioni (File totali)", min_value=10, max_value=1000, value=def_target_sim, step=10, key=f"ott_target_sim_{safe_nome}")
        
        if st.button(f"🚀 Avvia Backtest per {r_nome_ott}", type="primary", use_container_width=True):
            # Salvataggio parametri in memoria
            try:
                memoria_ott = {}
                if os.path.exists(file_memoria_ott):
                    with open(file_memoria_ott, "r") as f:
                        memoria_ott = json.load(f)
                memoria_ott[r_nome_ott] = {
                    "tp_min": float(tp_min), "tp_max": float(tp_max), "tp_step": float(tp_step),
                    "dts_min": float(dts_min), "dts_max": float(dts_max), "dts_step": float(dts_step),
                    "size": float(ott_size), "val_punto": float(ott_val_punto), "target_sim": int(ott_target_sim),
                    "tic_tot": int(ott_tic_tot)
                }
                with open(file_memoria_ott, "w") as f:
                    json.dump(memoria_ott, f, indent=4)
            except Exception as e:
                pass
                
            import numpy as np
            import shutil
            tp_list = np.arange(tp_min, tp_max + tp_step, tp_step).tolist()
            dts_list = np.arange(dts_min, dts_max + dts_step, dts_step).tolist()
            tp_range = {"min": tp_min, "max": tp_max, "step": tp_step}
            dts_range = {"min": dts_min, "max": dts_max, "step": dts_step}
            storico_file = "ottimizzazione_storico_globale.csv"
            
            # Resetto sempre lo storico prima di un nuovo calcolo
            if os.path.exists(storico_file):
                os.remove(storico_file)
            
            if ott_modo_dati == "Generazione Batch (LATERALE + RANDOM)":
                iterazioni = max(1, int(ott_target_sim / 10))
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                import time
                for it in range(iterazioni):
                    status_text.markdown(f"**Elaborazione in corso... Batch {it+1}/{iterazioni} ({(it+1)*10} file totali)**")
                    
                    file_paths_ott = []
                    molt_ott = CONFIG_STRUMENTI.get(r_nome_ott, {}).get("moltiplicatore", 1.0)
                    dec_ott = CONFIG_STRUMENTI.get(r_nome_ott, {}).get("decimali", 5)
                    v_valuta_ott = CONFIG_STRUMENTI.get(r_nome_ott, {}).get("valuta", "EUR")
                    if molt_ott == 1.0:
                        real_tick_ott = 1.0
                    else:
                        real_tick_ott = 5.0 * molt_ott
                    
                    for i in range(5):
                        p = Simulatore_Avanzato.genera_base_dati(f"BATCH_OTT_{int(time.time()*1000)}_{i}", "LATERALE", ott_partenza, real_tick_ott, ott_tic_tot, ott_size, decimali=dec_ott)
                        file_paths_ott.append(p)
                    for i in range(5):
                        p = Simulatore_Avanzato.genera_base_dati(f"BATCH_OTT_{int(time.time()*1000)}_{i}", "RANDOM", ott_partenza, real_tick_ott, ott_tic_tot, ott_size, decimali=dec_ott)
                        file_paths_ott.append(p)
                        
                    df_res = Simulatore_Avanzato.esegui_ottimizzazione_griglia(file_paths_ott, tp_range, dts_range, size=ott_size, mult=def_mult, valore_punto=ott_val_punto, valuta=v_valuta_ott, molt_strum=molt_ott, save_median=(it==0))
                    
                    if not df_res.empty:
                        if os.path.exists(storico_file):
                            df_storico = pd.read_csv(storico_file)
                            df_full = pd.concat([df_storico, df_res], ignore_index=True)
                        else:
                            df_full = df_res.copy()
                        df_full.to_csv(storico_file, index=False)
                        
                    for p in file_paths_ott:
                        if os.path.exists(p):
                            os.remove(p)
                            try:
                                parent_dir = os.path.dirname(p)
                                if os.path.exists(parent_dir) and not os.listdir(parent_dir):
                                    os.rmdir(parent_dir)
                            except:
                                pass
                    progress_bar.progress((it + 1) / iterazioni)
                
                tot_sim_effettive = iterazioni * 10
                status_text.success(f"✅ Backtest completato! ({tot_sim_effettive} file elaborati)")
                
            else:
                tot_sim_effettive = 1
                if not file_paths_ott:
                    st.error("Nessun dataset selezionato.")
                else:
                    with st.spinner("Backtest file singolo in corso..."):
                        molt_ott = CONFIG_STRUMENTI.get(r_nome_ott, {}).get("moltiplicatore", 1.0)
                        v_valuta_ott = CONFIG_STRUMENTI.get(r_nome_ott, {}).get("valuta", "EUR")
                        df_res = Simulatore_Avanzato.esegui_ottimizzazione_griglia(file_paths_ott, tp_range, dts_range, size=ott_size, mult=def_mult, valore_punto=ott_val_punto, valuta=v_valuta_ott, molt_strum=molt_ott, save_median=True)
                        if not df_res.empty:
                            if os.path.exists(storico_file):
                                df_storico = pd.read_csv(storico_file)
                                df_full = pd.concat([df_storico, df_res], ignore_index=True)
                            else:
                                df_full = df_res.copy()
                            df_full.to_csv(storico_file, index=False)
                            st.success("✅ Backtest file singolo completato!")
                            
            if os.path.exists(storico_file):
                df_full = pd.read_csv(storico_file)
                
                # Logica di salvataggio automatico e pulizia
                nome_pulito = r_nome_ott.replace(" ", "_").replace("/", "")
                base_file_name = f"Ott.{nome_pulito}_{tot_sim_effettive}test"
                file_finale = f"{base_file_name}.csv"
                path_finale = os.path.join(cartella_salvataggi, file_finale)
                
                # Gestione versionamento per non sovrascrivere file esistenti (v02, v03...)
                counter = 2
                while os.path.exists(path_finale):
                    file_finale = f"{base_file_name}_v{counter:02d}.csv"
                    path_finale = os.path.join(cartella_salvataggi, file_finale)
                    counter += 1
                
                shutil.copy(storico_file, path_finale)
                os.remove(storico_file)
                
                st.success(f"💾 Risultati salvati automaticamente in: `{file_finale}`")
                
                # Mostra subito i risultati
                renderizza_risultati_ottimizzazione(df_full, ott_modo_dati, r_nome_ott)
            else:
                st.warning("Nessun risultato ottenuto (griglia vuota o nessun test eseguito).")
