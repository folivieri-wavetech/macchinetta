import sys
sys.path.append("/data/libs")
import streamlit as st
import json
import os
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
import time
import pandas as pd
import requests
import re
from datetime import datetime, timedelta, timezone
try:
    from zoneinfo import ZoneInfo
    TZ_ITALIA = ZoneInfo("Europe/Rome")
except Exception:
    TZ_ITALIA = timezone(timedelta(hours=2))

def now_it():
    return datetime.now(TZ_ITALIA)

from dotenv import dotenv_values
import plotly.graph_objects as go
import numpy as np

# --- CONFIGURAZIONI CENTRALI ---
FILE_MEMORIA = "memoria_parametri.json"
FILE_TOKEN = "token_ig.json"
FILE_STORICO = "storico_operazioni.csv"
CONSOLE_LOG_FILE = "console_live.log"
STATO_SISTEMA = "stato_sistema.json"
import Sistema.auth_manager as auth_manager

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

config = dotenv_values(".env")
DEV_MODE = config.get("DEV_MODE", "False").lower() == "true"

st.set_page_config(page_title="Macchinetta IG", layout="wide", initial_sidebar_state="expanded")
if DEV_MODE:
    st.error("⚠️ **MODALITÀ SVILUPPO (DEV_MODE) ATTIVA** - I motori stanno scrivendo messaggi fittizi. Le connessioni API a IG sono sospese.")

# --- FUNZIONI HELPER MULTI-CONTO ---
def get_accounts():
    """Scansiona la root e trova tutte le cartelle conto valide."""
    tutti = [d for d in os.listdir() if os.path.isdir(d) and (d.endswith("_DEMO") or d.endswith("_REALE"))]
    if hasattr(st, "session_state") and getattr(st.session_state, "logged_in", False):
        if not st.session_state.get("tutti_i_conti", False):
            autorizzati = st.session_state.get("conti_autorizzati", [])
            tutti = [c for c in tutti if c in autorizzati]
    return tutti

def formatta_numero(valore, dec):
    if valore is None:
        return None
    r = round(float(valore), dec)
    return f"{r:.{dec}f}"

def formatta_ultimo_evento_sintesi(msg, dati=None, nome=None):
    if not msg or not isinstance(msg, str):
        return "Nessun evento registrato in questo ciclo."
    
    # 1) Ping-Pong / TICKET1 target
    # Es: [25/08 02:37:01] ✅ [EVENTO]: TICKET1 a target a 1.19993! Ping-Pong: Rigirato in SHORT. [Parziale: +31 €]
    # Diventa: [25/08 02:37:01] Profit TICKET1 a 1.19993. Ora [SHORT] a 1.19993
    m_pp = re.search(r'(?:\[(\d{2}/\d{2}\s+\d{2}:\d{2}:\d{2})\]\s*)?(?:✅\s*)?(?:\[EVENTO\]:\s*)?(?:\[?TICKET1?\]?)\s+a\s+target\s+a\s+([\d\.]+).*?Ping-Pong:\s*Rigirato\s*(?:in\s*)?([A-Za-z]+)(?:\s+a\s+([\d\.]+))?', msg, re.IGNORECASE)
    if m_pp:
        ts = m_pp.group(1)
        ts_prefix = f"[{ts}] " if ts else ""
        target_price = m_pp.group(2)
        raw_dir = m_pp.group(3).upper()
        dir_clean = "LONG" if raw_dir in ["BUY", "LONG"] else ("SHORT" if raw_dir in ["SELL", "SHORT"] else raw_dir)
        explicit_price = m_pp.group(4)
        if explicit_price:
            prezzo_nuovo = explicit_price
        elif dati and (dati.get("ticket1_entry") is not None or dati.get("ticket1_base") is not None):
            dec = CONFIG_STRUMENTI.get(nome, {}).get("decimali", 5) if nome else 5
            val = dati.get("ticket1_entry") if dati.get("ticket1_entry") is not None else dati.get("ticket1_base")
            prezzo_nuovo = formatta_numero(val, dec)
        else:
            prezzo_nuovo = target_price
        return f"{ts_prefix}Profit TICKET1 a {target_price}. Ora [{dir_clean}] a {prezzo_nuovo}"

    # 2) ASSICURAZIONE chiusa -> Entrata in Fase 2
    # Es: [25/08 00:02:20] ✅ [EVENTO]: ASSICURAZIONE chiusa [Parziale: +4 €]. ➡️ Entrata in Fase 2 - [TICKET1] LONG eseguito a 1.19717.
    # Diventa: [25/08 00:02:20] Fase 2 - [Ticket1] LONG a 1.19717
    m_ass = re.search(r'(?:\[(\d{2}/\d{2}\s+\d{2}:\d{2}:\d{2})\]\s*)?(?:✅\s*)?(?:\[EVENTO\]:\s*)?(?:\[?ASSICURAZIONE\]?)\s+chiusa.*?Entrata\s+in\s+Fase\s+2\s*-\s*\[?TICKET1?\]?\s*([A-Za-z]+)\s+eseguito\s+a\s+([\d\.]+)', msg, re.IGNORECASE)
    if m_ass:
        ts = m_ass.group(1)
        ts_prefix = f"[{ts}] " if ts else ""
        raw_dir = m_ass.group(2).upper()
        dir_clean = "LONG" if raw_dir in ["BUY", "LONG"] else ("SHORT" if raw_dir in ["SELL", "SHORT"] else raw_dir)
        entry_price = m_ass.group(3).rstrip('.')
        return f"{ts_prefix}Fase 2 - [Ticket1] {dir_clean} a {entry_price}"

    return msg

def formatta_mercato_con_bandiere(nome):
    if len(nome) == 7 and nome[3] == '/':
        nome_clean = nome.replace("/", "")
        return f"<div style='display: flex; flex-direction: column; align-items: center; line-height: 1.1; margin-left: 10px;'><u style='color: #FFD700; font-size: 1.15em; font-weight: bold;'>{nome_clean}</u></div>"
    
    return f"<u style='color: #FFD700; margin-left: 10px; font-weight: bold;'>{nome}</u>"

def formatta_titolo_con_bandiere_orizzontale(nome, badge):
    flags = {
        "AUD": "au",
        "CAD": "ca",
        "CHF": "ch",
        "EUR": "eu",
        "GBP": "gb",
        "JPY": "jp",
        "NZD": "nz",
        "USD": "us"
    }
    
    titolo = f"<span style='color: #FFD700;'>{nome}</span>"
    
    if len(nome) == 7 and nome[3] == '/':
        c1, c2 = nome[:3], nome[4:]
        if c1 in flags and c2 in flags:
            nome_spaziato = nome.replace("/", " / ")
            img1 = f"<img src='https://flagcdn.com/w80/{flags[c1]}.png' width='54' style='border-radius:3px; box-shadow: 0 0 4px rgba(0,0,0,0.5); margin-right: 5px;'>"
            img2 = f"<img src='https://flagcdn.com/w80/{flags[c2]}.png' width='54' style='border-radius:3px; box-shadow: 0 0 4px rgba(0,0,0,0.5);'>"
            titolo = f"<div style='margin-bottom: 5px; display: flex; align-items: center;'>{img1}{img2}</div><span style='color: #FFD700;'>{nome_spaziato}</span>"
        else:
            nome_spaziato = nome.replace("/", " / ")
            titolo = f"<span style='color: #FFD700;'>{nome_spaziato}</span>"
        
    return f"<div style='font-size: 1.4rem; font-weight: bold; white-space: nowrap; margin-bottom: -5px;'>{titolo} <span style='font-size: 0.85rem; padding-left: 4px; vertical-align: middle; color: #abb2bf;'>{badge}</span></div>"

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
def mostra_diario_wip(nome_strumento, storico, conto=None):
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
        
    if conto:
        mem = carica_memoria(conto)
        stats = mem.get(nome_strumento, {}).get("stats", {})
        if stats:
            st.html("<div style='margin-top: 15px; margin-bottom: 5px; font-weight: 700; color: #00FFCC; font-size: 0.95rem;'>📊 Riepilogo Statistiche Ciclo</div>")
            
            righe_sottotrading = []
            fasi_sotto = ["Micro", "Flip", "Ticket1", "Ticket2", "OverGain", "OverLoss", "Ultima"]
            tot_pnl_sub = 0.0
            tot_trade_sub = 0
            tot_prof_sub = 0
            tot_loss_sub = 0
            
            for k in fasi_sotto:
                s_data = stats.get(k, {"pnl": 0.0, "totale": 0, "profit": 0, "loss": 0})
                pnl = s_data.get("pnl", 0.0)
                tot = s_data.get("totale", 0)
                prof = s_data.get("profit", 0)
                loss = s_data.get("loss", 0)
                tot_pnl_sub += pnl
                tot_trade_sub += tot
                tot_prof_sub += prof
                tot_loss_sub += loss
                
                col_p = "#09ab3b" if pnl > 0 else ("#ff4b4b" if pnl < 0 else "#aaa")
                seg = "+" if pnl > 0 else ""
                righe_sottotrading.append(f"""
                <tr style='border-bottom: 1px solid rgba(255,255,255,0.05);'>
                    <td style='padding: 6px 10px; text-align: left;'><b>{k}</b></td>
                    <td style='padding: 6px 10px; text-align: center;'>{tot}</td>
                    <td style='padding: 6px 10px; text-align: center; color: #09ab3b;'>{prof}</td>
                    <td style='padding: 6px 10px; text-align: center; color: #ff4b4b;'>{loss}</td>
                    <td style='padding: 6px 10px; text-align: right; color: {col_p}; font-weight: bold;'>{seg}{pnl:.2f} €</td>
                </tr>
                """)
            
            col_sub = "#09ab3b" if tot_pnl_sub > 0 else ("#ff4b4b" if tot_pnl_sub < 0 else "#aaa")
            seg_sub = "+" if tot_pnl_sub > 0 else ""
            
            riga_totale_sub = f"""
            <tr style='background-color: rgba(255,215,0,0.08); border-top: 1px solid rgba(255,215,0,0.3); border-bottom: 1px solid rgba(255,215,0,0.3); font-weight: bold;'>
                <td style='padding: 8px 10px; text-align: left; color: #FFD700;'>Totale Sottotrading</td>
                <td style='padding: 8px 10px; text-align: center; color: #FFD700;'>{tot_trade_sub}</td>
                <td style='padding: 8px 10px; text-align: center; color: #09ab3b;'>{tot_prof_sub}</td>
                <td style='padding: 8px 10px; text-align: center; color: #ff4b4b;'>{tot_loss_sub}</td>
                <td style='padding: 8px 10px; text-align: right; color: {col_sub}; font-weight: bold;'>{seg_sub}{tot_pnl_sub:.2f} €</td>
            </tr>
            """
            
            # Assicurazione e Fase3
            ass_data = stats.get("Assicurazione", {"pnl": 0.0})
            ass_pnl = ass_data.get("pnl", 0.0)
            col_ass = "#09ab3b" if ass_pnl > 0 else ("#ff4b4b" if ass_pnl < 0 else "#aaa")
            seg_ass = "+" if ass_pnl > 0 else ""
            riga_ass = f"""
            <tr style='border-bottom: 1px solid rgba(255,255,255,0.05);'>
                <td style='padding: 6px 10px; text-align: left;'><b>Assicurazione</b></td>
                <td style='padding: 6px 10px; text-align: center;'>-</td>
                <td style='padding: 6px 10px; text-align: center;'>-</td>
                <td style='padding: 6px 10px; text-align: center;'>-</td>
                <td style='padding: 6px 10px; text-align: right; color: {col_ass}; font-weight: bold;'>{seg_ass}{ass_pnl:.2f} €</td>
            </tr>
            """
            
            f3_data = stats.get("Fase3", {"pnl": 0.0})
            f3_pnl = f3_data.get("pnl", 0.0)
            col_f3 = "#09ab3b" if f3_pnl > 0 else ("#ff4b4b" if f3_pnl < 0 else "#aaa")
            seg_f3 = "+" if f3_pnl > 0 else ""
            riga_f3 = f"""
            <tr style='border-bottom: 1px solid rgba(255,255,255,0.05);'>
                <td style='padding: 6px 10px; text-align: left;'><b>Fase 3</b></td>
                <td style='padding: 6px 10px; text-align: center;'>-</td>
                <td style='padding: 6px 10px; text-align: center;'>-</td>
                <td style='padding: 6px 10px; text-align: center;'>-</td>
                <td style='padding: 6px 10px; text-align: right; color: {col_f3}; font-weight: bold;'>{seg_f3}{f3_pnl:.2f} €</td>
            </tr>
            """
            
            tot_generale = tot_pnl_sub + ass_pnl + f3_pnl
            col_gen = "#09ab3b" if tot_generale > 0 else ("#ff4b4b" if tot_generale < 0 else "#aaa")
            seg_gen = "+" if tot_generale > 0 else ""
            
            riga_totale_ciclo = f"""
            <tr style='background-color: rgba(0,255,204,0.08); border-top: 1px solid rgba(0,255,204,0.3); font-weight: bold;'>
                <td colspan='4' style='padding: 8px 10px; text-align: left; color: #00FFCC;'>TOTALE CICLO (Sub + Ass + F3)</td>
                <td style='padding: 8px 10px; text-align: right; color: {col_gen}; font-weight: bold; font-size: 0.9rem;'>{seg_gen}{tot_generale:.2f} €</td>
            </tr>
            """
            
            tabella_html = f"""
            <div class='table-responsive'>
            <table style='width: 100%; border-collapse: collapse; font-size: 0.82rem; background-color: rgba(255,255,255,0.03); border-radius: 6px; overflow: hidden; margin-top: 5px;'>
                <thead>
                    <tr style='background-color: rgba(255,255,255,0.08); color: #888; text-transform: uppercase; font-size: 0.75rem;'>
                        <th style='padding: 8px 10px; text-align: left;'>Fase / Modulo</th>
                        <th style='padding: 8px 10px; text-align: center;'>Trade</th>
                        <th style='padding: 8px 10px; text-align: center;'>Profit</th>
                        <th style='padding: 8px 10px; text-align: center;'>Loss</th>
                        <th style='padding: 8px 10px; text-align: right;'>PnL (€)</th>
                    </tr>
                </thead>
                <tbody>
                    {''.join(righe_sottotrading)}
                    {riga_totale_sub}
                    {riga_ass}
                    {riga_f3}
                    {riga_totale_ciclo}
                </tbody>
            </table>
            </div>
            """
            st.html(tabella_html)
    st.markdown("---")

def get_ig_headers(conto_selezionato):
    if DEV_MODE: return None
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
        /* Bottoni Selezione Conto Sidebar */
        section[data-testid="stSidebar"] div[data-testid="stButton"] > button {
            display: flex !important;
            justify-content: flex-start !important;
            align-items: center !important;
            padding: 2px 8px !important;
            border-radius: 6px !important;
            font-size: 0.72rem !important;
            font-weight: 600 !important;
            min-height: 28px !important;
            height: 28px !important;
            margin-bottom: 2px !important;
            white-space: nowrap !important;
        }
        section[data-testid="stSidebar"] div[data-testid="stButton"] div[data-testid="stMarkdownContainer"] {
            width: 100% !important;
            display: flex !important;
        }
        section[data-testid="stSidebar"] div[data-testid="stButton"] > button p {
            display: flex !important;
            justify-content: space-between !important;
            align-items: center !important;
            width: 100% !important;
            margin: 0 !important;
            font-size: 0.72rem !important;
            white-space: nowrap !important;
        }
        section[data-testid="stSidebar"] div[data-testid="stButton"] span[style*="color: rgb(255, 171, 0)"],
        section[data-testid="stSidebar"] div[data-testid="stButton"] span[style*="color:rgb(255, 171, 0)"],
        section[data-testid="stSidebar"] div[data-testid="stButton"] span[style*="orange"] {
            color: #FFD700 !important;
            font-weight: 700 !important;
            margin-left: auto !important;
            text-align: right !important;
        }
        section[data-testid="stSidebar"] div[data-testid="stButton"] > button[kind="primary"] {
            box-shadow: 0 2px 8px rgba(25, 135, 84, 0.4) !important;
        }
        @media (min-width: 769px) {
            section[data-testid="stSidebar"] { min-width: 220px !important; max-width: 220px !important; }
        }
        button[data-testid="stNumberInputStepUp"], button[data-testid="stNumberInputStepDown"] { display: flex !important; }
        div[data-testid="stNumberInputContainer"] { padding-left: 0.2rem !important; padding-right: 0.2rem !important; }
        
        /* Contenitore per Scrolling Orizzontale Fluido (Tabelle e Pannelli) */
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

        /* ========================================================= */
        /* --- REGOLE RESPONSIVE PER TABLET (fino a 1024px) --- */
        /* ========================================================= */
        @media (max-width: 1024px) {
            .ig-table { width: 100% !important; font-size: 0.82rem !important; }
            .ig-table th, .ig-table td { padding: 7px 5px !important; }
            .stat-table { font-size: 0.85rem !important; }
            .stat-table th, .stat-table td { padding: 7px 5px !important; }
            section[data-testid="stSidebar"] { min-width: 200px !important; max-width: 250px !important; }
        }

        /* ========================================================= */
        /* --- REGOLE RESPONSIVE PER SMARTPHONE (fino a 768px) --- */
        /* ========================================================= */
        @media (max-width: 768px) {
            /* Container generale e margini */
            .main .block-container {
                padding-top: 1.5rem !important;
                padding-left: 0.5rem !important;
                padding-right: 0.5rem !important;
                padding-bottom: 2rem !important;
                max-width: 100% !important;
            }

            /* Tipografia mobile friendly */
            h1 { font-size: 1.4rem !important; text-align: center !important; margin-bottom: 0.5rem !important; }
            h2 { font-size: 1.2rem !important; }
            h3 { font-size: 1.05rem !important; }
            h4 { font-size: 0.95rem !important; }
            
            div[data-testid="stMetricValue"] { font-size: 1.15rem !important; }
            div[data-testid="stMetricLabel"] { font-size: 0.75rem !important; }

            /* Tabelle Touch Friendly con scorrimento */
            .ig-table {
                min-width: 580px !important;
                width: 100% !important;
                font-size: 0.75rem !important;
                margin-bottom: 10px !important;
            }
            .ig-table th, .ig-table td {
                padding: 5px 3px !important;
                font-size: 0.72rem !important;
            }
            .stat-table {
                min-width: 520px !important;
                width: 100% !important;
                font-size: 0.75rem !important;
                margin-bottom: 15px !important;
            }
            .stat-table th, .stat-table td {
                padding: 5px 3px !important;
                font-size: 0.72rem !important;
            }

            /* Bottoni a misura di tocco */
            div[data-testid="stButton"] > button {
                padding: 4px 6px !important;
                font-size: 0.82rem !important;
                min-height: 38px !important;
            }
            div[data-testid="stButton"] > button[kind="primary"] {
                min-height: 34px !important;
                height: auto !important;
                font-size: 0.82rem !important;
                padding: 4px 8px !important;
            }
            /* Bottoni Selezione Conto Sidebar */
            section[data-testid="stSidebar"] div[data-testid="stButton"] > button {
                padding: 2px 6px !important;
                font-size: 0.72rem !important;
                min-height: 28px !important;
                height: 28px !important;
            }
            section[data-testid="stSidebar"] div[data-testid="stButton"] > button p {
                font-size: 0.72rem !important;
            }

            /* Barra dei Tab a scorrimento orizzontale */
            div[data-baseweb="tab-list"] {
                display: flex !important;
                overflow-x: auto !important;
                white-space: nowrap !important;
                -webkit-overflow-scrolling: touch !important;
                scrollbar-width: thin !important;
                padding-bottom: 4px !important;
            }
            div[data-baseweb="tab"] {
                flex-shrink: 0 !important;
                padding: 8px 12px !important;
                font-size: 0.85rem !important;
            }

            /* Sidebar mobile fluida */
            section[data-testid="stSidebar"] {
                min-width: 250px !important;
                max-width: 85vw !important;
            }

            /* Righe Sintesi */
            .sintesi-testo {
                font-size: 0.82rem !important;
                height: auto !important;
            }

            /* Modal/Dialogo WIP */
            div[data-testid="stModal"] > div {
                width: 95vw !important;
                max-width: 95vw !important;
                padding: 10px !important;
            }
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
    st.session_state.ruolo = "VIEWER"
    st.session_state.conti_autorizzati = []
    st.session_state.tutti_i_conti = False

if not st.session_state.logged_in:
    if st.session_state.get("must_change_password"):
        st.title("🔐 Cambio Password Obbligatorio")
        st.warning("È il tuo primo accesso o la password è stata resettata. Inserisci una nuova password per continuare.")
        with st.form("change_pwd_form"):
            new_pw = st.text_input("Nuova Password", type="password")
            new_pw2 = st.text_input("Conferma Password", type="password")
            if st.form_submit_button("Salva e Accedi"):
                if new_pw and new_pw == new_pw2 and new_pw != "init":
                    auth_manager.modifica_password(st.session_state.temp_user, new_pw)
                    st.session_state.must_change_password = False
                    st.session_state.logged_in = True
                    st.session_state.user = st.session_state.temp_user
                    res = auth_manager.verifica_login(st.session_state.user, new_pw)
                    st.session_state.ruolo = res.get("ruolo", "VIEWER")
                    st.session_state.conti_autorizzati = res.get("conti_autorizzati", [])
                    st.session_state.tutti_i_conti = res.get("tutti_i_conti", False)
                    st.rerun()
                elif new_pw == "init":
                    st.error("La nuova password non può essere 'init'.")
                else:
                    st.error("Le password non coincidono o sono vuote.")
    else:
        st.title("🔐 Fiordok Trading")
        st.subheader("Accedi al pannello di controllo")
        with st.form("login_form"):
            user = st.text_input("Account")
            pw = st.text_input("Password", type="password")
            if st.form_submit_button("Accedi"):
                res = auth_manager.verifica_login(user, pw)
                if res.get("success"):
                    if pw == "init":
                        st.session_state.must_change_password = True
                        st.session_state.temp_user = user
                        st.rerun()
                    else:
                        st.session_state.logged_in = True
                        st.session_state.user = user
                        st.session_state.ruolo = res.get("ruolo", "VIEWER")
                        st.session_state.conti_autorizzati = res.get("conti_autorizzati", [])
                        st.session_state.tutti_i_conti = res.get("tutti_i_conti", False)
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
        
        @st.fragment(run_every=15)
        def renderizza_sidebar_conti():
            conto_attivo = st.session_state.get("conto_selezionato", conto_selezionato)
            if conti_reali:
                st.markdown("<p style='font-size: 0.78rem; font-weight: 700; color: #ff4b4b; margin: 10px 0 4px 0; letter-spacing: 0.8px;'>🔴 CONTI REALI</p>", unsafe_allow_html=True)
                for cr in conti_reali:
                    nome_cr_clean = cr.replace("_REALE", "")
                    st_cr = leggi_stato_sistema(cr)
                    cap_cr = formatta_eur(st_cr.get('saldo', '0'))
                    is_sel = (cr == conto_attivo)
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
                    is_sel = (cd == conto_attivo)
                    label_cd = f"🔵 {nome_cd_clean}: :orange[{cap_cd} €]"
                    if st.button(label_cd, key=f"side_acc_{cd}", type="primary" if is_sel else "secondary", use_container_width=True):
                        if not is_sel:
                            st.session_state.conto_selezionato = cd
                            st.rerun()
                            
        renderizza_sidebar_conti()
                        
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

            durata_str = "--"
            path_token = os.path.join(conto_selezionato, FILE_TOKEN)
            if motore_attivo_side and os.path.exists(path_token):
                try:
                    durata_sec = time.time() - os.path.getmtime(path_token)
                    ore = int(durata_sec // 3600)
                    minuti = int((durata_sec % 3600) // 60)
                    durata_str = f"{ore}h {minuti}m"
                except Exception:
                    durata_str = stato_side.get("durata_sessione", "--")
            elif motore_attivo_side:
                durata_str = stato_side.get("durata_sessione", "--")

            val_capitale = formatta_eur(stato_side.get('saldo', '0'))
            val_margine = formatta_eur(stato_side.get('margine', '0'))
            val_residuo = formatta_eur(stato_side.get('disponibile', '0'))
            val_dd = formatta_eur(stato_side.get('drawdown', '0'))
            
            try:
                dd_num = float(stato_side.get('drawdown', '0'))
                col_dd = "#ef4444" if dd_num < 0 else ("#09ab3b" if dd_num > 0 else "inherit")
            except:
                col_dd = "inherit"

            stato_box_html = f"""
            <div style='margin: 6px 0; padding: 4px 0; border-top: 1px solid rgba(255,255,255,0.1); border-bottom: 1px solid rgba(255,255,255,0.1);'>
                <div style='font-size: 0.78rem; color: #bbb; display: flex; justify-content: space-between; align-items: center;'>
                    <span>Stato Sistema:</span>
                    <span>{badge_motore_side}</span>
                </div>
                <div style='font-size: 0.75rem; color: #888; margin-top: 2px; display: flex; justify-content: space-between; align-items: center;'>
                    <span>⏱️ Sessione:</span>
                    <b style='color: #4ade80;'>{durata_str}</b>
                </div>
            </div>
            """
            st.markdown(stato_box_html, unsafe_allow_html=True)
            
            # --- INVESTIMENTO INIZIALE ---
            inv_iniziale_saved = float(prefs_side.get("investimento_iniziale", 0.0))
            def salva_inv_side():
                key_k = f"side_inv_input_{conto_selezionato}"
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
                key=f"side_inv_input_{conto_selezionato}",
                on_change=salva_inv_side
            )

            # Calcolo Delta assoluto e percentuale rispetto all'Investimento Iniziale
            delta_html = ""
            inv_attuale = float(st.session_state.get(f"side_inv_input_{conto_selezionato}", inv_iniziale_saved))
            if inv_attuale > 0:
                try:
                    saldo_float = float(stato_side.get('saldo', 0.0))
                    margine_float = float(stato_side.get('margine', 0.0))
                    diff_val = saldo_float - inv_attuale
                    col_diff = "#4ade80" if diff_val > 0 else ("#ef4444" if diff_val < 0 else "#aaa")
                    sign_diff = "+" if diff_val > 0 else ""
                    diff_eur_str = formatta_eur(diff_val)
                    
                    diff_pct = (diff_val / inv_attuale) * 100.0
                    sign_pct = "+" if diff_pct > 0 else ""
                    pct_str = f" {sign_pct}{diff_pct:.2f}%"
                        
                    delta_html = f"<div style='font-size: 0.82rem; font-weight: bold; color: {col_diff}; margin-top: 1px;'>({sign_diff}{diff_eur_str}{pct_str})</div>"
                except Exception:
                    pass

            st.markdown(f"<div style='font-size: 0.80rem; color: #aaa; margin-top: 4px;'>Capitale Totale</div><div style='font-size: 1.05rem; font-weight: bold; color: #FFD700;'>{val_capitale} €</div>{delta_html}", unsafe_allow_html=True)
            st.markdown(f"<div style='font-size: 0.80rem; color: #aaa; margin-top: 6px;'>Margine Utilizzato</div><div style='font-size: 1.05rem; font-weight: bold; color: #ef4444;'>{val_margine} €</div>", unsafe_allow_html=True)
            st.markdown(f"<div style='font-size: 0.80rem; color: #aaa; margin-top: 6px;'>Margine Residuo</div><div style='font-size: 1.05rem; font-weight: bold; color: #4ade80;'>{val_residuo} €</div>", unsafe_allow_html=True)
            st.markdown(f"<div style='font-size: 0.80rem; color: #aaa; margin-top: 6px;'>Drawdown (P/L)</div><div style='font-size: 1.05rem; font-weight: bold; color: {col_dd};'>{val_dd} €</div>", unsafe_allow_html=True)
        
        renderizza_sidebar_stats()

    ruolo = st.session_state.get("ruolo", "VIEWER")
    is_regista = (ruolo == "REGISTA")

    if is_regista:
        tabs = st.tabs(["💼 Portafoglio IG", "📈 Sintesi", "🛡️ Operatività", "🛑 Recovery", "📊 Statistiche", "📄 Report", "📊 Grafici", "💻 Console", "🔐 Autorizzazioni"])
        tab_portafoglio, tab_sintesi, tab_operativa, tab_restore, tab_statistiche, tab_report, tab_grafici, tab_console, tab_autorizzazioni = tabs
    else:
        tabs = st.tabs(["💼 Portafoglio IG", "📈 Sintesi", "📄 Report", "📊 Grafici"])
        tab_portafoglio, tab_sintesi, tab_report, tab_grafici = tabs
        tab_operativa = tab_restore = tab_console = tab_autorizzazioni = tab_statistiche = None

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
                        if "OL" in stato_sys:
                            sat_price = float(param_memoria.get("sat_price", 0))
                            tp = float(param_memoria.get("tp", 0))
                            c = CONFIG_STRUMENTI.get(nome_strum, {})
                            mult = c.get("moltiplicatore", 1)
                            if sat_price > 0 and tp > 0:
                                pos_level = float(pos_dict.get('level', 0))
                                distance_pts = abs(pos_level - sat_price) / mult
                                if distance_pts > (tp / 8):
                                    return "OverLoss"
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
                    if "TICKET1" in stato_sys: return "Ticket1"
                    if "SATELLIT" in stato_sys or "STANDBY" in stato_sys:
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
            th_tipo_pos = "<th style='text-align: center; color: white;'><u>TIPO</u></th>" if is_regista else ""
            html_pos = f"<h4 style='margin-top: 20px; text-align: center;'><u>Posizioni Aperte</u></h4>\n<div class='table-responsive'>\n<table class='ig-table'>\n<thead><tr><th style='text-align: left; color: #888; padding-left: 15px;'><u>MERCATO</u></th><th style='text-align: center; color: white;'><u>SIZE</u></th><th style='text-align: center; color: white;'><u>APERTURA</u></th><th style='text-align: center; color: white;'><u>ULTIMO</u></th><th style='text-align: center; color: white;'><u>STOP</u></th><th style='text-align: center; color: white;'><u>LIMITE</u></th>{th_tipo_pos}<th style='text-align: center; color: white;'><u>P/L (EUR)</u></th></tr></thead>\n<tbody>\n"
            
            totale_pnl_portafoglio = 0.0
            
            # Pre-calcolo strutture per Rowspan
            master_rows = []
            def get_group_total_size(posizioni):
                return sum(float(p['position']['size']) for p in posizioni)
                
            pos_row_counts = {}
            for k, posizioni in gruppi_pos.items():
                nome_r = k[0]
                count = 1 + (len(posizioni) if len(posizioni) > 1 else 0)
                pos_row_counts[nome_r] = pos_row_counts.get(nome_r, 0) + count
                
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
                
                stop_str = ""
                if len(stops) > 1: stop_str = "<span class='ig-multiplo'>Multiplo</span>"
                elif len(stops) == 1:
                    val = list(stops)[0]
                    stop_str = formatta_numero(val, dec) if val != "NONE" else ""
                
                lim_str = ""
                if len(limits) > 1: lim_str = "<span class='ig-multiplo'>Multiplo</span>"
                elif len(limits) == 1:
                    val = list(limits)[0]
                    lim_str = formatta_numero(val, dec) if val != "NONE" else ""
                
                pnl_class = "pnl-pos" if tot_pnl_eur >= 0 else "pnl-neg"
                pnl_str = f"{tot_pnl_eur:.0f} €"
                
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

                if is_first_of_instrument:
                    r_span = pos_row_counts.get(nome, 1)
                    td_mercato = f"<td rowspan='{r_span}' class='col-mercato' style='vertical-align: middle; border-right: 1px solid rgba(255,255,255,0.05);'><div style='display: flex; align-items: center;'><span class='ig-dot'></span>{formatta_mercato_con_bandiere(nome)}</div></td>"
                else:
                    td_mercato = ""

                td_tipo_master = f"<td><span class='{size_class}' style='font-weight: normal;'><u>{ruolo_master_str}</u></span></td>" if is_regista else ""
                html_pos += f"<tr class='ig-row ig-master-row' style='{master_style}'>{td_mercato}<td class='{size_class}'><u>{sign}{tot_size:g}</u></td><td class='{size_class}'><u>{formatta_numero(avg_entry, dec)}</u></td><td style='color: #00E676;'>{prezzo_str}</td><td>{stop_str}</td><td>{lim_str}</td>{td_tipo_master}<td class='{pnl_class}'><u>{pnl_str}</u></td></tr>\n"
                
                if has_subrows:
                    for idx, p in enumerate(posizioni):
                        sz = float(p['position']['size'])
                        lvl = float(p['position']['level'])
                        
                        dt_utc = datetime.strptime(p['position']['createdDateUTC'], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
                        data_str = dt_utc.astimezone().strftime("%d/%m/%y %H:%M")
                        
                        s_str = ""
                        if p['position'].get('stopLevel'): s_str = formatta_numero(p['position']['stopLevel'], dec)
                        elif p['position'].get('stopDistance'): s_str = "Stop" 
                        
                        l_str = ""
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
                        
                        td_tipo_child = f"<td><span class='{size_class}' style='font-weight: normal;'>{ruolo_child}</span></td>" if is_regista else ""
                        html_pos += f"<tr class='ig-row ig-subrow' style='{subrow_style}'><td class='{size_class}'>{sign}{sz:g}</td><td class='{size_class}'>{formatta_numero(lvl, dec)}<br><span style='font-size: 0.75rem; color: #888;'>{data_str}</span></td><td></td><td>{s_str}</td><td>{l_str}</td>{td_tipo_child}<td class='{pnl_c_class}'>{pnl_child_eur:.0f} €</td></tr>\n"
            
            totale_class = "pnl-pos" if totale_pnl_portafoglio >= 0 else "pnl-neg"
            empty_tds = "<td></td><td></td><td></td><td></td><td></td><td></td>" if is_regista else "<td></td><td></td><td></td><td></td><td></td>"
            html_pos += f"<tr class='ig-row' style='background-color: rgba(255,255,255,0.05); border-top: 2px solid #888;'><td class='col-mercato' style='font-weight: normal;'>Totale</td>{empty_tds}<td class='{totale_class}' style='font-size: 1rem;'>{totale_pnl_portafoglio:.0f} €</td></tr>\n</tbody></table></div>"
            
            if not pos_data: html_pos = "<h4 style='margin-top: 20px; text-align: center;'><u>Posizioni Aperte</u></h4><p style='color: #888; font-style: italic; text-align: center;'>Nessuna posizione aperta al momento.</p>"

            st.html(html_pos)
            
            # --- ELABORAZIONE ORDINI PENDENTI ---
            th_tipo_ord = "<th style='text-align: center; color: white;'><u>TIPO</u></th>" if is_regista else ""
            html_ord = f"<h4 style='margin-top: 40px; text-align: center;'><u>Ordini di Apertura</u></h4>\n<div class='table-responsive'>\n<table class='ig-table'>\n<thead><tr><th style='text-align: left; color: #888; padding-left: 15px;'><u>MERCATO</u></th><th style='text-align: center; color: white;'><u>SIZE</u></th><th style='text-align: center; color: white;'><u>LIVELLO</u></th><th style='text-align: center; color: white;'><u>STOP</u></th><th style='text-align: center; color: white;'><u>LIMITE</u></th>{th_tipo_ord}</tr></thead>\n<tbody>\n"
            
            # Ordino i pendenti per nome e poi per size
            ord_data_sorted = sorted(ord_data, key=lambda x: (
                epic_to_name.get(x['marketData']['epic'], x['marketData']['epic']),
                -float(x['workingOrderData'].get('orderSize', x['workingOrderData'].get('size', 0)))
            ))
            
            # Calcolo rowspan per ordini pendenti
            ord_counts = {}
            for o in ord_data_sorted:
                epic = o['marketData']['epic']
                n = epic_to_name.get(epic, epic)
                ord_counts[n] = ord_counts.get(n, 0) + 1
            
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
                
                s_str = ""
                if wo.get('stopDistance'): s_str = f"{int(float(wo['stopDistance']))}"
                
                l_str = ""
                if wo.get('limitDistance'): l_str = f"{int(float(wo['limitDistance']))}"
                
                ruolo_ord = get_role_ord(nome, dir, sz, memoria_attuale.get(nome, {}), wo)
                
                is_last_of_instrument = True
                if i < len(ord_data_sorted) - 1:
                    next_epic = ord_data_sorted[i+1]['marketData']['epic']
                    next_nome = epic_to_name.get(next_epic, next_epic)
                    if next_nome == nome:
                        is_last_of_instrument = False
                        
                row_style = "border-bottom: 2px solid rgba(255,255,255,0.3);" if is_last_of_instrument else ""
                
                is_first_of_instrument_ord = (i == 0 or epic_to_name.get(ord_data_sorted[i-1]['marketData']['epic'], ord_data_sorted[i-1]['marketData']['epic']) != nome)
                
                if is_first_of_instrument_ord:
                    r_span = ord_counts.get(nome, 1)
                    td_mercato_ord = f"<td rowspan='{r_span}' class='col-mercato' style='vertical-align: middle; border-right: 1px solid rgba(255,255,255,0.05);'><div style='display: flex; align-items: center;'><span class='ig-dot'></span>{formatta_mercato_con_bandiere(nome)}</div></td>"
                else:
                    td_mercato_ord = ""
                
                td_tipo_ord = f"<td><span class='{size_class}' style='font-weight: normal;'>{ruolo_ord}</span></td>" if is_regista else ""
                html_ord += f"<tr class='ig-row' style='{row_style}'>{td_mercato_ord}<td class='{size_class}'>{sign}{sz:g}</td><td class='{size_class}'>{formatta_numero(lvl, dec)}</td><td>{s_str}</td><td>{l_str}</td>{td_tipo_ord}</tr>\n"
                
            html_ord += "</tbody></table></div>"
            
            if not ord_data: html_ord = "<h4 style='margin-top: 40px; text-align: center;'><u>Ordini di Apertura</u></h4><p style='color: #888; font-style: italic; text-align: center;'>Nessun ordine pendente al momento.</p>"

            st.html(html_ord)
            
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

            ultima_operazione_testo = ""
            path_storico = os.path.join(conto_selezionato, "storico_operazioni.csv")
            try:
                if os.path.exists(path_storico):
                    with open(path_storico, "r", encoding="utf-8") as f:
                        last_line = None
                        for riga in f:
                            if riga.strip(): last_line = riga
                        if last_line and not last_line.startswith("Data,"):
                            parti = last_line.strip().split(",")
                            if len(parti) >= 4:
                                dt, strum, fase, pnl = parti[0], parti[1], parti[2], float(parti[3])
                                try:
                                    dt_obj = datetime.strptime(dt, "%Y-%m-%d %H:%M:%S")
                                    dt_fmt = dt_obj.strftime("%d/%m %H:%M")
                                except:
                                    dt_fmt = dt
                                segno = "+" if pnl > 0 else ""
                                col_pnl = "#09ab3b" if pnl > 0 else "#ff4b4b"
                                ultima_operazione_testo = f"<div style='font-size: 1rem; color: #FFD700; margin-top: 5px; font-weight: 500;'>⏱️ Ultima Op: <b>{strum}</b> - {fase} ({dt_fmt}) | <span style='color:{col_pnl}; font-weight:bold;'>{segno}{pnl:.0f} €</span></div>"
            except Exception:
                pass

            st.html(f"""
            <div style='display: flex; flex-wrap: wrap; justify-content: space-between; align-items: flex-end; gap: 10px; margin-top: -15px; margin-bottom: 20px;'>
                <div>
                    <h3 style='margin: 0; font-size: 1.6rem;'>📋 Sintesi Strumenti</h3>
                    {ultima_operazione_testo}
                </div>
                <div style='font-size: 1.05rem; font-weight: 500; display: flex; gap: 20px; align-items: center;'>
                    <span><span style='color: #888;'>Saldo:</span> {saldo_val} €</span>
                    <span><span style='color: #888;'>P/L:</span> <span style='color: {color_dd};'>{dd_val} €</span></span>
                </div>
            </div>
            """)
            
            with st.container(border=True):
                c1, c2, c3, c4 = st.columns([1.5, 3.5, 1.8, 3.2])
                c1.markdown("<div style='color: #888; font-size: 0.85rem; font-weight: 700; text-transform: uppercase; margin-top: 5px; margin-bottom: -5px;'>Strumento (WIP)</div>", unsafe_allow_html=True)
                c2.markdown("<div style='color: #888; font-size: 0.85rem; font-weight: 700; text-transform: uppercase; margin-top: 5px; margin-bottom: -5px;'>Fase Attuale</div>", unsafe_allow_html=True)
                c3.markdown("<div style='color: #888; font-size: 0.85rem; font-weight: 700; text-transform: uppercase; margin-top: 5px; margin-bottom: -5px;'>LIVE</div>", unsafe_allow_html=True)
                c4.markdown("<div style='color: #888; font-size: 0.85rem; font-weight: 700; text-transform: uppercase; margin-top: 5px; margin-bottom: -5px;'>Ultimo Evento</div>", unsafe_allow_html=True)
                st.markdown("<hr style='margin-top: 15px; margin-bottom: 15px; border-top: 1px solid rgba(255, 255, 255, 0.1);'>", unsafe_allow_html=True)
                
                tutti_strumenti = ["AUD/CAD", "AUD/NZD", "CAD/JPY", "EUR/GBP", "GBP/USD", "USD/CAD", "USD/CHF", "USD/JPY", "Spot Gold", "US 500 Cash"]
                # Mostra tutti gli strumenti, ordina mettendo prima quelli attivi, poi in ordine alfabetico
                strumenti_ordinati = sorted(tutti_strumenti, key=lambda x: (not memoria.get(x, {}).get("attivo", False), x))
                
                for nome in strumenti_ordinati:
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
                        stato_display += " [+ Ticket2]"

                    if is_attivo:
                        stato_visivo = f"<span style='background-color: rgba(40, 167, 69, 0.15); color: #09ab3b; padding: 4px 8px; border-radius: 4px; font-weight: bold; font-size: 0.82rem;'>⚡ ATTIVA ({stato_display}{spia})</span>"
                        if stato == "FASE_2_STANDBY":
                            stato_visivo = f"<span style='background-color: #FFD700; color: #000000; padding: 4px 8px; border-radius: 4px; font-weight: bold; font-size: 0.82rem;'>⏳ STANDBY (Attesa Rientro)</span>"
                    else:
                        if stato == "MANUALE":
                            stato_visivo = f"<span style='background-color: rgba(220, 53, 69, 0.15); color: #ff4b4b; padding: 4px 8px; border-radius: 4px; font-weight: bold; font-size: 0.82rem;'>⚠️ MANUALE</span>"
                        else:
                            stato_visivo = f"<span style='background-color: rgba(108, 117, 125, 0.15); color: #adb5bd; padding: 4px 8px; border-radius: 4px; font-weight: bold; font-size: 0.82rem;'>⏸️ IN ATTESA</span>"
                    
                    has_anomalia = bool(dati.get("alert_falso_allarme") or dati.get("errore_avvio") or dati.get("errore_ripristino") or dati.get("msg_manuale"))
                    
                    if has_anomalia:
                        bg_color = "#FFC107" # Giallo
                        text_color = "black"
                    elif is_attivo:
                        bg_color = "#198754" # Verde
                        text_color = "white"
                    else:
                        bg_color = "#495057" # Grigio scuro
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
                            mostra_diario_wip(nome, storico, conto=conto_selezionato)
                    
                    c2.markdown(f"<div style='height: 32px; display: flex; align-items: center;'>{stato_visivo}</div>", unsafe_allow_html=True)
                    c3.markdown(f"<div style='height: 32px; display: flex; align-items: center;'><span style='display: inline-block; min-width: 80px; width: auto; white-space: nowrap; text-align: center; font-family: monospace; font-size: 1.1rem; color: #FFD700; letter-spacing: 0.5px; border: 1px solid rgba(255, 215, 0, 0.5); padding: 3px 8px; border-radius: 5px; background-color: rgba(255, 215, 0, 0.08);'>{prezzo}</span></div>", unsafe_allow_html=True)
                    ultimo_evento_raw = storico[-1] if storico else "Nessun evento registrato in questo ciclo."
                    ultimo_evento = formatta_ultimo_evento_sintesi(ultimo_evento_raw, dati, nome)
                    c4.markdown(f"<div style='font-size: 0.85rem; color: white; line-height: 1.3; display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden;'>{ultimo_evento}</div>", unsafe_allow_html=True)
                    st.markdown("<div style='margin-bottom: 12px;'></div>", unsafe_allow_html=True)
                    
        renderizza_sintesi()

    if tab_operativa is not None:
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
                        c_bal1.markdown(f"<div style='font-size: 0.9rem; color: #aaa; font-weight: 600; margin-bottom: -5px;'>CAPITALE TOTALE</div><div style='font-size: 1.4rem; font-weight: bold; color: #FFD700;'>{formatta_eur(stato.get('saldo', '0'))} EUR</div>", unsafe_allow_html=True)
                        c_bal2.markdown(f"<div style='font-size: 0.9rem; color: #aaa; font-weight: 600; margin-bottom: -5px;'>CAPITALE DISPONIBILE</div><div style='font-size: 1.4rem; font-weight: bold; color: #4ade80;'>{formatta_eur(stato.get('disponibile', '0'))} EUR</div>", unsafe_allow_html=True)
                    
                        st.markdown("<div style='margin-bottom: 15px;'></div>", unsafe_allow_html=True)
                    
                        c_bal3, c_bal4 = st.columns(2)
                        c_bal3.markdown(f"<div style='font-size: 0.9rem; color: #aaa; font-weight: 600; margin-bottom: -5px;'>MARGINE UTILIZZATO</div><div style='font-size: 1.4rem; font-weight: bold; color: #ef4444;'>{formatta_eur(stato.get('margine', '0'))} EUR</div>", unsafe_allow_html=True)
                    
                        try:
                            dd_num_op = float(stato.get('drawdown', '0'))
                            dd_col_op = "#09ab3b" if dd_num_op > 0 else ("#ef4444" if dd_num_op < 0 else "white")
                        except:
                            dd_col_op = "white"
                        
                        c_bal4.markdown(f"<div style='font-size: 0.9rem; color: #aaa; font-weight: 600; margin-bottom: -5px;'>DRAWDOWN (P/L)</div><div style='font-size: 1.4rem; font-weight: bold; color: {dd_col_op};'>{formatta_eur(stato.get('drawdown', '0'))} EUR</div>", unsafe_allow_html=True)
                        st.caption(stato.get('messaggio', ''))

                st.markdown("---")

                def crea_riquadro_strumento(nome, tipo, tp_default, opp_default, dts_default, size_default=4):
                    with st.container(border=True):
                        dati_salvati = memoria_attuale.get(nome, {})
                        stato_corrente = dati_salvati.get("stato", "IN_ATTESA")
                        stato_attivo = dati_salvati.get("attivo", False)
                        direzione = dati_salvati.get("direzione", "")
                        modalita_manuale = dati_salvati.get("modalita_manuale", False)
                        is_sospeso_wk = dati_salvati.get("sospeso_weekend", False) and stato_attivo
                        is_sosp_rollover = dati_salvati.get("sospeso_rollover", False) and stato_attivo
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
                            titolo_html = formatta_titolo_con_bandiere_orizzontale(nome, badge)
                            st.markdown(titolo_html, unsafe_allow_html=True)
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
                        elif is_distanza_pericolosa: st.markdown(f"<div style='background-color: rgba(239, 68, 68, 0.15); border-left: 3px solid #ef4444; padding: 8px 12px; border-radius: 4px; font-size: 0.82rem; color: #fca5a5; margin-bottom: 15px;'>⚠️ <b>ATTENZIONE:</b> Stop Minimo IG: <b>{min_richiesto_ig} pt</b>. Impostato: <b>{min_impostato} pt</b>.</div>", unsafe_allow_html=True)
                        else: st.caption(f"📏 Distanza richiesta da IG: **{min_richiesto_ig} pt** | Minimo Griglia: **{min_impostato} pt**")
                    
                        margine_u = CONFIG_STRUMENTI.get(nome, {}).get("margine_unitario", "N/D")
                        if margine_u != "N/D":
                            st.caption(f"🛡️ Margine (Size=1): **{margine_u}€**")

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
                    
                        if is_sospeso_wk:
                            st.warning("🌴 **MACCHINA IN SOSPENSIONE WEEKEND.** Le funzioni generali sono bloccate per proteggere la memoria. Clicca Riprendi per sbloccare la console e piazzare i Satelliti.")
                            if st.button("▶️ RIPRENDI", key=f"WK_{conto_selezionato}_{nome}", width="stretch"):
                                memoria_attuale[nome] = {**dati_salvati, "comando_riprendi": True, "comando_weekend": False, "msg_weekend": "", "tp": tp, "opp": opp, "dts": dts, "size": size, "errore_avvio": False, "errore_ripristino": False, "msg_manuale": ""}
                                salva_memoria(conto_selezionato, memoria_attuale)
                                st.rerun()
                        elif is_sosp_rollover:
                            st.warning("🌙 **PAUSA NOTTURNA (ROLLOVER) ATTIVA.** Le funzioni sono bloccate e gli ordini pendenti rimossi temporaneamente per protezione dallo spread. Ripresa automatica alle 00:29.")
                        elif modalita_manuale:
                            st.warning("⚠️ STRUMENTO IN MANUALE. Gestiscilo su IG.")
                            col_m1, col_m2 = st.columns(2, vertical_alignment="center")
                            with col_m1:
                                if st.button("🛰️ RIATTIVA AUTO (Fase 2)", key=f"RIATT_{conto_selezionato}_{nome}", width="stretch"):
                                    memoria_attuale[nome] = {**dati_salvati, "comando_riattiva_fase2": True, "msg_manuale": "", "sospeso_weekend": False}
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
                                if "FASE_2" in stato_corrente:
                                    if st.button("🌴 WEEKEND", key=f"WK_{conto_selezionato}_{nome}", width="stretch"):
                                        memoria_attuale[nome] = {**dati_salvati, "comando_weekend": True, "msg_weekend": "", "tp": tp, "opp": opp, "dts": dts, "size": size, "errore_avvio": False, "errore_ripristino": False, "msg_manuale": ""}
                                        salva_memoria(conto_selezionato, memoria_attuale)
                                        st.rerun()
                                elif is_sosp_rollover:
                                    st.warning("🌙 ROLLOVER")
                                else:
                                    st.success("✔️ OK")
                            with c_sync:
                                if st.button("🔄 SYNC", key=f"SYNC_{conto_selezionato}_{nome}", width="stretch"):
                                    dialog_sync(conto_selezionato, nome)

                        if not modalita_manuale:
                            if stato_attivo:
                                if is_sospeso_wk: st.warning(f"🌴 IN PAUSA WEEKEND ({direzione}) | In attesa di ripresa")
                                elif is_sosp_rollover: st.warning(f"🌙 IN PAUSA ROLLOVER ({direzione}) | In attesa delle 00:29")
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

    if tab_restore is not None:
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
                opzioni = ["Ordine ULTIMA (Pendente)", "Posizione TAGLIO CORE (A Mercato)"]

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
                        p_base = st.number_input("Prezzo Base Core mancante in memoria. Inseriscilo manualmente per calcolare la Micro:", value=0.0, format="%.5f", step=0.5, key=f"rec_pb_micro_{conto_selezionato}_{r_nome}")
                    if not p_base or p_base <= 0:
                        st.error("Prezzo base Core mancante. Inseriscilo per proseguire.")
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
                        p_base = st.number_input("Prezzo Base Core mancante in memoria. Inseriscilo manualmente per calcolare i Satelliti OCO:", value=0.0, format="%.5f", step=0.5, key=f"rec_pb_sat1_{conto_selezionato}_{r_nome}")
                    if not p_base or p_base <= 0:
                        st.error("Prezzo base Core mancante. Inseriscilo per proseguire.")
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

                elif "TAGLIO CORE" in r_anom:
                    f3_dir = dati.get("fase3_dir")
                    f3_step = dati.get("fase3_step", 1)
                    if not f3_dir:
                        st.error("Dati Fase 3 mancanti in memoria.")
                    else:
                        d_contro = "SELL" if f3_dir == "BUY" else "BUY"
                        s_taglio = round(s_core * 0.35, 2) if f3_step == 1 else s_core # actually we should just try to close what is there, let's use 0.35 for step 1
                        # Wait, s_taglio is handled correctly if we just provide the command
                        st.info("Il Taglio Core è un ORDINE A MERCATO per chiudere parte (o tutta) la posizione. Il motore eseguirà la chiusura parziale.")
                        cmd_data = {"azione": "MERCATO", "dir": d_contro, "size": s_taglio, "lim": None, "stop": None, "etichetta": f"[RECOVERY TAGLIO CORE STEP {f3_step}]"}

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

    if tab_statistiche is not None:
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
                            if "2" in f or "TICKET1" in f or "TICKET2" in f or "SAT" in f or "OVERGAIN" in f or "OVERLOSS" in f or "OG" in f or "OL" in f: return "F2"
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
                    
                        html_t1 = "<div class='table-responsive'><table class='stat-table'><thead><tr><th>STRUMENTO</th><th>P/L TOT.</th><th>F1</th><th>F2</th><th>F3</th><th>ALTRO</th></tr></thead><tbody>"
                        for _, row in pivot_strum.iterrows():
                            strum = row['Strumento']
                        
                            def format_td(val, is_bold=False):
                                if abs(val) < 0.001: return "<td></td>"
                                color_class = "text-green" if val > 0 else "text-red"
                                bold_class = "text-bold" if is_bold else ""
                                return f"<td class='{color_class} {bold_class}'>€ {val:.2f}</td>"
                            
                            td_pl = format_td(row['P/L Tot.'], is_bold=False)
                            td_f1 = format_td(row['F1'])
                            td_f2 = format_td(row['F2'])
                            td_f3 = format_td(row['F3'])
                            td_alt = format_td(row['Altro'])
                        
                            html_t1 += f"<tr><td>{strum}</td>{td_pl}{td_f1}{td_f2}{td_f3}{td_alt}</tr>"
                        html_t1 += "</tbody></table></div>"
                    
                        st.html(html_t1)
                        st.html("<br>")
                    
                        # --- RENDIMENTO PER FASE (Sotto) ---
                        st.subheader("Rendimento per Fase")
                        df_fase = df_filtrato.groupby('Fase').agg(
                            Pnl_Totale=('Profitto_EUR', 'sum'),
                            Tot_Op=('Profitto_EUR', 'count'),
                            Vincenti=('Profitto_EUR', lambda x: (x > 0).sum()),
                            Perdenti=('Profitto_EUR', lambda x: (x <= 0).sum())
                        ).reset_index()
                    
                        html_t2 = "<div class='table-responsive'><table class='stat-table'><thead><tr><th>FASE</th><th>P/L TOT.</th><th>TOT. OP.</th><th>WIN</th><th>LOSS</th><th>WIN RATE %</th></tr></thead><tbody>"
                        for _, row in df_fase.iterrows():
                            fase = row['Fase']
                            pnl = row['Pnl_Totale']
                            tot_op = row['Tot_Op']
                            win = row['Vincenti']
                            loss = row['Perdenti']
                            wr = (win / tot_op * 100) if tot_op > 0 else 0
                        
                            pnl_class = "text-green" if pnl > 0 else ("text-red" if pnl < 0 else "")
                            pnl_str = f"€ {pnl:.2f}" if abs(pnl) >= 0.001 else "€ 0.00"
                        
                            win_class = "text-green" if win > 0 else ""
                            loss_class = "text-red" if loss > 0 else ""
                            wr_class = "text-green" if wr >= 50 else ("text-red" if wr > 0 else "")
                        
                            html_t2 += f"<tr><td>{fase}</td><td class='{pnl_class}'>{pnl_str}</td><td>{tot_op}</td><td class='{win_class}'>{win}</td><td class='{loss_class}'>{loss}</td><td class='{wr_class}'>{wr:.1f}%</td></tr>"
                        html_t2 += "</tbody></table></div>"
                    
                        st.html(html_t2)
                    

                    
                    else:
                        st.info("Nessuna operazione registrata nel periodo selezionato.")
                except Exception as e:
                    st.error(f"Errore nella lettura del file storico: {e}")
            else:
                st.warning("Nessun dato statistico disponibile. Il file storico verrà creato alla prima operazione chiusa.")

    if tab_console is not None:
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
                
                logs_escaped = logs.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br>")
                st.html(f"""
                    <div style='
                        background-color: #1E1E1E; 
                        color: #D4D4D4; 
                        font-family: "Courier New", Courier, monospace; 
                        font-size: 0.82rem; 
                        padding: 10px; 
                        border-radius: 5px; 
                        max-height: 500px; 
                        overflow-y: auto;
                        line-height: 1.4;
                        white-space: nowrap;
                    '>
                        {logs_escaped}
                    </div>
                """)
            
            renderizza_console()

    with tab_report:
        st.markdown("<h2 style='text-align: center; color: #00FFCC;'>📄 Report Giornaliero</h2>", unsafe_allow_html=True)
        st.markdown("<p style='text-align: center; color: #888; font-size: 0.9rem;'>Visualizza lo storico dei valori salvati automaticamente ogni giorno feriale alle 21:30.</p>", unsafe_allow_html=True)
        
        file_report = os.path.join(conto_selezionato, "report_giornaliero.csv") if conto_selezionato else "report_giornaliero.csv"
        
        @st.dialog("🗑️ Reset Database Report")
        def dialog_reset_db_report(f_rep, min_d, max_d, df_rep):
            st.markdown(f"Seleziona l'intervallo temporale da eliminare per il conto **{conto_selezionato}**.")
            st.markdown("<p style='font-size: 0.8rem; color: #888;'>L'eliminazione è definitiva e rimuoverà i dati storici dal file report del conto.</p>", unsafe_allow_html=True)
            
            today_d = datetime.today().date()
            c_r1, c_r2 = st.columns(2)
            with c_r1:
                res_da = st.date_input("Data Iniziale", value=min_d, min_value=min_d, max_value=today_d, key="dialog_reset_da")
            with c_r2:
                def_max = max_d if max_d <= today_d else today_d
                res_a = st.date_input("Data Finale (compresa)", value=def_max, min_value=res_da, max_value=today_d, key="dialog_reset_a")
                
            m_del = (df_rep['Data_dt'].dt.date >= res_da) & (df_rep['Data_dt'].dt.date <= res_a)
            num_del = int(m_del.sum())
            
            if num_del > 0:
                st.warning(f"⚠️ Verranno eliminati **{num_del}** record compresi tra il **{res_da}** e il **{res_a}**.")
            else:
                st.info(f"Nessun record trovato tra il {res_da} e il {res_a}.")
                
            st.markdown("<div style='margin-top: 15px;'></div>", unsafe_allow_html=True)
            btn_c1, btn_c2 = st.columns(2)
            with btn_c1:
                if st.button("❌ Annulla", key="cancel_reset_rep", use_container_width=True):
                    st.rerun()
            with btn_c2:
                if st.button("🗑️ Elimina Record", type="primary", key="confirm_reset_rep", use_container_width=True, disabled=(num_del == 0)):
                    df_rimasti = df_rep.loc[~m_del].drop(columns=['Data_dt'], errors='ignore')
                    df_rimasti.to_csv(f_rep, index=False)
                    st.success(f"✅ {num_del} record eliminati con successo!")
                    time.sleep(1)
                    st.rerun()

        if os.path.exists(file_report):
            df_report = pd.read_csv(file_report)
            
            if 'Data' in df_report.columns:
                df_report = df_report.drop_duplicates(subset=['Data'], keep='last')
                df_report['Data_dt'] = pd.to_datetime(df_report['Data'], format="%Y-%m-%d", errors='coerce')
                df_report = df_report.dropna(subset=['Data_dt'])
                min_date = df_report['Data_dt'].min().date() if not df_report.empty else datetime.today().date()
                max_date = df_report['Data_dt'].max().date() if not df_report.empty else datetime.today().date()
                
                c1, c2, c3 = st.columns([2, 2, 1])
                with c1:
                    da_data = st.date_input("Da data", value=min_date, key=f"rep_da_data_{conto_selezionato}")
                with c2:
                    a_data = st.date_input("A data", value=datetime.today().date(), key=f"rep_a_data_{conto_selezionato}")
                with c3:
                    st.markdown("<div style='margin-top: 28px;'></div>", unsafe_allow_html=True)
                    if st.button("🗑️ Reset DB", key=f"btn_open_reset_db_{conto_selezionato}", use_container_width=True, help="Elimina un intervallo di date dal DB del report"):
                        dialog_reset_db_report(file_report, min_date, max_date, df_report)
                
                prefs_tab = carica_preferenze(conto_selezionato)
                inv_iniziale_tab = float(st.session_state.get(f"side_inv_input_{conto_selezionato}", prefs_tab.get("investimento_iniziale", 0.0)))
                
                st.markdown(f"""
                <div style='text-align: center; margin: 10px auto 20px auto; padding: 6px 14px; background: rgba(255,215,0,0.06); border: 1px solid rgba(255,215,0,0.25); border-radius: 8px; max-width: 440px;'>
                    <span style='color: #bbb; font-size: 0.85rem;'>💰 Investimento Iniziale di riferimento:</span>
                    <b style='color: #FFD700; font-size: 1.05rem; margin-left: 6px;'>{formatta_eur(inv_iniziale_tab)} €</b>
                </div>
                """, unsafe_allow_html=True)
                    
                mask = (df_report['Data_dt'].dt.date >= da_data) & (df_report['Data_dt'].dt.date <= a_data)
                df_filtrato = df_report.loc[mask].sort_values(by='Data_dt', ascending=False)
                
                if df_filtrato.empty:
                    st.info("Nessun dato registrato nell'intervallo di date selezionato.")
                else:
                    righe_tabella = []
                    for _, riga in df_filtrato.iterrows():
                        d_str = str(riga.get('Data', ''))
                        try:
                            cap_val = float(riga.get('Capitale Totale', 0.0))
                        except:
                            cap_val = 0.0
                        try:
                            marg_val = float(riga.get('Margine Utilizzato', 0.0))
                        except:
                            marg_val = 0.0
                        try:
                            dd_val = float(riga.get('Drawdown', 0.0))
                        except:
                            dd_val = 0.0
                            
                        # Calcolo Rendimento
                        diff_abs = cap_val - inv_iniziale_tab if inv_iniziale_tab > 0 else 0.0
                        diff_pct = (diff_abs / inv_iniziale_tab * 100.0) if inv_iniziale_tab > 0 else 0.0
                        
                        if inv_iniziale_tab <= 0:
                            rend_html = "<span style='color: #888;'>--</span>"
                        elif diff_abs > 0:
                            pct_str = f"{diff_pct:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                            rend_html = f"<span style='color: #4ade80; font-weight: 600;'>+{formatta_eur(diff_abs)} € (+{pct_str}%)</span>"
                        elif diff_abs < 0:
                            pct_str = f"{abs(diff_pct):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                            rend_html = f"<span style='color: #ff6b6b; font-weight: 600;'>-{formatta_eur(abs(diff_abs))} € (-{pct_str}%)</span>"
                        else:
                            rend_html = "<span style='color: #bbb;'>0,00 € (0,00%)</span>"
                            
                        # Drawdown styling
                        if dd_val < 0:
                            dd_html = f"<span style='color: #ff6b6b; font-weight: 600;'>{formatta_eur(dd_val)} €</span>"
                        elif dd_val > 0:
                            dd_html = f"<span style='color: #4ade80; font-weight: 600;'>+{formatta_eur(dd_val)} €</span>"
                        else:
                            dd_html = "<span style='color: #bbb;'>0,00 €</span>"
                            
                        cap_html = f"<span style='color: #FFD700; font-weight: 600;'>{formatta_eur(cap_val)} €</span>"
                        marg_html = f"<span style='color: #d1d4dc;'>{formatta_eur(marg_val)} €</span>"
                        
                        righe_tabella.append(f"""
                        <tr style='border-bottom: 1px solid rgba(255,255,255,0.05);'>
                            <td style='padding: 8px 12px; text-align: center; color: #fff; font-weight: 500;'>{d_str}</td>
                            <td style='padding: 8px 12px; text-align: center;'>{cap_html}</td>
                            <td style='padding: 8px 12px; text-align: center;'>{rend_html}</td>
                            <td style='padding: 8px 12px; text-align: center;'>{marg_html}</td>
                            <td style='padding: 8px 12px; text-align: center;'>{dd_html}</td>
                        </tr>
                        """)
                        
                    tabella_report_html = f"""
                    <div class='table-responsive'>
                    <table style='width: 90%; max-width: 900px; margin: 0 auto; border-collapse: collapse; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; font-size: 0.86rem; background-color: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.08); border-radius: 8px; overflow: hidden; box-shadow: 0 4px 16px rgba(0,0,0,0.25);'>
                        <thead>
                            <tr style='background-color: rgba(0,255,204,0.08); border-bottom: 1px solid rgba(0,255,204,0.25); color: #00FFCC; text-transform: uppercase; font-size: 0.76rem; letter-spacing: 0.5px;'>
                                <th style='padding: 10px 12px; text-align: center;'>📅 Data</th>
                                <th style='padding: 10px 12px; text-align: center;'>💰 Capitale Totale</th>
                                <th style='padding: 10px 12px; text-align: center;'>📈 Rendimento (%)</th>
                                <th style='padding: 10px 12px; text-align: center;'>🔒 Margine Utilizzato</th>
                                <th style='padding: 10px 12px; text-align: center;'>📉 Drawdown</th>
                            </tr>
                        </thead>
                        <tbody>
                            {''.join(righe_tabella)}
                        </tbody>
                    </table>
                    </div>
                    """
                    st.html(tabella_report_html)
            else:
                st.dataframe(df_report, use_container_width=True, hide_index=True)
        else:
            st.info("Nessun report giornaliero disponibile al momento. Il primo salvataggio avverrà alle 21:30 (da lunedì a venerdì).")

    with tab_grafici:
        st.markdown("<h2 style='text-align: center; color: #FFD700;'>📊 Grafici Interattivi (IG Live)</h2>", unsafe_allow_html=True)
        
        c1, c2, c3 = st.columns([2,2,1])
        with c1:
            grafico_strum = st.selectbox("Seleziona Strumento", options=list(CONFIG_STRUMENTI.keys()), key="grafico_strum")
        with c2:
            res_options = {"5 Minuti": "MINUTE_5", "15 Minuti": "MINUTE_15", "1 Ora": "HOUR", "4 Ore": "HOUR_4", "Daily": "DAY", "Weekly": "WEEK"}
            grafico_res_label = st.selectbox("Timeframe", options=list(res_options.keys()), index=2, key="grafico_res")
            grafico_res = res_options[grafico_res_label]
        with c3:
            st.write("")
            st.write("")
            btn_aggiorna = st.button("🔄 Aggiorna Grafico", use_container_width=True)
            
        if btn_aggiorna:
            def fetch_and_calc_sr(epic, h_api, base_url, res, window=5):
                import json
                import os
                import time
                
                cache_file = os.path.join(ROOT_DIR, "Logs_e_Cache", f"sr_cache_{epic}_{res}.json")
                
                # Cache valida per 7 giorni (livelli W/M non cambiano intraday)
                if os.path.exists(cache_file):
                    if time.time() - os.path.getmtime(cache_file) < 604800: # 7 giorni
                        try:
                            with open(cache_file, "r") as f:
                                data = json.load(f)
                                return data.get("peaks", []), data.get("troughs", [])
                        except Exception:
                            pass
                
                try:
                    num_candles = 36 if res == "WEEK" else 24
                    url = f"{base_url}/prices/{epic}/{res}/{num_candles}"
                    resp = requests.get(url, headers=h_api)
                    if resp.status_code == 200:
                        data = resp.json().get("prices", [])
                        if data:
                            df_sr = pd.DataFrame([{
                                'High': p['highPrice']['bid'],
                                'Low': p['lowPrice']['bid']
                            } for p in data])
                            
                            df_sr['Peak'] = df_sr['High'] == df_sr['High'].rolling(window, center=True).max()
                            df_sr['Trough'] = df_sr['Low'] == df_sr['Low'].rolling(window, center=True).min()
                            
                            peaks = df_sr[df_sr['Peak']]['High'].tail(2).tolist()
                            troughs = df_sr[df_sr['Trough']]['Low'].tail(2).tolist()
                            
                            # Save to cache
                            os.makedirs(os.path.dirname(cache_file), exist_ok=True)
                            with open(cache_file, "w") as f:
                                json.dump({"peaks": peaks, "troughs": troughs}, f)
                                
                            return peaks, troughs
                    else:
                        if os.path.exists(cache_file):
                            try:
                                with open(cache_file, "r") as f:
                                    data = json.load(f)
                                    return data.get("peaks", []), data.get("troughs", [])
                            except Exception:
                                pass
                except Exception:
                    pass
                return [], []

            with st.spinner("Aggiornamento storico da IG (modalità cache)..."):
                epic = CONFIG_STRUMENTI[grafico_strum]["epic"]
                h_api = get_ig_headers(conto_selezionato)
                if h_api:
                    # Logica Cache Intelligente per minimizzare consumo API
                    import os
                    cache_file = os.path.join(ROOT_DIR, "Logs_e_Cache", f"cache_candele_{epic}_{grafico_res}.csv")
                    max_fetch = 350
                    df_cache = None
                    
                    if os.path.exists(cache_file):
                        try:
                            df_cache = pd.read_csv(cache_file, parse_dates=['Time'])
                            if not df_cache.empty:
                                last_time = df_cache['Time'].iloc[-1]
                                gap_minutes = (pd.Timestamp.utcnow().tz_localize(None) - last_time).total_seconds() / 60
                                res_to_min = {"MINUTE_5": 5, "MINUTE_15": 15, "HOUR": 60, "HOUR_4": 240, "DAY": 1440, "WEEK": 10080}
                                # Calcoliamo le candele mancanti + un buffer stretto di 10 candele
                                candles_needed = int(abs(gap_minutes) / res_to_min.get(grafico_res, 60)) + 10
                                if candles_needed < 350:
                                    max_fetch = max(5, candles_needed)
                        except Exception:
                            pass

                    # Usiamo la versione 2 e il path corretto
                    h_api["Version"] = "2"
                    base_url = "https://api.ig.com/gateway/deal" if "_REALE" in conto_selezionato.upper() else "https://demo-api.ig.com/gateway/deal"
                    url = f"{base_url}/prices/{epic}/{grafico_res}/{max_fetch}"
                    
                    resp = requests.get(url, headers=h_api)
                    df = None
                    if resp.status_code == 200:
                        data = resp.json().get("prices", [])
                        if data:
                            df_new = pd.DataFrame([{
                                'Time': p['snapshotTime'],
                                'Open': p['openPrice']['bid'],
                                'High': p['highPrice']['bid'],
                                'Low': p['lowPrice']['bid'],
                                'Close': p['closePrice']['bid']
                            } for p in data])
                            
                            df_new['Time'] = pd.to_datetime(df_new['Time'])
                            
                            # Merge con la cache
                            if df_cache is not None and not df_cache.empty:
                                df = pd.concat([df_cache, df_new]).drop_duplicates(subset=['Time'], keep='last').sort_values('Time').tail(600)
                            else:
                                df = df_new
                                
                            # Salva cache aggiornata per i click successivi
                            os.makedirs(os.path.dirname(cache_file), exist_ok=True)
                            df.to_csv(cache_file, index=False)
                        else:
                            if df_cache is not None and not df_cache.empty:
                                df = df_cache
                            else:
                                st.warning("Nessun dato restituito dall'API per questo timeframe.")
                    else:
                        if df_cache is not None and not df_cache.empty:
                            df = df_cache
                            st.warning("⚠️ Limite settimanale dati storici IG raggiunto. Grafico visualizzato dall'ultima cache salvata.")
                        else:
                            st.error(f"Errore API IG: {resp.text}\n(Nessuna cache locale disponibile per {grafico_strum}. Si sbloccherà al reset settimanale di IG).")
                    
                    if df is not None and not df.empty:
                        # Calcolo Donchian Midlines
                        df['Donchian_55'] = (df['High'].rolling(55).max() + df['Low'].rolling(55).min()) / 2
                        df['Donchian_21'] = (df['High'].rolling(21).max() + df['Low'].rolling(21).min()) / 2
                        
                        # Calcolo HMA 377
                        def WMA(s, period):
                            weights = np.arange(1, period + 1)
                            return s.rolling(period).apply(lambda x: np.dot(x, weights) / weights.sum(), raw=True)
                        
                        if len(df) >= 377:
                            half_len = int(377 / 2)
                            sqrt_len = int(np.sqrt(377))
                            wmaf = WMA(df['Close'], half_len)
                            wmas = WMA(df['Close'], 377)
                            diff = 2 * wmaf - wmas
                            df['HMA_377'] = WMA(diff, sqrt_len)
                        else:
                            df['HMA_377'] = np.nan
                            
                        # Punti Pivot (Daily e Weekly)
                        df['Date'] = df['Time'].dt.date
                        df['YearWeek'] = df['Time'].dt.isocalendar().year.astype(str) + '-' + df['Time'].dt.isocalendar().week.astype(str)
                        
                        daily_agg = df.groupby('Date').agg({'High': 'max', 'Low': 'min', 'Close': 'last'})
                        daily_agg['Pivot_Daily'] = (daily_agg['High'] + daily_agg['Low'] + daily_agg['Close']) / 3
                        daily_agg['Pivot_Daily'] = daily_agg['Pivot_Daily'].shift(1)
                        
                        weekly_agg = df.groupby('YearWeek').agg({'High': 'max', 'Low': 'min', 'Close': 'last'})
                        weekly_agg['Pivot_Weekly'] = (weekly_agg['High'] + weekly_agg['Low'] + weekly_agg['Close']) / 3
                        weekly_agg['Pivot_Weekly'] = weekly_agg['Pivot_Weekly'].shift(1)
                        
                        df = df.merge(daily_agg[['Pivot_Daily']], on='Date', how='left')
                        df = df.merge(weekly_agg[['Pivot_Weekly']], on='YearWeek', how='left')
                        
                        # Costruzione Plotly Figure
                        fig = go.Figure()
                        
                        # Candele
                        fig.add_trace(go.Candlestick(
                            x=df['Time'], open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], 
                            name='Prezzo', 
                            increasing_line_color='white', increasing_fillcolor='#7CFC00', 
                            decreasing_line_color='white', decreasing_fillcolor='#FA8072'
                        ))
                        
                        # Estrazione ultimi valori per la legenda
                        val_d55 = round(df['Donchian_55'].iloc[-1], 5) if pd.notna(df['Donchian_55'].iloc[-1]) else "-"
                        val_d21 = round(df['Donchian_21'].iloc[-1], 5) if pd.notna(df['Donchian_21'].iloc[-1]) else "-"
                        val_hma = round(df['HMA_377'].iloc[-1], 5) if pd.notna(df['HMA_377'].iloc[-1]) else "-"
                        val_pd = round(df['Pivot_Daily'].iloc[-1], 5) if pd.notna(df['Pivot_Daily'].iloc[-1]) else "-"
                        val_pw = round(df['Pivot_Weekly'].iloc[-1], 5) if pd.notna(df['Pivot_Weekly'].iloc[-1]) else "-"
                        
                        # Kijun (Gialla, tratto-punto, spessa)
                        fig.add_trace(go.Scatter(x=df['Time'], y=df['Donchian_55'], mode='lines', name=f'<span style="color:yellow;">Kijun<br><b>{val_d55}</b></span>', line=dict(color='yellow', dash='dashdot', width=2.5)))
                        
                        # Tenkan (Azzurro/Blu chiaro, tratto-punto, spessa)
                        fig.add_trace(go.Scatter(x=df['Time'], y=df['Donchian_21'], mode='lines', name=f'<span style="color:#00BFFF;">Tenkan<br><b>{val_d21}</b></span>', line=dict(color='#00BFFF', dash='dashdot', width=2.5)))
                        
                        # HMA 377 (Grigio Chiaro, tratto-punto, spessa)
                        if df['HMA_377'].notna().any():
                            fig.add_trace(go.Scatter(x=df['Time'], y=df['HMA_377'], mode='lines', name=f'<span style="color:lightgray;">HMA 377<br><b>{val_hma}</b></span>', line=dict(color='lightgray', dash='dashdot', width=2.5)))
                        
                        # Pivot (Solo l'ultimo per non sporcare il grafico storico)
                        fig.add_trace(go.Scatter(x=[None], y=[None], mode='lines', name=f'<span style="color:#4CAF50;">Pivot Daily<br><b>{val_pd}</b></span>', line=dict(color='#4CAF50', width=2)))
                        fig.add_trace(go.Scatter(x=[None], y=[None], mode='lines', name=f'<span style="color:orange;">Pivot Weekly<br><b>{val_pw}</b></span>', line=dict(color='orange', width=2)))
                        
                        last_date = df['Date'].iloc[-1]
                        group_daily = df[df['Date'] == last_date]
                        if group_daily['Pivot_Daily'].notna().any():
                            fig.add_trace(go.Scatter(x=group_daily['Time'], y=group_daily['Pivot_Daily'], mode='lines', showlegend=False, line=dict(color='#4CAF50', width=2)))
                            
                        last_week = df['YearWeek'].iloc[-1]
                        group_weekly = df[df['YearWeek'] == last_week]
                        if group_weekly['Pivot_Weekly'].notna().any():
                            fig.add_trace(go.Scatter(x=group_weekly['Time'], y=group_weekly['Pivot_Weekly'], mode='lines', showlegend=False, line=dict(color='orange', width=2)))
                        
                        # Macro Supporti e Resistenze (ProRealTrend style)
                        peaks_w, troughs_w = fetch_and_calc_sr(epic, h_api, base_url, "WEEK", 5)
                        peaks_m, troughs_m = fetch_and_calc_sr(epic, h_api, base_url, "MONTH", 5)
                        
                        for p in peaks_w:
                            fig.add_hline(y=p, line_dash="dot", line_color="salmon", opacity=0.8, annotation_text="Resistenza (W)", annotation_position="top left")
                        for t in troughs_w:
                            fig.add_hline(y=t, line_dash="dot", line_color="limegreen", opacity=0.8, annotation_text="Supporto (W)", annotation_position="bottom left")
                        for p in peaks_m:
                            fig.add_hline(y=p, line_dash="dash", line_color="salmon", opacity=1.0, line_width=2, annotation_text="Resistenza (M)", annotation_position="top right")
                        for t in troughs_m:
                            fig.add_hline(y=t, line_dash="dash", line_color="limegreen", opacity=1.0, line_width=2, annotation_text="Supporto (M)", annotation_position="bottom right")

                        
                        # Zoom Iniziale asse X e Y (ultime 100 candele per tutti i timeframe)
                        visible = 100
                        
                        if visible < len(df):
                            x_start = df['Time'].iloc[-visible]
                            x_end = df['Time'].iloc[-1]
                            xaxis_dict = dict(rangeslider=dict(visible=False), range=[x_start, x_end], rangebreaks=[dict(bounds=["sat", "mon"])])
                            
                            # Calcolo min/max per centrare asse Y sulle candele visibili
                            df_vis = df.tail(visible)
                            cols_to_check = ['High', 'Low', 'Donchian_55', 'Donchian_21', 'HMA_377', 'Pivot_Daily', 'Pivot_Weekly']
                            min_y = df_vis[cols_to_check].min().min()
                            max_y = df_vis[cols_to_check].max().max()
                            padding = (max_y - min_y) * 0.05
                            yaxis_dict = dict(side='right', range=[min_y - padding, max_y + padding])
                        else:
                            xaxis_dict = dict(rangeslider=dict(visible=False), rangebreaks=[dict(bounds=["sat", "mon"])])
                            yaxis_dict = dict(side='right')
                        
                        fig.update_layout(
                            title=f'{grafico_strum} - {grafico_res_label}',
                            template='plotly_dark',
                            dragmode='pan',
                            yaxis=yaxis_dict,
                            xaxis=xaxis_dict,
                            height=750,
                            margin=dict(l=20, r=20, t=100, b=20),
                            legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="left", x=0)
                        )
                        
                        st.plotly_chart(fig, use_container_width=True, config={'scrollZoom': True})
                else:
                    st.error("Connessione IG mancante. Avvia il Motore per generare il token.")

    if tab_autorizzazioni is not None:
        with tab_autorizzazioni:
            st.markdown("## 🔐 Gestione Autorizzazioni")
            st.write("Solo il Regista ha accesso a questa sezione. Qui puoi gestire gli account Viewer e assegnare i conti visibili.")
            
            with st.expander("➕ Aggiungi Nuovo Utente", expanded=False):
                with st.form("form_nuovo_utente"):
                    n_user = st.text_input("Nickname (Username)")
                    n_ruolo = st.selectbox("Ruolo", ["VIEWER", "REGISTA"])
                    tutti_i_folders_disp = [c for c in os.listdir() if os.path.isdir(c) and (c.endswith("_DEMO") or c.endswith("_REALE"))]
                    n_conti = st.multiselect("Conti Visibili", tutti_i_folders_disp)
                    st.info("La password iniziale sarà impostata in automatico a 'init'. L'utente dovrà cambiarla al primo accesso.")
                    if st.form_submit_button("Crea Utente"):
                        if n_user:
                            ok, msg = auth_manager.aggiungi_utente(n_user, "init", n_ruolo, n_conti)
                            if ok: 
                                st.success(msg)
                            else: 
                                st.error(msg)
                        else:
                            st.error("Inserire l'username.")
            
            st.markdown("### Elenco Utenti")
            utenti = auth_manager.get_tutti_utenti()
            tutti_i_folders = [c for c in os.listdir() if os.path.isdir(c) and (c.endswith("_DEMO") or c.endswith("_REALE"))]
            
            for u, d in utenti.items():
                with st.container(border=True):
                    st.markdown(f"**👤 {u}** | Ruolo: `{d.get('ruolo')}`")
                    
                    if d.get('ruolo') != "REGISTA":
                        sel_conti = st.multiselect(f"Conti visibili per {u}", tutti_i_folders, default=[c for c in d.get("conti_autorizzati", []) if c in tutti_i_folders], key=f"conti_{u}")
                        
                        col1, col2, col3 = st.columns([1, 1, 1])
                        with col1:
                            if st.button("💾 Salva Permessi", key=f"salva_{u}"):
                                auth_manager.aggiorna_conti_utente(u, sel_conti)
                                st.success(f"Permessi aggiornati per {u}")
                        with col2:
                            if st.button("🔑 Reset Password", key=f"reset_{u}"):
                                auth_manager.modifica_password(u, "init")
                                st.success(f"Password per {u} resettata a 'init'.")
                        with col3:
                            if st.button("🗑️ Elimina", key=f"del_{u}"):
                                ok, msg = auth_manager.elimina_utente(u)
                                if ok: st.success(msg)
                                else: st.error(msg)
                    else:
                        col1, col2 = st.columns([1, 1])
                        with col1:
                            if st.button("🔑 Reset Password", key=f"reset_reg_{u}"):
                                auth_manager.modifica_password(u, "init")
                                st.success(f"Password per {u} resettata a 'init'.")
                        with col2:
                            if st.button("🗑️ Elimina Regista", key=f"del_reg_{u}"):
                                ok, msg = auth_manager.elimina_utente(u)
                                if ok: st.success(msg)
                                else: st.error(msg)

    # --- TAB SIMULATORE ---
