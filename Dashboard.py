import sys
sys.path.append("/data/libs")
import streamlit as st
import streamlit.components.v1 as components
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
    "AUD/NZD": {"epic": "CS.D.AUDNZD.MINI.IP", "moltiplicatore": 0.0001, "decimali": 5, "valuta": "NZD", "valore_punto": 1, "margine_unitario": 310},
    "CAD/JPY": {"epic": "CS.D.CADJPY.MINI.IP", "moltiplicatore": 0.01, "decimali": 3, "valuta": "JPY", "valore_punto": 100, "margine_unitario": 210},
    "EUR/USD": {"epic": "CS.D.EURUSD.CEBM.IP", "moltiplicatore": 0.0001, "decimali": 5, "valuta": "USD", "valore_punto": 1, "margine_unitario": 335},
    "GBP/JPY": {"epic": "CS.D.GBPJPY.MINI.IP", "moltiplicatore": 0.01, "decimali": 3, "valuta": "JPY", "valore_punto": 100, "margine_unitario": 350},
    "GBP/USD": {"epic": "CS.D.GBPUSD.MINI.IP", "moltiplicatore": 0.0001, "decimali": 5, "valuta": "USD", "valore_punto": 1, "margine_unitario": 400},
    "USD/CAD": {"epic": "CS.D.USDCAD.MINI.IP", "moltiplicatore": 0.0001, "decimali": 5, "valuta": "CAD", "valore_punto": 1, "margine_unitario": 300},
    "USD/CHF": {"epic": "CS.D.USDCHF.MINI.IP", "moltiplicatore": 0.0001, "decimali": 5, "valuta": "CHF", "valore_punto": 1, "margine_unitario": 290},
    "USD/JPY": {"epic": "CS.D.USDJPY.MINI.IP", "moltiplicatore": 0.01, "decimali": 3, "valuta": "JPY", "valore_punto": 100, "margine_unitario": 290},
    "Spot Gold": {"epic": "CS.D.CFEGOLD.CBE.IP", "moltiplicatore": 1, "decimali": 1, "valuta": "EUR", "valore_punto": 1, "margine_unitario": 220},
    "US 500 Cash": {"epic": "IX.D.SPTRD.IBE.IP", "moltiplicatore": 1, "decimali": 2, "valuta": "EUR", "valore_punto": 1, "margine_unitario": 400}
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

def formatta_mercato_con_bandiere(nome, color="#FFD700"):
    if len(nome) == 7 and nome[3] == '/':
        nome_clean = nome.replace("/", "")
        return f"<div style='display: flex; flex-direction: column; align-items: center; line-height: 1.1; margin-left: 10px;'><u style='color: {color}; font-size: 1.15em; font-weight: bold;'>{nome_clean}</u></div>"
    
    return f"<div style='display: flex; flex-direction: column; align-items: center; line-height: 1.1; margin-left: 10px;'><u style='color: {color}; font-size: 1.15em; font-weight: bold;'>{nome}</u></div>"

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
    eur_usd = prezzi.get("EUR/USD")
    gbp_usd = prezzi.get("GBP/USD")
    if not eur_usd:
        eur_gbp = prezzi.get("EUR/GBP")
        if eur_gbp and gbp_usd:
            eur_usd = eur_gbp * gbp_usd
        elif gbp_usd:
            eur_usd = 1.08
        else:
            eur_usd = 1.08
    
    if valuta == "USD": return 1.0 / eur_usd
    if valuta == "GBP": return (gbp_usd / eur_usd) if gbp_usd else (1.25 / eur_usd)
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
        return 0.58 / eur_usd
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
        mem[nome]["alert_falso_allarme"] = ""
        salva_memoria(conto, mem)
        st.toast(f"Comando di RECOVERY inviato per {nome}! In attesa di esecuzione...", icon="✅")
        st.rerun()

@st.dialog("Diario di Bordo (WIP)")
def mostra_diario_wip(nome_strumento, storico, conto=None):
    st.markdown(f"### 📈 Cronologia: {nome_strumento}")
    st.markdown("---")
    if storico:
        totale = 0.0
        for riga in storico:
            match = re.search(r"\[Parziale:\s*([+-]?\d+(?:\.\d+)?)\s*€\]", riga)
            if match:
                totale += float(match.group(1))
        
        righe_eventi = []
        for riga in storico:
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

@st.dialog("📈 Cronologia Trend WIP")
def mostra_diario_wip_trend(nome_strumento, storico, conto=None):
    st.markdown(f"### 📈 Cronologia Trend WIP: {nome_strumento}")
    st.markdown("---")
    
    conto_eff = conto or st.session_state.get("conto_selezionato", "FIORDOK_DEMO")
    mem_conto = carica_memoria(conto_eff)
    dati_inst = mem_conto.get(nome_strumento, {})
    stato_sys = leggi_stato_sistema(conto_eff)
    prezzi_live = stato_sys.get("prezzi_live", {})
    px = prezzi_live.get(nome_strumento)

    pos_core = dati_inst.get("posizioni_core", [])
    pos_incr = dati_inst.get("posizioni_incr", [])
    dir_t = dati_inst.get("direzione", "")

    c_cfg = CONFIG_STRUMENTI.get(nome_strumento, {})
    c_mult = c_cfg.get("moltiplicatore", 1)
    c_valore_punto = c_cfg.get("valore_punto", 1)
    c_valuta = c_cfg.get("valuta", "USD")
    c_rate = get_eur_rate(c_valuta, prezzi_live)

    # 1. Core [LONG/SHORT] [Aperta/Chiusa]: +-xxxx €
    if pos_core:
        c_p = pos_core[0]
        e_c = float(c_p.get("entry", 0))
        sz_c = float(c_p.get("size", 1))
        dir_c = c_p.get("direction", dir_t or "LONG")
        if px and c_mult > 0:
            pts_c = (px - e_c)/c_mult if dir_c == "LONG" else (e_c - px)/c_mult
            pnl_c = pts_c * sz_c * c_valore_punto * c_rate
        else:
            pnl_c = 0.0
        stato_c_lbl = "Aperta"
    else:
        dir_c = dir_t if dir_t else "-"
        pnl_c = 0.0
        for r in (storico or []):
            if any(k in r for k in ("Close Core", "Stop Core", "Trailing Core", "Paracadute Core")):
                m_c = re.search(r"\[PnL:\s*([+-]?\d+(?:[\.,]\d+)?)\s*€\]", r)
                if m_c:
                    pnl_c = float(m_c.group(1).replace(",", "."))
                    break
        stato_c_lbl = "Chiusa"

    col_oro = "#FFD700"
    segno_c = "+" if pnl_c >= 0.5 else ""
    col_c = "#00E676" if pnl_c >= 0.5 else ("#FA8072" if pnl_c <= -0.5 else "#cccccc")
    line1_html = f"<div><span style='color: {col_oro}; font-weight: normal;'>Core [{dir_c}] [{stato_c_lbl}]:</span> <span style='color: {col_c}; font-weight: normal;'>{segno_c}{pnl_c:.0f} €</span></div>"

    # 2. Incr. Chiusi [n1]: +-yyyy €
    tot_inc_c = 0.0
    n_inc_c = 0
    for r in (storico or []):
        if not any(k in r for k in ("Close Core", "Stop Core", "Trailing Core", "Paracadute Core")):
            m_inc = re.search(r"\[PnL:\s*([+-]?\d+(?:[\.,]\d+)?)\s*€\]", r)
            if m_inc:
                tot_inc_c += float(m_inc.group(1).replace(",", "."))
                n_inc_c += 1
    segno_ic = "+" if tot_inc_c >= 0.5 else ""
    col_ic = "#00E676" if tot_inc_c >= 0.5 else ("#FA8072" if tot_inc_c <= -0.5 else "#cccccc")
    line2_html = f"<div><span style='color: {col_oro}; font-weight: normal;'>Incr. Chiusi [{n_inc_c}]:</span> <span style='color: {col_ic}; font-weight: normal;'>{segno_ic}{tot_inc_c:.0f} €</span></div>"

    # 3. Incr. Aperti [n2]: +-zzzz €
    tot_inc_a = 0.0
    n_inc_a = len(pos_incr)
    for ip in pos_incr:
        e_i = float(ip.get("entry", 0))
        sz_i = float(ip.get("size", 1))
        dir_i = ip.get("direction", dir_t or "LONG")
        if px and c_mult > 0:
            pts_i = (px - e_i)/c_mult if dir_i == "LONG" else (e_i - px)/c_mult
            tot_inc_a += (pts_i * sz_i * c_valore_punto * c_rate)
    segno_ia = "+" if tot_inc_a >= 0.5 else ""
    col_ia = "#00E676" if tot_inc_a >= 0.5 else ("#FA8072" if tot_inc_a <= -0.5 else "#cccccc")
    line3_html = f"<div><span style='color: {col_oro}; font-weight: normal;'>Incr. Aperti [{n_inc_a}]:</span> <span style='color: {col_ia}; font-weight: normal;'>{segno_ia}{tot_inc_a:.0f} €</span></div>"

    # 4. Box Sintesi + Linea Divisoria
    box_sintesi_html = f"""
    <div style='background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.12); border-radius: 6px; padding: 10px 14px; font-family: monospace; font-size: 0.95rem; line-height: 1.6; margin-bottom: 8px;'>
        {line1_html}
        {line2_html}
        {line3_html}
    </div>
    <div style='letter-spacing: 2px; color: rgba(255,255,255,0.3); text-align: center; margin-bottom: 12px; font-weight: bold; font-size: 0.9rem;'>================================================</div>
    """
    st.html(box_sintesi_html)

    if storico:
        righe_eventi = []
        for riga in storico:
            riga_arr = re.sub(r"\[PnL:\s*([+-]?\d+)(?:[\.,]\d+)?\s*€\]", r"[PnL: \1 €]", riga)
            riga_colorata = re.sub(r"(\[PnL:.*?\])", r"<span style='color: #FFD700;'>\1</span>", riga_arr)
            righe_eventi.append(f"&bull; {riga_colorata}<br>")
        
        eventi_html = f"<div style='font-size: 0.85rem; line-height: 1.6; max-height: 350px; overflow-y: auto; padding-right: 5px;'>{''.join(righe_eventi)}</div>"
        st.html(eventi_html)
    else:
        st.info("Nessun evento Trend registrato in questo ciclo.")
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

def chiudi_posizioni_trend_su_ig(conto, nome_strumento):
    """Chiude immediatamente a mercato tutte le posizioni reali su IG aperte per lo strumento dato."""
    h = get_ig_headers(conto)
    if not h:
        return False, "Headers IG non disponibili", []
    
    base_url = "https://api.ig.com/gateway/deal" if "_REALE" in conto.upper() else "https://demo-api.ig.com/gateway/deal"
    epic = CONFIG_STRUMENTI.get(nome_strumento, {}).get("epic")
    
    h_v2 = h.copy()
    h_v2["VERSION"] = "2"
    
    try:
        r = requests.get(f"{base_url}/positions", headers=h_v2, timeout=6)
        if r.status_code != 200:
            return False, f"Errore recupero posizioni IG ({r.status_code})", []
        
        pos_list = r.json().get("positions", [])
        chiusi = 0
        errori = []
        rimaste = []
        
        h_del = h.copy()
        h_del["VERSION"] = "1"
        h_del["_method"] = "DELETE"
        
        clean_nome = nome_strumento.upper().replace("/", "").replace(" ", "")
        for p in pos_list:
            m = p.get("market", {})
            pos = p.get("position", {})
            p_epic = m.get("epic", "")
            p_name = m.get("instrumentName", "")
            clean_pname = p_name.upper().replace("/", "").replace(" ", "")
            
            # Match per epic o per nome strumento
            if (epic and p_epic == epic) or (clean_nome in clean_pname) or (clean_pname in clean_nome):
                deal_id = pos.get("dealId")
                direction = pos.get("direction")
                size = pos.get("size")
                m_status = m.get("marketStatus", "TRADEABLE")
                
                if m_status != "TRADEABLE":
                    errori.append(f"{m_status}")
                    rimaste.append(pos)
                    continue
                
                if deal_id and direction and size:
                    dir_chiusura = "SELL" if direction in ("BUY", "LONG") else "BUY"
                    body = {
                        "dealId": deal_id,
                        "direction": dir_chiusura,
                        "size": str(int(size)) if float(size).is_integer() else str(size),
                        "orderType": "MARKET"
                    }
                    r_c = requests.post(f"{base_url}/positions/otc", json=body, headers=h_del, timeout=8)
                    accettato = False
                    if r_c.status_code == 200:
                        ref = r_c.json().get("dealReference")
                        if ref:
                            for _ in range(4):
                                time.sleep(0.5)
                                try:
                                    r_conf = requests.get(f"{base_url}/confirms/{ref}", headers={"X-IG-API-KEY": h.get("X-IG-API-KEY"), "CST": h.get("CST"), "X-SECURITY-TOKEN": h.get("X-SECURITY-TOKEN"), "VERSION": "1"}, timeout=5)
                                    if r_conf.status_code == 200:
                                        c_data = r_conf.json()
                                        if c_data.get("dealStatus") == "ACCEPTED":
                                            accettato = True
                                            break
                                        elif c_data.get("dealStatus") == "REJECTED":
                                            errori.append(c_data.get("reason", "REJECTED"))
                                            break
                                except Exception:
                                    pass
                        if accettato:
                            chiusi += 1
                        else:
                            rimaste.append(pos)
                    else:
                        errori.append(f"HTTP {r_c.status_code}")
                        rimaste.append(pos)
                    time.sleep(0.5)
                    
        if rimaste or errori:
            err_str = ", ".join(set(errori)) if errori else "Posizioni non chiuse"
            return False, err_str, rimaste
        return True, f"{chiusi} posizioni chiuse", []
    except Exception as e:
        return False, str(e), []

def carica_radar_trend_dash(conto=None):
    """Carica i dati freschi da radar_trend.json come Unica Fonte di Verità per KJ e TK."""
    candidates = []
    if conto:
        candidates.append(os.path.join(conto, "radar_trend.json"))
        candidates.append(os.path.join("..", conto, "radar_trend.json"))
    for c_alt in ["FIORDOK_DEMO", "DANY_DEMO", "BONGIOLO_DEMO", "FIORDOK_REALE", "DANY_REALE", "BONGIOLO_REALE", "."]:
        candidates.append(os.path.join(c_alt, "radar_trend.json"))
        candidates.append(os.path.join("..", c_alt, "radar_trend.json"))
        
    for p in candidates:
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    d = json.load(f)
                    rad = d.get("radar_trend", {})
                    ts = d.get("radar_trend_ts")
                    if rad:
                        return rad, ts
            except Exception:
                pass
    return {}, None

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
    
    if mem_l.get("attivo", False) or mem_s.get("attivo", False):
        msg_l = f"- **{conto_l}** risulta già ATTIVO.\n" if mem_l.get("attivo", False) else ""
        msg_s = f"- **{conto_s}** risulta già ATTIVO.\n" if mem_s.get("attivo", False) else ""
        st.error(f"⚠️ **ATTENZIONE: Strumento già occupato!**\n\nPrima di avviare il Sincrono devi spegnere e chiudere {nome_strumento} sui conti selezionati per sistemare il portafoglio:\n{msg_l}{msg_s}")
        if st.button("❌ ANNULLA", key=f"sync_annulla_occ_{nome_strumento}"):
            st.session_state[f"sync_open_{nome_strumento}"] = False
            st.rerun()
        return
    
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


@st.dialog("Configurazione Avvio Multiconto (Trend + Range)", width="large")
def dialog_sync_start_trend(conto_partenza, nome_strumento):
    conti_disponibili = [d for d in os.listdir(".") if os.path.isdir(d) and (d.endswith("_DEMO") or d.endswith("_REALE"))]
    if len(conti_disponibili) < 2:
        st.error("⚠️ Sono necessari almeno due conti (Demo o Reali) per utilizzare l'Avvio Multiconto.")
        return
        
    st.markdown(f"### ⚖️ Avvio Multiconto Trend-Range per {nome_strumento}")
    st.write("Avvia contemporaneamente una gamba in **TREND** su un conto e una gamba di copertura in **RANGE** nella direzione opposta su un secondo conto.")
    st.info("ℹ️ **Regola Timeframe:** L'Avvio Multiconto Trend è consentito esclusivamente su **H1 (1 Ora)** e **H4 (4 Ore)**.")
    
    idx_trend = conti_disponibili.index(conto_partenza) if conto_partenza in conti_disponibili else 0
    idx_range = (idx_trend + 1) % len(conti_disponibili) if len(conti_disponibili) > 1 else 0
    
    col_c1, col_c2 = st.columns(2)
    with col_c1:
        conto_t = st.selectbox("📈 Conto TREND", conti_disponibili, index=idx_trend, key=f"synct_ct_{nome_strumento}")
        dir_trend = st.radio("Direzione Trend", ["LONG", "SHORT"], horizontal=True, key=f"synct_dir_{nome_strumento}")
        
        tf_options = {"HOUR": "H1 (1 Ora)", "HOUR_4": "H4 (4 Ore)"}
        mem_t_curr = carica_memoria(conto_t).get(nome_strumento, {})
        tf_curr = mem_t_curr.get("timeframe", "HOUR")
        if tf_curr not in tf_options:
            tf_curr = "HOUR"
        tf_keys = list(tf_options.keys())
        idx_tf = tf_keys.index(tf_curr) if tf_curr in tf_keys else 0
        tf_scelto = st.selectbox("Timeframe Trend (Solo H1 o H4)", tf_keys, index=idx_tf, format_func=lambda x: tf_options[x], key=f"synct_tf_{nome_strumento}")
        
    with col_c2:
        conto_r = st.selectbox("🔄 Conto RANGE (Opposto)", conti_disponibili, index=idx_range, key=f"synct_cr_{nome_strumento}")
        dir_range = "SHORT" if dir_trend == "LONG" else "LONG"
        dir_color = "#FA8072" if dir_range == "SHORT" else "#00E676"
        st.markdown(f"<div style='margin-top: 15px; margin-bottom: 25px;'><b>Direzione Range automatica:</b> <span style='color: {dir_color}; font-weight: bold; font-size: 1.15rem;'>{dir_range}</span></div>", unsafe_allow_html=True)
        
    if conto_t == conto_r:
        st.error("⚠️ Devi selezionare due conti differenti per l'Avvio Multiconto!")
        if st.button("❌ ANNULLA", key=f"synct_annulla_err_{nome_strumento}"):
            st.session_state[f"sync_trend_open_{nome_strumento}"] = False
            st.rerun()
        return
        
    # Info parametri di entrambi i conti
    mem_t = carica_memoria(conto_t).get(nome_strumento, {})
    mem_r = carica_memoria(conto_r).get(nome_strumento, {})
    
    if mem_t.get("attivo", False) or mem_r.get("attivo", False):
        msg_t = f"- **{conto_t}** risulta già ATTIVO.\n" if mem_t.get("attivo", False) else ""
        msg_r = f"- **{conto_r}** risulta già ATTIVO.\n" if mem_r.get("attivo", False) else ""
        st.error(f"⚠️ **ATTENZIONE: Strumento già occupato!**\n\nPrima di avviare il Multiconto Trend-Range devi spegnere e chiudere {nome_strumento} sui conti selezionati per sistemare il portafoglio:\n{msg_t}{msg_r}")
        if st.button("❌ ANNULLA", key=f"synct_annulla_occ_{nome_strumento}"):
            st.session_state[f"sync_trend_open_{nome_strumento}"] = False
            st.rerun()
        return
    
    sz_t = mem_t.get("size", 3)
    szm_t = mem_t.get("size_max", 5)
    sc_t = mem_t.get("scala", 1)
    
    is_asset = nome_strumento in ["Spot Gold", "US 500 Cash"]
    def_tp = 100 if is_asset else 50
    def_opp = 20 if is_asset else 10
    def_dts = 10 if is_asset else 5
    tp_r = mem_r.get("tp", def_tp)
    opp_r = mem_r.get("opp", def_opp)
    dts_r = mem_r.get("dts", def_dts)
    sz_r = mem_r.get("size", 4)
    
    # Controllo di coerenza Kijun per la gamba Trend
    tf_map_d = {"MINUTE_5": "M5", "MINUTE_10": "M10", "HOUR": "H1", "HOUR_4": "H4", "DAY": "D1"}
    tf_badge_d = tf_map_d.get(tf_scelto, "H1")
    
    rad_d, _ = carica_radar_trend_dash(conto_t)
    kj_dialog = None
    if rad_d and nome_strumento in rad_d:
        kj_dialog = rad_d[nome_strumento].get("timeframes", {}).get(tf_badge_d, {}).get("kj")
        
    st_t = leggi_stato_sistema(conto_t)
    px_live_dialog = st_t.get("prezzi_live", {}).get(nome_strumento)
    dec_d = CONFIG_STRUMENTI.get(nome_strumento, {}).get("decimali", 2)
    
    if kj_dialog is None:
        c_loc_d = carica_candele_locali_dash(conto_t, nome_strumento, tf_scelto, px_live=px_live_dialog)
        kj_dialog = calcola_kj55_da_candele_dash(c_loc_d, periods=55)
    
    blocco_multiconto = False
    msg_blocco_multi = ""
    if kj_dialog is not None and px_live_dialog is not None and isinstance(px_live_dialog, (int, float)):
        if dir_trend == "SHORT" and px_live_dialog > kj_dialog:
            blocco_multiconto = True
            msg_blocco_multi = f"🛑 **Blocco Kijun ({tf_options[tf_scelto]}):** Impossibile avviare la gamba Trend in **SHORT** perché il Prezzo Live ({px_live_dialog:.{dec_d}f}) si trova sopra la Kijun ({kj_dialog:.{dec_d}f})."
        elif dir_trend == "LONG" and px_live_dialog < kj_dialog:
            blocco_multiconto = True
            msg_blocco_multi = f"🛑 **Blocco Kijun ({tf_options[tf_scelto]}):** Impossibile avviare la gamba Trend in **LONG** perché il Prezzo Live ({px_live_dialog:.{dec_d}f}) si trova sotto la Kijun ({kj_dialog:.{dec_d}f})."
            
    if blocco_multiconto:
        st.error(msg_blocco_multi)
    
    st.markdown("---")
    col_info_t, col_info_r = st.columns(2)
    with col_info_t:
        st.markdown(f"**🎯 Parametri Trend ({conto_t}):**\n- TF: **{tf_options[tf_scelto]}**\n- Entry Size: **{sz_t}** | Max Size: **{szm_t}**\n- Scala: **{sc_t}**")
    with col_info_r:
        st.markdown(f"**🛡️ Parametri Range ({conto_r}):**\n- Direzione: **{dir_range}**\n- TP: **{tp_r}** | OPP: **{opp_r}**\n- DTS: **{dts_r}** | Size: **{sz_r}**")
        
    c_btn1, c_btn2 = st.columns(2)
    with c_btn1:
        if st.button("⚡ CONFERMA AVVIO MULTICONTO", type="primary", use_container_width=True, key=f"synct_conf_{nome_strumento}", disabled=blocco_multiconto):
            if blocco_multiconto:
                st.rerun()
            full_mem_t = carica_memoria(conto_t)
            full_mem_r = carica_memoria(conto_r)
            
            full_mem_t[nome_strumento] = {
                **mem_t,
                "attivo": True,
                "direzione": dir_trend,
                "stato": "FLAT",
                "tipo_strategia": "TREND",
                "timeframe": tf_scelto,
                "needs_manual_start": True,
                "msg_manuale": "",
                "storico_wip_trend": [],
                "posizioni_core": [],
                "posizioni_incr": [],
                "trailing_sl_core": None,
                "trailing_sl_incr": None
            }
            salva_memoria(conto_t, full_mem_t)
            
            full_mem_r[nome_strumento] = {
                **mem_r,
                "attivo": True,
                "direzione": dir_range,
                "tp": tp_r,
                "opp": opp_r,
                "dts": dts_r,
                "size": sz_r,
                "stato": "IN_ATTESA",
                "tipo_strategia": "RANGE",
                "storico_wip": [],
                "errore_avvio": False,
                "errore_ripristino": False,
                "comando_manuale": False,
                "msg_manuale": ""
            }
            salva_memoria(conto_r, full_mem_r)
            
            st.session_state[f"sync_trend_open_{nome_strumento}"] = False
            st.rerun()
    with c_btn2:
        if st.button("❌ ANNULLA", use_container_width=True, key=f"synct_annulla_{nome_strumento}"):
            st.session_state[f"sync_trend_open_{nome_strumento}"] = False
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
            flex-direction: column !important;
            justify-content: center !important;
            align-items: stretch !important;
            padding: 6px 10px !important;
            border-radius: 8px !important;
            min-height: 48px !important;
            height: auto !important;
            margin-bottom: 6px !important;
            white-space: normal !important;
            width: 100% !important;
        }
        section[data-testid="stSidebar"] div[data-testid="stButton"] div[data-testid="stMarkdownContainer"] {
            width: 100% !important;
            display: flex !important;
            flex-direction: column !important;
            gap: 2px !important;
        }
        section[data-testid="stSidebar"] div[data-testid="stButton"] > button p {
            display: flex !important;
            justify-content: flex-start !important;
            align-items: center !important;
            width: 100% !important;
            margin: 0 !important;
            line-height: 1.25 !important;
            white-space: nowrap !important;
            gap: 4px !important;
        }
        section[data-testid="stSidebar"] div[data-testid="stButton"] > button p:first-child {
            font-size: 0.74rem !important;
            font-weight: 700 !important;
        }
        section[data-testid="stSidebar"] div[data-testid="stButton"] > button p:nth-child(2) {
            font-size: 0.68rem !important;
            font-weight: 500 !important;
            color: #bbb !important;
        }
        section[data-testid="stSidebar"] div[data-testid="stButton"] > button p:first-child > span:last-child,
        section[data-testid="stSidebar"] div[data-testid="stButton"] span[style*="color: rgb(255, 171, 0)"],
        section[data-testid="stSidebar"] div[data-testid="stButton"] span[style*="color:rgb(255, 171, 0)"],
        section[data-testid="stSidebar"] div[data-testid="stButton"] span[style*="orange"] {
            color: #FFD700 !important;
            font-weight: 700 !important;
            margin-left: auto !important;
            text-align: right !important;
            white-space: nowrap !important;
        }
        section[data-testid="stSidebar"] div[data-testid="stButton"] > button[kind="primary"] {
            box-shadow: 0 2px 8px rgba(25, 135, 84, 0.4) !important;
        }
        @media (min-width: 769px) {
            section[data-testid="stSidebar"] { min-width: 240px !important; max-width: 240px !important; }
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
        .ig-table { width: 90%; max-width: 1400px; margin: 0 auto; border-collapse: collapse; font-family: -apple-system, BlinkMacSystemFont, sans-serif; font-size: 0.77rem; color: #d1d4dc; margin-bottom: 20px; }
        .ig-table th { text-align: center; color: white; padding: 10px 8px; border-bottom: 1px solid rgba(255,255,255,0.1); font-weight: 600; font-size: 0.68rem; text-transform: uppercase; }
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
        .ig-subrow td { color: #aaa; font-size: 0.72rem; border-bottom: none; padding: 6px 8px; font-weight: normal !important; text-decoration: none !important; }
        .ig-subrow td.pnl-pos { color: #3b82f6 !important; font-weight: bold !important; }
        .ig-subrow td.pnl-neg { color: #ef4444 !important; font-weight: bold !important; }

        .size-buy { color: #3b82f6; }
        .size-sell { color: #ef4444; }
        .size-trend { color: #FF8C00 !important; }
        .ig-row .size-buy, .ig-row .size-sell, .ig-row .size-trend { font-weight: normal; text-align: center !important; }
        
        /* Modifica per far ereditare correttamente il colore della size nei subrows */
        .ig-subrow td.size-buy { color: #3b82f6 !important; font-weight: normal !important; }
        .ig-subrow td.size-sell { color: #ef4444 !important; font-weight: normal !important; }
        .ig-subrow td.size-trend { color: #FF8C00 !important; font-weight: normal !important; }

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
            .ig-table { width: 100% !important; font-size: 0.74rem !important; }
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
                font-size: 0.68rem !important;
                margin-bottom: 10px !important;
            }
            .ig-table th, .ig-table td {
                padding: 5px 3px !important;
                font-size: 0.65rem !important;
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
    tmp_path = f"{path}.tmp.{os.getpid()}"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(dati, f, indent=4)
        os.replace(tmp_path, path)
    except Exception:
        with open(path, "w", encoding="utf-8") as f:
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
    tmp_path = f"{path}.tmp.{os.getpid()}"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(prefs, f, indent=4)
        os.replace(tmp_path, path)
    except Exception:
        pass

def carica_ultimo_utente():
    path = "ultimo_utente.json"
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f).get("ultimo_utente", "Fiordok")
        except Exception:
            return "Fiordok"
    return "Fiordok"

def salva_ultimo_utente(username):
    try:
        with open("ultimo_utente.json", "w", encoding="utf-8") as f:
            json.dump({"ultimo_utente": username}, f)
    except Exception:
        pass

def calcola_kj55_da_candele_dash(candele_list, periods=55):
    if not candele_list:
        return None
    recent = candele_list[-periods:] if len(candele_list) >= periods else candele_list
    valid = []
    for c in recent:
        h = c.get('highPrice', {}).get('bid') or c.get('highPrice', {}).get('ask') or c.get('high')
        l = c.get('lowPrice', {}).get('bid') or c.get('lowPrice', {}).get('ask') or c.get('low')
        if h is not None and l is not None:
            try:
                vh, vl = float(h), float(l)
                if 0 < vh < 1e8 and 0 < vl < 1e8:
                    valid.append((vh, vl))
            except (ValueError, TypeError):
                pass
    if not valid or len(valid) < periods:
        return None
    highest = max(v[0] for v in valid)
    lowest = min(v[1] for v in valid)
    return (highest + lowest) / 2.0

def is_valid_candele_dash(data, tf=None):
    if not data or len(data) < 2:
        return False
    try:
        highs = [float(c.get('highPrice', {}).get('bid', c.get('high', 0))) for c in data if c.get('highPrice', {}).get('bid') or c.get('high')]
        lows = [float(c.get('lowPrice', {}).get('bid', c.get('low', 0))) for c in data if c.get('lowPrice', {}).get('bid') or c.get('low')]
        if not highs or not lows:
            return False
        if (max(highs) - min(lows)) <= 1e-6:
            return False
            
        tf_mins = {'MINUTE_5': 5, 'MINUTE_15': 15, 'HOUR': 60, 'HOUR_4': 240, 'DAY': 1440}
        if tf and tf in tf_mins:
            expected_min = tf_mins[tf]
            times = []
            for c in data[:10]:
                st_str = c.get('snapshotTime')
                if st_str:
                    for fmt in ("%Y/%m/%d %H:%M:%S", "%Y/%m/%d %H:%M:00", "%Y-%m-%d %H:%M:%S"):
                        try:
                            times.append(datetime.strptime(st_str, fmt))
                            break
                        except Exception:
                            pass
            if len(times) >= 2:
                delta_m = round((times[1] - times[0]).total_seconds() / 60.0)
                if expected_min <= 15 and delta_m >= 30:
                    return False
                if expected_min == 60 and (delta_m < 30 or delta_m > 120):
                    return False
                if expected_min >= 1440 and delta_m < 720:
                    return False
        return True
    except Exception:
        return False

def aggrega_candele_dash(candele_src, tf_src, tf_dest):
    tf_mins = {'MINUTE_5': 5, 'MINUTE_15': 15, 'HOUR': 60, 'HOUR_4': 240, 'DAY': 1440}
    m_src = tf_mins.get(tf_src, 5)
    m_dest = tf_mins.get(tf_dest, 60)
    if m_dest <= m_src:
        return []
    groups = {}
    for c in candele_src:
        st_str = c.get("snapshotTime")
        if not st_str:
            continue
        dt = None
        for fmt in ("%Y/%m/%d %H:%M:%S", "%Y/%m/%d %H:%M:00", "%Y-%m-%d %H:%M:%S"):
            try:
                dt = datetime.strptime(st_str, fmt)
                break
            except Exception:
                pass
        if not dt:
            continue
        offset = 60 if m_dest in (60, 240, 1440) else 0
        min_tot = dt.hour * 60 + dt.minute
        boundary_min = ((min_tot - offset) // m_dest) * m_dest + offset
        base_dt = dt.replace(hour=0, minute=0, second=0, microsecond=0)
        target_dt = base_dt + timedelta(minutes=boundary_min)
        target_snap = target_dt.strftime("%Y/%m/%d %H:%M:00")
        
        if target_snap not in groups:
            groups[target_snap] = []
        groups[target_snap].append(c)

    res = []
    for snap_key in sorted(groups.keys()):
        chunk = groups[snap_key]
        try:
            o_bid = float(chunk[0].get('openPrice', {}).get('bid', chunk[0].get('open', 0)))
            h_bid = max(float(c.get('highPrice', {}).get('bid', c.get('high', 0))) for c in chunk)
            l_bid = min(float(c.get('lowPrice', {}).get('bid', c.get('low', 0))) for c in chunk)
            c_bid = float(chunk[-1].get('closePrice', {}).get('bid', chunk[-1].get('close', 0)))
            res.append({
                "snapshotTime": snap_key,
                "openPrice": {"bid": o_bid, "ask": o_bid, "lastTraded": None},
                "highPrice": {"bid": h_bid, "ask": h_bid, "lastTraded": None},
                "lowPrice": {"bid": l_bid, "ask": l_bid, "lastTraded": None},
                "closePrice": {"bid": c_bid, "ask": c_bid, "lastTraded": None}
            })
        except Exception:
            pass
    return res

def allinea_candele_live_dash(candele_locali, nome, tf, px_live):
    if not candele_locali or not px_live or not isinstance(px_live, (int, float)):
        return candele_locali
    now_t = now_it()
    ora_dt = now_t.time()
    wd = now_t.weekday()
    if (wd == 4 and ora_dt >= time(23, 0)) or wd == 5 or (wd == 6 and ora_dt < time(21, 45)):
        return candele_locali
        
    tf_mins = {'MINUTE_5': 5, 'MINUTE_15': 15, 'HOUR': 60, 'HOUR_4': 240, 'DAY': 1440}
    min_tf = tf_mins.get(tf, 5)
    offset = 60 if min_tf in (60, 240, 1440) else 0
    min_tot = now_t.hour * 60 + now_t.minute
    boundary_min = ((min_tot - offset) // min_tf) * min_tf + offset
    base_dt = now_t.replace(hour=0, minute=0, second=0, microsecond=0)
    target_dt = base_dt + timedelta(minutes=boundary_min)
    
    try:
        last_t_str = candele_locali[-1].get("snapshotTime")
        last_dt = datetime.strptime(last_t_str, "%Y/%m/%d %H:%M:%S").replace(tzinfo=TZ_ITALIA)
    except Exception:
        return candele_locali

    if last_dt >= target_dt:
        return candele_locali
        
    snap_synth = target_dt.strftime("%Y/%m/%d %H:%M:00")
    last_c = candele_locali[-1]
    try:
        prev_close = (float(last_c.get('closePrice',{}).get('bid', px_live)) + float(last_c.get('closePrice',{}).get('ask', px_live))) / 2
    except Exception:
        prev_close = px_live
        
    synth_candle = {
        "snapshotTime": snap_synth,
        "openPrice": {"bid": prev_close, "ask": prev_close, "lastTraded": None},
        "highPrice": {"bid": max(prev_close, px_live), "ask": max(prev_close, px_live), "lastTraded": None},
        "lowPrice": {"bid": min(prev_close, px_live), "ask": min(prev_close, px_live), "lastTraded": None},
        "closePrice": {"bid": px_live, "ask": px_live, "lastTraded": None}
    }
    candele_locali.append(synth_candle)
    return candele_locali[-100:]

def carica_candele_locali_dash(conto, nome, tf, px_live=None):
    clean = nome.replace("/", "_").replace(" ", "_")
    fname = f"candele_{clean}_{tf}.json"
    candidates = [
        os.path.join(conto, fname) if conto else fname,
        fname,
        os.path.join("..", conto, fname) if conto else fname
    ]
    for altro in ["DANY_DEMO", "FIORDOK_DEMO", "BONGIOLO_DEMO"]:
        candidates.append(os.path.join(altro, fname))
        candidates.append(os.path.join("..", altro, fname))
        
    for p in candidates:
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    d = json.load(f)
                    if len(d) >= 55 and is_valid_candele_dash(d, tf):
                        if px_live and isinstance(px_live, (int, float)):
                            return allinea_candele_live_dash(d, nome, tf, px_live)
                        return d
            except Exception:
                pass
                

    tf_order = ["MINUTE_5", "MINUTE_15", "HOUR", "HOUR_4", "DAY"]
    tf_mins = {'MINUTE_5': 5, 'MINUTE_15': 15, 'HOUR': 60, 'HOUR_4': 240, 'DAY': 1440}
    for tf_try in tf_order:
        if tf_try == tf or tf_mins.get(tf_try, 0) >= tf_mins.get(tf, 0):
            continue
        fname_alt = f"candele_{clean}_{tf_try}.json"
        for altro in ["DANY_DEMO", "FIORDOK_DEMO", "BONGIOLO_DEMO", "."]:
            p_alt = os.path.join(altro, fname_alt) if altro != "." else fname_alt
            if os.path.exists(p_alt):
                try:
                    with open(p_alt, "r", encoding="utf-8") as f:
                        d = json.load(f)
                        if is_valid_candele_dash(d, tf_try):
                            c_agg = aggrega_candele_dash(d, tf_try, tf)
                            if is_valid_candele_dash(c_agg, tf):
                                if px_live and isinstance(px_live, (int, float)):
                                    return allinea_candele_live_dash(c_agg, nome, tf, px_live)
                                return c_agg
                except Exception:
                    pass
                    
    if px_live and isinstance(px_live, (int, float)):
        return [{"highPrice": {"bid": px_live, "ask": px_live}, "lowPrice": {"bid": px_live, "ask": px_live}}]
    return []

def renderizza_schermata_radar(conto_selezionato=None):
    @st.fragment(run_every=15)
    def renderizza_radar_body():
        radar_data = {}
        ts_aggiornamento = None
        prezzi_live = {}
        
        accs = get_accounts()
        if conto_selezionato and conto_selezionato not in accs:
            accs = [conto_selezionato] + accs
            
        for c_dir in accs:
            r_file = os.path.join(c_dir, "radar_trend.json")
            if os.path.exists(r_file):
                try:
                    with open(r_file, "r", encoding="utf-8") as f_rf:
                        rf_d = json.load(f_rf)
                        d_r = rf_d.get("radar_trend", {})
                        ts_r = rf_d.get("radar_trend_ts")
                        if d_r:
                            radar_data.update(d_r)
                            if not ts_aggiornamento or (ts_r and ts_r > ts_aggiornamento):
                                ts_aggiornamento = ts_r
                except Exception:
                    pass
            st_file = os.path.join(c_dir, STATO_SISTEMA)
            if os.path.exists(st_file):
                try:
                    with open(st_file, "r", encoding="utf-8") as f_st:
                        st_d = json.load(f_st)
                        pl = st_d.get("prezzi_live", {})
                        if pl:
                            prezzi_live.update(pl)
                except Exception:
                    pass
                    
        if not ts_aggiornamento:
            ts_aggiornamento = now_it().strftime("%d/%m/%Y %H:%M:%S")

        col_radar_info, col_radar_btn = st.columns([5, 1.2])
        with col_radar_info:
            st.html(f"""
            <h2 style='color: #FFD700; margin-top: -15px; margin-bottom: 2px; font-size: 1.35rem; font-weight: bold;'>📡 Radar Trend Multi-Timeframe (KJ55)</h2>
            <div style='color: #aaa; font-size: 0.78rem; margin-top: -2px; margin-bottom: 8px;'>Scanner di prossimità a <b>0 chiamate API</b> su Kijun 55 periodi (M5, H1, H4, D1). Ultimo aggiornamento: <b style='color: #FFD700; font-size: 0.90rem; margin-left: 3px;'>{ts_aggiornamento}</b></div>
            <div style='display: flex; gap: 14px; flex-wrap: wrap; margin-bottom: 10px; font-size: 0.76rem;'>
                <div style='display: flex; align-items: center; gap: 5px;'><span style='display: inline-block; width: 10px; height: 10px; border-radius: 50%; background: #22c55e;'></span> <b>Zona Calda (≤ 15 punti)</b>: Possibile ingresso imminente</div>
                <div style='display: flex; align-items: center; gap: 5px;'><span style='display: inline-block; width: 10px; height: 10px; border-radius: 50%; background: #64748b;'></span> <b>Lontano (> 15 punti)</b>: Monitoraggio continuo</div>
                <div style='display: flex; align-items: center; gap: 5px;'><span style='display: inline-block; width: 10px; height: 10px; border-radius: 50%; background: #3b82f6;'></span> <b>In Trend</b>: Posizione già a mercato</div>
            </div>
            """)
        with col_radar_btn:
            st.markdown("""
            <style>
            div.st-key-btn_radar_nav_trend button {
                background: linear-gradient(135deg, #1e3a8a 0%, #2563eb 100%) !important;
                color: #ffffff !important;
                border: 1px solid #60a5fa !important;
                font-weight: bold !important;
                font-size: 0.85rem !important;
                border-radius: 6px !important;
                padding: 6px 14px !important;
                margin-top: 10px !important;
                box-shadow: 0 2px 10px rgba(37, 99, 235, 0.35) !important;
                transition: all 0.2s ease-in-out !important;
            }
            div.st-key-btn_radar_nav_trend button:hover {
                background: linear-gradient(135deg, #2563eb 0%, #3b82f6 100%) !important;
                border-color: #93c5fd !important;
                box-shadow: 0 4px 16px rgba(59, 130, 246, 0.6) !important;
                transform: translateY(-1px);
            }
            </style>
            """, unsafe_allow_html=True)
            if st.button("📈 TREND", key="btn_radar_nav_trend", use_container_width=True):
                st.session_state.vista_sidebar = "CONTO"
                st.session_state.target_tab = "Trend"
                st.rerun()

        tutti_strumenti = ["AUD/NZD", "CAD/JPY", "EUR/USD", "GBP/JPY", "GBP/USD", "USD/CAD", "USD/CHF", "USD/JPY", "Spot Gold", "US 500 Cash"]
        tf_map_code = {"M5": "MINUTE_5", "H1": "HOUR", "H4": "HOUR_4", "D1": "DAY"}
        
        html_table = """
        <table style='width: 100%; border-collapse: collapse; background: #0f172a; border-radius: 6px; overflow: hidden; font-family: -apple-system, BlinkMacSystemFont, sans-serif; font-size: 0.75rem;'>
            <thead>
                <tr style='background: #1e293b; color: #cbd5e1; text-align: center; border-bottom: 2px solid #334155;'>
                    <th style='padding: 6px 8px; text-align: center; font-size: 0.74rem; text-transform: uppercase;'>Strumento</th>
                    <th style='padding: 6px 8px; font-size: 0.74rem; text-transform: uppercase;'>Live</th>
                    <th style='padding: 6px 8px; font-size: 0.74rem; text-transform: uppercase;'>M5</th>
                    <th style='padding: 6px 8px; font-size: 0.74rem; text-transform: uppercase;'>H1</th>
                    <th style='padding: 6px 8px; font-size: 0.74rem; text-transform: uppercase;'>H4</th>
                    <th style='padding: 6px 8px; font-size: 0.74rem; text-transform: uppercase;'>D1</th>
                    <th style='padding: 6px 8px; font-size: 0.74rem; text-transform: uppercase;'>Stato Trend</th>
                </tr>
            </thead>
            <tbody>
        """
        
        for idx, s_nome in enumerate(tutti_strumenti):
            cfg_s = CONFIG_STRUMENTI.get(s_nome, {})
            dec = cfg_s.get("decimali", 2)
            mult = cfg_s.get("moltiplicatore", 0.0001)
            px = prezzi_live.get(s_nome)
            
            info_r = radar_data.get(s_nome, {})
            tf_dict = info_r.get("timeframes", {})
            
            # Raccogli tutti i trade attivi per questo strumento su tutti i conti/timeframe
            trades_tf = {}
            
            check_dirs = [conto_selezionato] + [d for d in accs if d != conto_selezionato] if conto_selezionato else accs
            for c_dir in check_dirs:
                if not c_dir: continue
                mem_c = carica_memoria(c_dir)
                mem_s = mem_c.get(s_nome, {})
                if mem_s.get("attivo", False) and mem_s.get("stato") in ("LONG", "SHORT"):
                    tf_a = mem_s.get("timeframe", "HOUR")
                    tf_lbl = "M5" if "MINUTE_5" in tf_a else ("H1" if "HOUR" in tf_a and "HOUR_4" not in tf_a else ("H4" if "HOUR_4" in tf_a else "D1"))
                    if tf_lbl not in trades_tf:
                        pos_c = mem_s.get("posizioni_core", [])
                        pos_i = mem_s.get("posizioni_incr", [])
                        tot_pnl_pts = 0.0
                        has_pos = False
                        
                        if px and isinstance(px, (int, float)):
                            for pc in pos_c:
                                e_px = pc.get("entry")
                                sz = pc.get("size", 1)
                                d_pos = pc.get("direction", mem_s.get("stato"))
                                if e_px and isinstance(e_px, (int, float)) and e_px > 0:
                                    has_pos = True
                                    diff = (px - e_px) if d_pos == "LONG" else (e_px - px)
                                    tot_pnl_pts += (diff / mult) * sz
                            for pi in pos_i:
                                e_px = pi.get("entry")
                                sz = pi.get("size", 1)
                                d_pos = pi.get("direction", mem_s.get("stato"))
                                if e_px and isinstance(e_px, (int, float)) and e_px > 0:
                                    has_pos = True
                                    diff = (px - e_px) if d_pos == "LONG" else (e_px - px)
                                    tot_pnl_pts += (diff / mult) * sz
                        
                        is_profit = (tot_pnl_pts >= 0) if has_pos else True
                        
                        trades_tf[tf_lbl] = {
                            "stato": mem_s.get("stato"),
                            "conto": c_dir.replace("_DEMO", "").replace("_REALE", ""),
                            "is_profit": is_profit,
                            "pnl_pts": tot_pnl_pts
                        }
            
            if trades_tf:
                pills = []
                for tf_k in ["M5", "H1", "H4", "D1"]:
                    if tf_k in trades_tf:
                        t_info = trades_tf[tf_k]
                        st_dir = t_info["stato"]
                        ct_name = t_info["conto"]
                        is_profit = t_info.get("is_profit", True)
                        pnl_pts = t_info.get("pnl_pts", 0.0)
                        pnl_sign = f"+{pnl_pts:.0f}" if pnl_pts > 0 else f"{pnl_pts:.0f}"
                        
                        col_bg = "rgba(34, 197, 94, 0.2)" if is_profit else "rgba(239, 68, 68, 0.2)"
                        col_bdr = "#22c55e" if is_profit else "#ef4444"
                        col_txt = "#4ade80" if is_profit else "#f87171"
                        icon_d = "🟢" if is_profit else "🔴"
                        tag_d = "L" if st_dir == "LONG" else "S"
                        pills.append(f"<span style='background: {col_bg}; color: {col_txt}; border: 1px solid {col_bdr}; border-radius: 3px; padding: 1px 4px; font-weight: bold; font-size: 0.68rem; white-space: nowrap;' title='Conto: {ct_name} ({st_dir}) | PnL: {pnl_sign} pt'>{icon_d} {tf_k} ({tag_d})</span>")
                badge_stato = f"<div style='display: flex; gap: 3px; justify-content: center; flex-wrap: nowrap;'>{''.join(pills)}</div>"
            else:
                badge_stato = "<span style='background: rgba(148, 163, 184, 0.15); color: #94a3b8; border-radius: 3px; padding: 2px 5px; font-size: 0.70rem;'>⏳ FLAT</span>"
            
            px_str = f"<b>{px:.{dec}f}</b>" if (px and isinstance(px, (int, float))) else "<span style='color:#64748b;'>-</span>"
            
            def format_radar_cell(lbl_key):
                t_data = tf_dict.get(lbl_key, {})
                kj_v = t_data.get("kj")
                dist_p = t_data.get("dist_pips")
                dir_p = t_data.get("dir", "-")
                vicino = t_data.get("vicino", False)
                
                if kj_v is None and px and isinstance(px, (int, float)):
                    tf_code = tf_map_code.get(lbl_key, "HOUR")
                    candele_c = carica_candele_locali_dash(conto_selezionato or "FIORDOK_DEMO", s_nome, tf_code, px_live=px)
                    kj_c = calcola_kj55_da_candele_dash(candele_c, 55)
                    if kj_c is not None:
                        kj_v = kj_c
                        diff_pts = px - kj_v
                        dist_p = round(abs(diff_pts) / mult)
                        dir_p = "Possibile Entrata"
                        vicino = (dist_p <= 15)

                is_current_tf_trade = (lbl_key in trades_tf)
                
                if is_current_tf_trade:
                    t_info = trades_tf[lbl_key]
                    st_val = t_info["stato"]
                    ct_val = t_info["conto"]
                    is_profit = t_info.get("is_profit", True)
                    pnl_pts = t_info.get("pnl_pts", 0.0)
                    col_dir_tr = "#4ade80" if is_profit else "#f87171"
                    icon_dir = "🟢" if is_profit else "🔴"
                    pnl_sign = f"+{pnl_pts:.0f}" if pnl_pts > 0 else f"{pnl_pts:.0f}"
                    title_tip = f"Conto: {ct_val} ({st_val}) | PnL: {pnl_sign} pt"
                    kj_line = f"<span style='font-size:0.60rem; color:#FFFF00; font-weight:500;'>KJ: {kj_v:.{dec}f}</span>" if (kj_v is not None) else "<span style='font-size:0.60rem; color:#64748b;'>-</span>"
                    return f"<div style='background: rgba(59, 130, 246, 0.2); border: 2px solid #3b82f6; border-radius: 4px; padding: 2px 4px; text-align: center; line-height: 1.15;' title='{title_tip}'><b style='color: #60a5fa; font-size: 0.70rem;'>IN TREND</b><br><span style='font-size:0.66rem; color:{col_dir_tr}; font-weight:bold;'>{icon_dir} {st_val}</span><br>{kj_line}</div>"

                if kj_v is None or dist_p is None:
                    return "<div style='color: #64748b; text-align: center; font-size: 0.75rem;'>-</div>"
                    
                kj_formatted = f"{kj_v:.{dec}f}"
                dist_int = int(round(dist_p))
                dir_label = "Possibile Entrata"
                col_gold = "#fbbf24" # Giallo oro
                
                if vicino:
                    bg_cell = "rgba(251, 191, 36, 0.2)"
                    bdr_cell = "#f59e0b"
                    return f"<div style='background: {bg_cell}; border: 1px solid {bdr_cell}; border-radius: 4px; padding: 2px 4px; text-align: center; line-height: 1.15;'><b style='color: {col_gold}; font-size: 0.64rem;'>⚡ {dist_int} punti</b><br><span style='font-size:0.64rem; color:{col_gold}; font-weight:bold;'>{dir_label}</span><br><span style='font-size:0.60rem; color:#FFFF00; font-weight:500;'>KJ: {kj_formatted}</span></div>"
                else:
                    return f"<div style='text-align: center; color: #94a3b8; line-height: 1.15;'><span style='font-weight: bold; font-size: 0.64rem;'>{dist_int} punti</span><br><span style='font-size:0.64rem; color:{col_gold};'>{dir_label}</span><br><span style='font-size:0.60rem; color:#FFFF00; font-weight:500;'>KJ: {kj_formatted}</span></div>"

            c_m5 = format_radar_cell("M5")
            c_h1 = format_radar_cell("H1")
            c_h4 = format_radar_cell("H4")
            c_d1 = format_radar_cell("D1")
            
            bg_row = "#1e293b" if idx % 2 == 1 else "#0f172a"
            html_table += f"""
            <tr style='background: {bg_row}; border-bottom: 1px solid rgba(255,255,255,0.05);'>
                <td style='padding: 3px 8px; font-weight: bold; font-size: 0.76rem;'>{formatta_mercato_con_bandiere(s_nome)}</td>
                <td style='padding: 3px 6px; text-align: center; color: #00E676; font-size: 0.76rem;'>{px_str}</td>
                <td style='padding: 2px 4px;'>{c_m5}</td>
                <td style='padding: 2px 4px;'>{c_h1}</td>
                <td style='padding: 2px 4px;'>{c_h4}</td>
                <td style='padding: 2px 4px;'>{c_d1}</td>
                <td style='padding: 3px 6px; text-align: center;'>{badge_stato}</td>
            </tr>
            """
        
        html_table += "</tbody></table>"
        st.html(html_table)
        
    renderizza_radar_body()

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
                    salva_ultimo_utente(st.session_state.user)
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
        ultimo_acc = carica_ultimo_utente()
        with st.form("login_form"):
            user = st.text_input("Account", value=ultimo_acc)
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
                        salva_ultimo_utente(user)
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
            
            def get_tempo_connessione(acc, st_acc):
                motore_attivo = False
                path_stato = os.path.join(acc, STATO_SISTEMA)
                if os.path.exists(path_stato) and (time.time() - os.path.getmtime(path_stato)) < 60:
                    motore_attivo = True

                durata_str = "--"
                path_token = os.path.join(acc, FILE_TOKEN)
                if motore_attivo and os.path.exists(path_token):
                    try:
                        durata_sec = time.time() - os.path.getmtime(path_token)
                        ore = int(durata_sec // 3600)
                        minuti = int((durata_sec % 3600) // 60)
                        durata_str = f"{ore}h {minuti}m"
                    except Exception:
                        durata_str = st_acc.get("durata_sessione", "--")
                elif motore_attivo:
                    durata_str = st_acc.get("durata_sessione", "--")

                if motore_attivo:
                    return f"🟢 Connesso: {durata_str}"
                else:
                    return "🔴 Offline"

            def get_stato_salute(acc):
                path_memoria = os.path.join(acc, FILE_MEMORIA)
                if not os.path.exists(path_memoria): return "⚪"
                try:
                    with open(path_memoria, "r", encoding="utf-8") as f:
                        memoria = json.load(f)
                    has_yellow = False
                    for strum, dati in memoria.items():
                        stato = dati.get("stato", "")
                        # L'emergenza scatta se c'è un errore di avvio/ripristino esplicito
                        emergenza = (stato == "MANUALE" and (dati.get("errore_ripristino") or dati.get("errore_avvio")))
                        
                        # L'emergenza scatta anche se il motore si è autosospeso in corsa (attivo = False + msg_manuale di emergenza)
                        msg = dati.get("msg_manuale", "")
                        if dati.get("attivo") is False and msg and ("🆘" in msg or "Emergenza" in msg or "Fallita" in msg or "Rifiuto" in msg or "Fallito" in msg):
                            emergenza = True
                            
                        if emergenza: return "🔴"
                        if dati.get("alert_falso_allarme"): has_yellow = True
                    return "🟡" if has_yellow else "🟢"
                except:
                    return "🟢"

            vista_side = st.session_state.get("vista_sidebar", "CONTO")
            if conti_reali:
                st.markdown("<p style='font-size: 0.78rem; font-weight: 700; color: #ff4b4b; margin: 8px 0 4px 0; letter-spacing: 0.8px;'>🔴 CONTI REALI</p>", unsafe_allow_html=True)
                for cr in conti_reali:
                    nome_cr_clean = cr.replace("_REALE", "")
                    st_cr = leggi_stato_sistema(cr)
                    cap_cr = formatta_eur(st_cr.get('saldo', '0'))
                    is_sel = (cr == conto_attivo and vista_side == "CONTO")
                    tempo_conn = get_tempo_connessione(cr, st_cr)
                    salute = get_stato_salute(cr)
                    label_cr = f"🔴 {nome_cr_clean} :orange[{cap_cr} €]\n\n{tempo_conn} {salute}"
                    if st.button(label_cr, key=f"side_acc_{cr}", type="primary" if is_sel else "secondary", use_container_width=True):
                        st.session_state.conto_selezionato = cr
                        st.session_state.vista_sidebar = "CONTO"
                        st.rerun()
                st.markdown("<div style='margin: 4px 0;'></div>", unsafe_allow_html=True)
                
            if conti_demo:
                st.markdown("<p style='font-size: 0.78rem; font-weight: 700; color: #1E88E5; margin: 8px 0 4px 0; letter-spacing: 0.8px;'>🔵 CONTI DEMO</p>", unsafe_allow_html=True)
                for cd in conti_demo:
                    nome_cd_clean = cd.replace("_DEMO", "")
                    st_cd = leggi_stato_sistema(cd)
                    cap_cd = formatta_eur(st_cd.get('saldo', '0'))
                    is_sel = (cd == conto_attivo and vista_side == "CONTO")
                    tempo_conn = get_tempo_connessione(cd, st_cd)
                    salute = get_stato_salute(cd)
                    label_cd = f"🔵 {nome_cd_clean} :orange[{cap_cd} €]\n\n{tempo_conn} {salute}"
                    if st.button(label_cd, key=f"side_acc_{cd}", type="primary" if is_sel else "secondary", use_container_width=True):
                        st.session_state.conto_selezionato = cd
                        st.session_state.vista_sidebar = "CONTO"
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

            val_capitale = formatta_eur(stato_side.get('saldo', '0'))
            val_margine = formatta_eur(stato_side.get('margine', '0'))
            val_residuo = formatta_eur(stato_side.get('disponibile', '0'))
            val_dd = formatta_eur(stato_side.get('drawdown', '0'))
            
            try:
                dd_num = float(stato_side.get('drawdown', '0'))
                col_dd = "#ef4444" if dd_num < 0 else ("#09ab3b" if dd_num > 0 else "inherit")
            except:
                col_dd = "inherit"
            
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
            
            st.markdown("""
                <style>
                div.st-key-btn_radar_sidebar {
                    display: flex !important;
                    justify-content: center !important;
                    align-items: center !important;
                    width: 100% !important;
                    margin: 0 auto !important;
                }
                div.st-key-btn_radar_sidebar button {
                    background-color: #000000 !important;
                    border: 2px solid #FFD700 !important;
                    border-radius: 8px !important;
                    padding: 12px 6px !important;
                    min-height: 54px !important;
                    width: 100% !important;
                    display: flex !important;
                    justify-content: center !important;
                    align-items: center !important;
                    text-align: center !important;
                    box-shadow: 0 0 16px rgba(255, 215, 0, 0.4) !important;
                    transition: all 0.2s ease-in-out !important;
                }
                div.st-key-btn_radar_sidebar button div[data-testid="stMarkdownContainer"],
                div.st-key-btn_radar_sidebar button div,
                div.st-key-btn_radar_sidebar button p,
                div.st-key-btn_radar_sidebar button span {
                    display: flex !important;
                    justify-content: center !important;
                    align-items: center !important;
                    text-align: center !important;
                    color: #FFD700 !important;
                    font-size: 1.22rem !important;
                    font-weight: 900 !important;
                    letter-spacing: 1.2px !important;
                    text-transform: uppercase !important;
                    width: 100% !important;
                    margin: 0 auto !important;
                    padding: 0 !important;
                    line-height: 1.2 !important;
                }
                div.st-key-btn_radar_sidebar button:hover {
                    background-color: #1a1a00 !important;
                    border-color: #FFE55C !important;
                    box-shadow: 0 0 24px rgba(255, 215, 0, 0.65) !important;
                    transform: translateY(-1px);
                }
                div.st-key-btn_radar_sidebar button:hover div[data-testid="stMarkdownContainer"],
                div.st-key-btn_radar_sidebar button:hover div,
                div.st-key-btn_radar_sidebar button:hover p,
                div.st-key-btn_radar_sidebar button:hover span {
                    color: #FFE55C !important;
                }
                </style>
            """, unsafe_allow_html=True)
            
            st.markdown("<div style='margin-top: 15px; margin-bottom: 5px;'></div>", unsafe_allow_html=True)
            is_radar_sel = (st.session_state.get("vista_sidebar", "CONTO") == "RADAR")
            if st.button("📡 RADAR TREND", key="btn_radar_sidebar", type="primary" if is_radar_sel else "secondary", use_container_width=True):
                st.session_state.vista_sidebar = "RADAR"
                st.rerun()

        renderizza_sidebar_stats()

    if st.session_state.get("vista_sidebar", "CONTO") == "RADAR":
        renderizza_schermata_radar(conto_selezionato)
        st.stop()

    ruolo = st.session_state.get("ruolo", "VIEWER")
    is_regista = (ruolo == "REGISTA")

    st.markdown("""
        <style>
        div[data-testid="stTabs"] > div[role="tablist"] {
            gap: 5px !important;
            justify-content: flex-start !important;
        }
        div[data-testid="stTabs"] button {
            padding-left: 0.3rem !important;
            padding-right: 0.3rem !important;
            padding-top: 0.2rem !important;
            padding-bottom: 0.2rem !important;
            font-size: 0.75rem !important;
            min-width: 0 !important;
        }
        </style>
    """, unsafe_allow_html=True)

    if is_regista:
        tabs = st.tabs(["💼 Pfoglio", "📋 Sintesi Range", "📈 Sintesi Trend", "🛡️ Range", "📈 Trend", "🛑 Recovery", "📊 Stat", "📄 Report", "💻 Log", "🔐 Regia"])
        tab_portafoglio, tab_sintesi, tab_sintesi_trend, tab_operativa, tab_trend, tab_restore, tab_statistiche, tab_report, tab_console, tab_autorizzazioni = tabs
    else:
        tabs = st.tabs(["💼 Pfoglio", "📋 Sintesi Range", "📈 Sintesi Trend", "📄 Report"])
        tab_portafoglio, tab_sintesi, tab_sintesi_trend, tab_report = tabs
        tab_operativa = tab_trend = tab_restore = tab_console = tab_autorizzazioni = tab_statistiche = None

    target_tab_to_open = st.session_state.pop("target_tab", None)
    if target_tab_to_open:
        components.html(f"""
            <script>
            setTimeout(function() {{
                try {{
                    const tabs = window.parent.document.querySelectorAll('div[data-testid="stTabs"] button');
                    for (let t of tabs) {{
                        const txt = (t.innerText || t.textContent || "").trim();
                        if ("{target_tab_to_open}" === "Trend") {{
                            if (txt.includes("Trend") && !txt.includes("Sintesi")) {{
                                t.click();
                                break;
                            }}
                        }} else if (txt.includes("{target_tab_to_open}")) {{
                            t.click();
                            break;
                        }}
                    }}
                }} catch(e) {{
                    console.error("Tab switch error:", e);
                }}
            }}, 150);
            </script>
        """, height=0, width=0)

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

            # Salvataggio in sessione per validazioni incrociate
            st.session_state.live_pos_data = pos_data
            st.session_state.live_ord_data = ord_data

            epic_to_name = {v['epic']: k for k, v in CONFIG_STRUMENTI.items()}
            stato = leggi_stato_sistema(conto_selezionato)
            prezzi_live = stato.get("prezzi_live", {})
            memoria_attuale = carica_memoria(conto_selezionato)
            
            # --- HELPER: Riconoscimento Ruolo Chirurgico ---
            def get_role_pos(nome_strum, dir_pos, sz_pos, param_memoria, pos_dict):
                tipo_strategia = param_memoria.get("tipo_strategia", "RANGE")
                
                if tipo_strategia == "TREND":
                    tf_val = param_memoria.get("timeframe", "MINUTE_5")
                    tf_map = {"MINUTE_5": "M5", "MINUTE_10": "M10", "HOUR": "H1", "HOUR_4": "H4", "DAY": "D"}
                    tf_str = tf_map.get(tf_val, tf_val)
                    
                    pos_core = param_memoria.get("posizioni_core", [])
                    pos_incr = param_memoria.get("posizioni_incr", [])
                    deal_id = pos_dict.get("dealId")
                    dir_str = 'LONG' if dir_pos=='BUY' else 'SHORT'
                    
                    if deal_id and any(c.get("ticket") == deal_id for c in pos_core):
                        return f"<span style='color: #FF8C00; font-weight: bold;'>Core ({dir_str}) <span style='color: #FFD700;'>[{tf_str}]</span></span>"
                    
                    if deal_id:
                        for idx, i_d in enumerate(pos_incr):
                            if i_d.get("ticket") == deal_id:
                                return f"<span style='color: #FF8C00; font-weight: bold;'>Incremento n. {idx+1}</span>"
                    
                    # Fallback per size
                    s_c = float(param_memoria.get("size", 1))
                    if abs(sz_pos - s_c) < 0.001:
                        return f"<span style='color: #FF8C00; font-weight: bold;'>Core ({dir_str}) <span style='color: #FFD700;'>[{tf_str}]</span></span>"
                    return f"<span style='color: #FF8C00; font-weight: bold;'>Incremento</span>"
                    
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
                
                is_trend = memoria_attuale.get(nome, {}).get("tipo_strategia", "RANGE") == "TREND"
                trend_color = "#FF8C00" if is_trend else "#FFD700"
                
                sign = "+" if dir == "BUY" else "-"
                size_class = "size-trend" if is_trend else ("size-buy" if dir == "BUY" else "size-sell")
                
                stop_str = ""
                lim_str = ""
                
                if is_trend:
                    kj_val = memoria_attuale.get(nome, {}).get("current_kj")
                    tk_val = memoria_attuale.get(nome, {}).get("current_tk")
                    
                    if kj_val is not None:
                        stop_str = f"<span style='color: #FFD700;' title='Kijun-sen (KJ)'>{formatta_numero(kj_val, dec)}</span>"
                    else:
                        stop_str = "-"
                        
                    if tk_val is not None:
                        lim_str = f"<span style='color: #00BFFF;' title='Tenkan-sen (TK)'>{formatta_numero(tk_val, dec)}</span>"
                    else:
                        lim_str = "-"
                else:
                    if len(stops) > 1: stop_str = "<span class='ig-multiplo'>Multiplo</span>"
                    elif len(stops) == 1:
                        val = list(stops)[0]
                        stop_str = formatta_numero(val, dec) if val != "NONE" else ""
                    
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

                is_trend = memoria_attuale.get(nome, {}).get("tipo_strategia", "RANGE") == "TREND"
                trend_color = "#FF8C00" if is_trend else None
                color_style = f"color: {trend_color};" if is_trend else ""
                u_style = f"border-bottom: 1px solid {trend_color}; text-decoration: none;" if is_trend else ""

                if is_first_of_instrument:
                    r_span = pos_row_counts.get(nome, 1)
                    td_mercato = f"<td rowspan='{r_span}' class='col-mercato' style='vertical-align: middle; border-right: 1px solid rgba(255,255,255,0.05);'><div style='display: flex; align-items: center;'><span class='ig-dot'></span>{formatta_mercato_con_bandiere(nome, color=trend_color)}</div></td>"
                else:
                    td_mercato = ""

                td_tipo_master = f"<td><span class='{size_class}' style='font-weight: normal; {color_style}'><u style='{u_style}'>{ruolo_master_str}</u></span></td>" if is_regista else ""
                
                html_pos += f"<tr class='ig-row ig-master-row' style='{master_style}'>{td_mercato}<td class='{size_class}' style='{color_style}'><u style='{u_style}'>{sign}{tot_size:g}</u></td><td class='{size_class}' style='{color_style}'><u style='{u_style}'>{formatta_numero(avg_entry, dec)}</u></td><td style='color: #00E676;'>{prezzo_str}</td><td>{stop_str}</td><td>{lim_str}</td>{td_tipo_master}<td class='{pnl_class}'><u>{pnl_str}</u></td></tr>\n"
                
                if has_subrows:
                    if is_trend:
                        mem_strum = memoria_attuale.get(nome, {})
                        s_core = float(mem_strum.get("size", 3))
                        core_positions = [p for p in posizioni if abs(float(p['position']['size']) - s_core) < 0.001 or any(c.get("ticket") == p['position'].get("dealId") for c in mem_strum.get("posizioni_core", []))]
                        other_positions = [p for p in posizioni if p not in core_positions]
                        other_positions.sort(key=lambda x: x['position'].get('createdDateUTC', ''))
                        posizioni_render = core_positions + other_positions
                    else:
                        core_positions = []
                        other_positions = []
                        posizioni_render = posizioni

                    for idx, p in enumerate(posizioni_render):
                        sz = float(p['position']['size'])
                        lvl = float(p['position']['level'])
                        
                        dt_utc = datetime.strptime(p['position']['createdDateUTC'], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
                        data_str = dt_utc.astimezone(TZ_ITALIA).strftime("%d/%m/%y %H:%M")
                        
                        s_str = ""
                        l_str = ""
                        
                        if is_trend:
                            l_str = "-"
                            is_core_subrow = (p in core_positions)
                            if is_core_subrow:
                                trailing_sl_core = memoria_attuale.get(nome, {}).get("trailing_sl_core")
                                kj_val = memoria_attuale.get(nome, {}).get("current_kj")
                                pip_val = c.get("moltiplicatore", 0.0001)
                                if trailing_sl_core is not None:
                                    sl_core = trailing_sl_core
                                    title_core = "Trailing SL Core (+-40 pip da Close | dist KJ >= 40 pip)"
                                elif kj_val is not None:
                                    sl_core = (kj_val - (5 * pip_val)) if dir == 'BUY' else (kj_val + (5 * pip_val))
                                    title_core = "Stop Core (KJ +- 5 pip)"
                                else:
                                    sl_core = None
                                
                                if sl_core is not None:
                                    s_str = f"<span style='color: #b0b0b0;' title='{title_core}'>{formatta_numero(sl_core, dec)}</span>"
                                else:
                                    s_str = "-"
                                tf_val = memoria_attuale.get(nome, {}).get("timeframe", "MINUTE_5")
                                tf_map = {"MINUTE_5": "M5", "MINUTE_10": "M10", "HOUR": "H1", "HOUR_4": "H4", "DAY": "D"}
                                tf_str = tf_map.get(tf_val, tf_val)
                                dir_str = 'LONG' if dir == 'BUY' else 'SHORT'
                                ruolo_child = f"<span style='color: #FF8C00; font-weight: bold;'>Core ({dir_str}) <span style='color: #FFD700;'>[{tf_str}]</span></span>"
                            else:
                                incr_idx = other_positions.index(p) + 1
                                ruolo_child = f"<span style='color: #FF8C00; font-weight: bold;'>Incremento n. {incr_idx}</span>"
                                
                                trailing_sl_incr = memoria_attuale.get(nome, {}).get("trailing_sl_incr")
                                tk_val = memoria_attuale.get(nome, {}).get("current_tk")
                                pip_val = c.get("moltiplicatore", 0.0001)
                                if trailing_sl_incr is not None:
                                    sl_display = trailing_sl_incr
                                    title_info = "Trailing SL (+-20 pip da Close | dist TK >= 20 pip)"
                                elif tk_val is not None:
                                    sl_display = (tk_val - (5 * pip_val)) if dir == 'BUY' else (tk_val + (5 * pip_val))
                                    title_info = "Stop TK (+-5 pip)"
                                else:
                                    sl_display = None
                                
                                if sl_display is not None:
                                    s_str = f"<span style='color: #b0b0b0;' title='{title_info}'>{formatta_numero(sl_display, dec)}</span>"
                                else:
                                    s_str = "-"
                        else:
                            if p['position'].get('stopLevel'): s_str = formatta_numero(p['position']['stopLevel'], dec)
                            elif p['position'].get('stopDistance'): s_str = "Stop" 
                            
                            if p['position'].get('limitLevel'): l_str = formatta_numero(p['position']['limitLevel'], dec)
                            elif p['position'].get('limitDistance'): l_str = "Limite"
                            
                            raw_ruolo = get_role_pos(nome, dir, sz, memoria_attuale.get(nome, {}), p['position'])
                            ruolo_child = raw_ruolo.replace("Add-On 1", "+1").replace("Add-On 2", "+2")
                        
                        pnl_child_eur = 0.0
                        if prezzo_attuale:
                            pts = (prezzo_attuale - lvl)/mult if dir == 'BUY' else (lvl - prezzo_attuale)/mult
                            pnl_child_eur = pts * sz * valore_punto * rate
                            
                        pnl_c_class = "pnl-pos" if pnl_child_eur >= 0 else "pnl-neg"
                        
                        is_last_subrow = (idx == len(posizioni_render) - 1)
                        subrow_style = "border-bottom: 2px solid rgba(255,255,255,0.3);" if (is_last_of_instrument and is_last_subrow) else ""
                        
                        td_tipo_child = f"<td><span class='{size_class}' style='font-weight: normal; {color_style}'><u style='{u_style}'>{ruolo_child}</u></span></td>" if is_regista else ""
                        html_pos += f"<tr class='ig-row ig-subrow' style='{subrow_style}'><td class='{size_class}' style='{color_style}'><u style='{u_style}'>{sign}{sz:g}</u></td><td class='{size_class}' style='{color_style}'><u style='{u_style}'>{formatta_numero(lvl, dec)}</u><br><span style='font-size: 0.75rem; color: #888;'>{data_str}</span></td><td></td><td>{s_str}</td><td>{l_str}</td>{td_tipo_child}<td class='{pnl_c_class}'>{pnl_child_eur:.0f} €</td></tr>\n"
            
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
                    <h3 style='margin: 0; font-size: 1.6rem;'>📋 Sintesi Trading Range</h3>
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
                
                tutti_strumenti = ["AUD/NZD", "CAD/JPY", "EUR/USD", "GBP/JPY", "GBP/USD", "USD/CAD", "USD/CHF", "USD/JPY", "Spot Gold", "US 500 Cash"]
                strumenti_ordinati = sorted(tutti_strumenti, key=lambda x: (not memoria.get(x, {}).get("attivo", False), x))
                
                for nome in strumenti_ordinati:
                    dati = memoria.get(nome, {})
                    stato = dati.get("stato", "IN_ATTESA")
                    is_attivo = dati.get("attivo", False)
                    tipo_strategia = dati.get("tipo_strategia", "RANGE")
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
                        elif stato == "FASE_2_SATELLITI":
                            pos_live = st.session_state.get("live_pos_data", [])
                            c = CONFIG_STRUMENTI.get(nome, {})
                            if c and c.get("epic"):
                                s_core = float(dati.get("size", 4))
                                s_mezzo = max(1.0, s_core / 2)
                                t_epic = c.get("epic")
                                for p in pos_live:
                                    if p['market']['epic'] == t_epic and float(p['position']['size']) == s_mezzo:
                                        p_dir = p['position']['direction']
                                        p_level = float(p['position']['level'])
                                        spia = " 🟢" if (prezzo > p_level if p_dir == "BUY" else prezzo < p_level) else " 🔴"
                                        break
                    
                    if dati.get("ticket2_active"):
                        stato_display += " [+ Ticket2]"

                    if is_attivo:
                        if tipo_strategia == "TREND":
                            stato_visivo = f"<span style='background-color: rgba(0, 191, 255, 0.15); color: #00BFFF; padding: 4px 8px; border-radius: 4px; font-weight: bold; font-size: 0.82rem;'>📈 IN TREND</span>"
                        else:
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
                    elif is_attivo and tipo_strategia == "RANGE":
                        bg_color = "#198754" # Verde
                        text_color = "white"
                    elif is_attivo and tipo_strategia == "TREND":
                        bg_color = "#00BFFF" # Azzurro
                        text_color = "white"
                    else:
                        bg_color = "#495057" # Grigio scuro
                        text_color = "white"
                        
                    if not is_attivo or stato == "IN_ATTESA":
                        html_tot_wip = "<div style='font-size: 0.71rem; color: #888; margin-top: 0px; margin-bottom: -10px; padding-left: 2px; line-height: 1.1; white-space: nowrap;'>Totale: <b style='color: #888;'>WIP</b></div>"
                    else:
                        totale_wip = 0.0
                        if storico:
                            for riga in storico:
                                match = re.search(r"\[Parziale:\s*([+-]?\d+(?:[\.,]\d+)?)\s*€\]", riga)
                                if match:
                                    totale_wip += float(match.group(1).replace(",", "."))
                        
                        segno_wip = "+" if totale_wip > 0 else ""
                        col_tot_wip = "#4ade80" if totale_wip > 0 else ("#ff6b6b" if totale_wip < 0 else "#aaa")
                        valore_tot_str = f"{segno_wip}{totale_wip:.2f} €".replace(".", ",")
                        html_tot_wip = f"<div style='font-size: 0.71rem; color: #bbb; margin-top: 0px; margin-bottom: -10px; padding-left: 2px; line-height: 1.1; white-space: nowrap;'>Totale: <b style='color: {col_tot_wip};'>{valore_tot_str}</b></div>"

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
                        st.markdown(html_tot_wip, unsafe_allow_html=True)
                        if st.button(nome, key=f"wip_{conto_selezionato}_{nome}", type="primary", use_container_width=True):
                            mostra_diario_wip(nome, storico, conto=conto_selezionato)
                    
                    c2.markdown(f"<div style='height: 32px; display: flex; align-items: center;'>{stato_visivo}</div>", unsafe_allow_html=True)
                    
                    if has_anomalia:
                        btn_label = "🚨 Visto Emergenza" if (dati.get("errore_avvio") or dati.get("errore_ripristino") or (dati.get("msg_manuale") and ("Fallit" in str(dati.get("msg_manuale")) or "Emergenza" in str(dati.get("msg_manuale")) or "Rifiuto" in str(dati.get("msg_manuale"))))) else "👁️ Visto Anomalia"
                        if c2.button(btn_label, key=f"ack_all_{conto_selezionato}_{nome}"):
                            p = carica_memoria(conto_selezionato)
                            if nome in p:
                                p[nome].pop("alert_falso_allarme", None)
                                p[nome]["errore_ripristino"] = False
                                p[nome]["errore_avvio"] = False
                                p[nome]["msg_manuale"] = ""
                                salva_memoria(conto_selezionato, p)
                                st.rerun()
                            
                    c3.markdown(f"<div style='height: 32px; display: flex; align-items: center;'><span style='display: inline-block; min-width: 80px; width: auto; white-space: nowrap; text-align: center; font-family: monospace; font-size: 1.1rem; color: #FFD700; letter-spacing: 0.5px; border: 1px solid rgba(255, 215, 0, 0.5); padding: 3px 8px; border-radius: 5px; background-color: rgba(255, 215, 0, 0.08);'>{prezzo}</span></div>", unsafe_allow_html=True)
                    ultimo_evento_raw = storico[-1] if storico else "Nessun evento registrato in questo ciclo."
                    ultimo_evento = formatta_ultimo_evento_sintesi(ultimo_evento_raw, dati, nome)
                    c4.markdown(f"<div style='font-size: 0.85rem; color: white; line-height: 1.3; display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden;'>{ultimo_evento}</div>", unsafe_allow_html=True)
                    st.markdown("<div style='margin-bottom: 12px;'></div>", unsafe_allow_html=True)
                    
        renderizza_sintesi()

    if tab_sintesi_trend is not None:
        with tab_sintesi_trend:
            @st.fragment(run_every=15)
            def renderizza_sintesi_trend():
                memoria = carica_memoria(conto_selezionato)
                stato_sys = leggi_stato_sistema(conto_selezionato)
                prezzi_live = stato_sys.get("prezzi_live", {})
                
                tutti_strumenti = ["AUD/NZD", "CAD/JPY", "EUR/USD", "GBP/JPY", "GBP/USD", "USD/CAD", "USD/CHF", "USD/JPY", "Spot Gold", "US 500 Cash"]
                strumenti_ordinati = sorted(tutti_strumenti, key=lambda x: (not memoria.get(x, {}).get("attivo", False), x))
                
                st.html("""
                <div style='display: flex; flex-wrap: wrap; justify-content: space-between; align-items: flex-end; gap: 10px; margin-top: -15px; margin-bottom: 20px;'>
                    <div><h3 style='margin: 0; font-size: 1.6rem;'>📈 Sintesi Trend</h3></div>
                </div>
                """)
                
                with st.container(border=True):
                    c1, c2, c3, c4 = st.columns([1.5, 3.5, 1.8, 3.2])
                    c1.markdown("<div style='color: #888; font-size: 0.85rem; font-weight: 700; text-transform: uppercase; margin-top: 5px; margin-bottom: -5px;'>Strumento</div>", unsafe_allow_html=True)
                    c2.markdown("<div style='color: #888; font-size: 0.85rem; font-weight: 700; text-transform: uppercase; margin-top: 5px; margin-bottom: -5px;'>Stato Trend</div>", unsafe_allow_html=True)
                    c3.markdown("<div style='color: #888; font-size: 0.85rem; font-weight: 700; text-transform: uppercase; margin-top: 5px; margin-bottom: -5px;'>LIVE</div>", unsafe_allow_html=True)
                    c4.markdown("<div style='color: #888; font-size: 0.85rem; font-weight: 700; text-transform: uppercase; margin-top: 5px; margin-bottom: -5px;'>Ultimo Evento</div>", unsafe_allow_html=True)
                    st.markdown("<hr style='margin-top: 15px; margin-bottom: 15px; border-top: 1px solid rgba(255, 255, 255, 0.1);'>", unsafe_allow_html=True)
                    
                    for nome in strumenti_ordinati:
                        dati = memoria.get(nome, {})
                        stato = dati.get("stato", "FLAT")
                        is_attivo = dati.get("attivo", False)
                        dir_t = dati.get("direzione", "")
                        tf = dati.get("timeframe", "MINUTE_5")
                        sz = dati.get("size", 1)
                        storico = dati.get("storico_wip_trend", [])
                        prezzo = prezzi_live.get(nome, "In aggiornamento...")
                        
                        posizioni_core = dati.get("posizioni_core", [])
                        posizioni_incr = dati.get("posizioni_incr", [])
                        
                        core_count = len(posizioni_core)
                        core_entry = posizioni_core[0].get("entry", 0) if core_count > 0 else 0
                        
                        incr_count = len(posizioni_incr)
                        incr_avg = sum(p.get("entry", 0) for p in posizioni_incr) / incr_count if incr_count > 0 else 0
                        
                        tipo_strat = dati.get("tipo_strategia", "RANGE")
                        
                        # Colore e stile del pulsante Strumento WIP
                        if is_attivo and tipo_strat == "TREND":
                            if dir_t == "LONG":
                                bg_color_t = "#198754" # Verde
                            elif dir_t == "SHORT":
                                bg_color_t = "#dc3545" # Rosso
                            else:
                                bg_color_t = "#00BFFF" # Azzurro
                            text_color_t = "white"
                        elif is_attivo and tipo_strat == "RANGE":
                            bg_color_t = "#17a2b8"
                            text_color_t = "white"
                        else:
                            bg_color_t = "#495057"
                            text_color_t = "white"
                            
                        totale_wip_t = 0.0
                        if storico:
                            for riga in storico:
                                match = re.search(r"\[PnL:\s*([+-]?\d+(?:[\.,]\d+)?)\s*€\]", riga)
                                if match:
                                    totale_wip_t += float(match.group(1).replace(",", "."))
                        
                        segno_t = "+" if totale_wip_t > 0 else ""
                        col_tot_t = "#4ade80" if totale_wip_t > 0 else ("#ff6b6b" if totale_wip_t < 0 else "#aaa")
                        valore_tot_t_str = f"{segno_t}{totale_wip_t:.0f} €"
                        
                        # Calcolo PnL Live Core + Incrementi (derivante da Pfoglio)
                        c_conf = CONFIG_STRUMENTI.get(nome, {})
                        c_mult = c_conf.get("moltiplicatore", 1)
                        c_valore_punto = c_conf.get("valore_punto", 1)
                        c_valuta = c_conf.get("valuta", "USD")
                        c_rate = get_eur_rate(c_valuta, prezzi_live)
                        c_epic = c_conf.get("epic")
                        
                        pnl_live_trend = 0.0
                        has_live_pos = False
                        
                        pos_live_all = st.session_state.get("live_pos_data", [])
                        if pos_live_all and c_epic:
                            for p in pos_live_all:
                                if p.get('market', {}).get('epic') == c_epic:
                                    sz_p = float(p.get('position', {}).get('size', 0))
                                    lvl_p = float(p.get('position', {}).get('level', 0))
                                    dir_p = p.get('position', {}).get('direction')
                                    if isinstance(prezzo, (int, float)):
                                        pts = (prezzo - lvl_p)/c_mult if dir_p == 'BUY' else (lvl_p - prezzo)/c_mult
                                        pnl_live_trend += (pts * sz_p * c_valore_punto * c_rate)
                                        has_live_pos = True
                                        
                        if not has_live_pos and isinstance(prezzo, (int, float)):
                            for cp in posizioni_core:
                                sz_p = float(cp.get("size", 0))
                                lvl_p = float(cp.get("entry", 0))
                                dir_p = cp.get("direction", dir_t)
                                pts = (prezzo - lvl_p)/c_mult if dir_p == 'LONG' else (lvl_p - prezzo)/c_mult
                                pnl_live_trend += (pts * sz_p * c_valore_punto * c_rate)
                                has_live_pos = True
                            for ip in posizioni_incr:
                                sz_p = float(ip.get("size", 0))
                                lvl_p = float(ip.get("entry", 0))
                                dir_p = ip.get("direction", dir_t)
                                pts = (prezzo - lvl_p)/c_mult if dir_p == 'LONG' else (lvl_p - prezzo)/c_mult
                                pnl_live_trend += (pts * sz_p * c_valore_punto * c_rate)
                                has_live_pos = True
                                
                        if has_live_pos:
                            segno_live = "+" if pnl_live_trend > 0 else ""
                            # Verde erba (#00E676) o Rosso salmone (#FA8072)
                            col_live = "#00E676" if pnl_live_trend >= 0 else "#FA8072"
                            valore_live_str = f"{segno_live}{pnl_live_trend:.0f} €"
                        else:
                            col_live = "#888888"
                            valore_live_str = "0 €"
                        
                        html_tot_wip_t = f"""<div style='font-size: 0.70rem; color: #bbb; margin-top: 0px; margin-bottom: 3px; padding-left: 2px; line-height: 1.15; white-space: nowrap;'>
<div>Live: <b style='color: {col_live};'>{valore_live_str}</b></div>
<div>Totale: <b style='color: {col_tot_t};'>{valore_tot_t_str}</b></div>
</div>"""

                        marker_class_t = f"btn-trend-{nome.replace('/', '').replace(' ', '')}"
                        css_marker_t = f"""<style>
                        div[data-testid="stHorizontalBlock"]:has(.{marker_class_t}) {{
                            margin-bottom: -15px !important;
                        }}
                        div[data-testid="stColumn"]:has(.{marker_class_t}) {{
                            margin-top: -22px !important;
                        }}
                        div[data-testid="stColumn"]:has(.{marker_class_t}) div[data-testid="stButton"] > button {{
                            background-color: {bg_color_t} !important; border-color: {bg_color_t} !important; color: {text_color_t} !important;
                        }}
                        </style>"""

                        c1, c2, c3, c4 = st.columns([1.5, 3.5, 1.8, 3.2], vertical_alignment="center")
                        with c1:
                            st.markdown(f"<span class='{marker_class_t}'></span>{css_marker_t}", unsafe_allow_html=True)
                            st.markdown(html_tot_wip_t, unsafe_allow_html=True)
                            if st.button(nome, key=f"wip_trend_{conto_selezionato}_{nome}", type="primary", use_container_width=True):
                                mostra_diario_wip_trend(nome, storico, conto=conto_selezionato)
                        
                        if is_attivo and tipo_strat == "TREND":
                            tf_map = {"MINUTE_5": "M5", "MINUTE_10": "M10", "HOUR": "H1", "HOUR_4": "H4", "DAY": "D"}
                            tf_display = tf_map.get(tf, tf)
                            if dir_t in ("LONG", "SHORT") and core_count > 0:
                                color = "#198754" if dir_t == "LONG" else "#dc3545"
                                bg_c = "rgba(40,167,69,0.15)" if dir_t == "LONG" else "rgba(220,53,69,0.15)"
                                dec = CONFIG_STRUMENTI.get(nome, {}).get("decimali", 5)
                                core_sz_val = posizioni_core[0].get("size", sz) if core_count > 0 else sz
                                str_core = f"Core: {core_sz_val:g}@{core_entry:.{dec}f}"
                                str_incr = f" | Incr: {incr_count} @ {incr_avg:.{dec}f}" if incr_count > 0 else " | Incr: 0"
                                c2.markdown(f"<div style='display: flex; align-items: center; gap: 8px;'><span style='background-color: {bg_c}; color: {color}; padding: 4px 8px; border-radius: 4px; font-weight: bold; font-size: 0.85rem; white-space: nowrap;'>⚡ {dir_t} ({tf_display})</span><span style='color:#ccc; font-size:0.8rem; white-space: nowrap;'>{str_core}{str_incr}</span></div>", unsafe_allow_html=True)
                            elif dati.get("needs_manual_start", False):
                                c2.markdown(f"<div style='display: flex; align-items: center; gap: 8px;'><span style='background-color: rgba(13,110,253,0.15); color: #0d6efd; padding: 4px 8px; border-radius: 4px; font-weight: bold; font-size: 0.85rem; white-space: nowrap;'>🚀 AVVIO ({dir_t})</span><span style='color:#bbb; font-size:0.8rem; white-space: nowrap;'>Esecuzione a mercato...</span></div>", unsafe_allow_html=True)
                            else:
                                c2.markdown(f"<div style='display: flex; align-items: center; gap: 8px;'><span style='background-color: rgba(255,193,7,0.15); color: #ffc107; padding: 4px 8px; border-radius: 4px; font-weight: bold; font-size: 0.85rem; white-space: nowrap;'>⏳ FLAT ({tf_display})</span></div>", unsafe_allow_html=True)
                        elif is_attivo and tipo_strat == "RANGE":
                            c2.markdown("<span style='background-color: rgba(23,162,184,0.1); color: #17a2b8; padding: 4px 8px; border-radius: 4px; font-weight: bold;'>🛡️ IN RANGE</span>", unsafe_allow_html=True)
                        else:
                            c2.markdown("<span style='background-color: rgba(108,117,125,0.1); color: #adb5bd; padding: 4px 8px; border-radius: 4px; font-weight: bold;'>⏸️ SPENTO</span>", unsafe_allow_html=True)
                            
                        c3.markdown(f"<div style='height: 32px; display: flex; align-items: center;'><span style='display: inline-block; min-width: 80px; width: auto; white-space: nowrap; text-align: center; font-family: monospace; font-size: 1.1rem; color: #FFD700; letter-spacing: 0.5px; border: 1px solid rgba(255, 215, 0, 0.5); padding: 3px 8px; border-radius: 5px; background-color: rgba(255, 215, 0, 0.08);'>{prezzo}</span></div>", unsafe_allow_html=True)
                        
                        ultimo_evento_raw = storico[-1] if storico else "Nessun evento registrato in questo ciclo."
                        ultimo_evento = formatta_ultimo_evento_sintesi(ultimo_evento_raw, dati, nome)
                        c4.markdown(f"<div style='font-size: 0.85rem; color: white; line-height: 1.3; display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden;'>{ultimo_evento}</div>", unsafe_allow_html=True)
                        st.markdown("<div style='margin-bottom: 12px;'></div>", unsafe_allow_html=True)

            renderizza_sintesi_trend()

    if tab_operativa is not None:
        with tab_operativa:

            @st.fragment(run_every=15)
            def renderizza_dati_live():
                memoria_attuale = carica_memoria(conto_selezionato) 
                stato = leggi_stato_sistema(conto_selezionato)
                distanze_minime = stato.get("distanze_minime", {})
                prezzi_live = stato.get("prezzi_live", {})
                prezzi_bid_ask = stato.get("prezzi_bid_ask", {})
            
                col_titolo_main, col_btn_restart = st.columns([5, 1])
                with col_titolo_main:
                    st.markdown("<h1 style='color: #FFD700; margin-top: -15px; white-space: nowrap;'>⚙️ Dashboard Trading Range</h1>", unsafe_allow_html=True)
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
                        tipo_strategia = dati_salvati.get("tipo_strategia", "RANGE")
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
                            st.warning("🌙 **PAUSA NOTTURNA (ROLLOVER) ATTIVA.** Le funzioni sono bloccate e gli ordini pendenti rimossi temporaneamente per protezione dallo spread. Ripresa automatica alle 00:15.")
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
                        elif tipo_strategia == "TREND" and stato_attivo:
                            st.warning("⚠️ L'asset è attualmente configurato e **ATTIVO in Trend**.")
                        elif not stato_attivo:
                            msg_err = dati_salvati.get("msg_manuale") or ("Errore avvio" if dati_salvati.get("errore_avvio") else ("Errore ripristino" if dati_salvati.get("errore_ripristino") else ""))
                            if msg_err:
                                st.error(f"🛑 **Allarme/Sospensione Rilevata:** {msg_err}")
                                if st.button("🗑️ RICONOSCI & RESETTA ALLARME", key=f"RST_ERR_{conto_selezionato}_{nome}", width="stretch"):
                                    memoria_attuale[nome] = {**dati_salvati, "msg_manuale": "", "errore_avvio": False, "errore_ripristino": False, "alert_falso_allarme": False}
                                    salva_memoria(conto_selezionato, memoria_attuale)
                                    st.rerun()
                            col_l, col_s = st.columns(2)
                            with col_l:
                                if st.button("🚀AVVIA LONG", key=f"L_{conto_selezionato}_{nome}", width="stretch"):
                                    memoria_attuale[nome] = {"attivo": True, "direzione": "LONG", "tp": tp, "opp": opp, "dts": dts, "size": size, "stato": "IN_ATTESA", "storico_wip": [], "errore_avvio": False, "errore_ripristino": False, "comando_manuale": False, "msg_manuale": "", "tipo_strategia": "RANGE"}
                                    salva_memoria(conto_selezionato, memoria_attuale)
                                    st.rerun()
                            with col_s:
                                if st.button("🚀AVVIA SHORT", key=f"S_{conto_selezionato}_{nome}", width="stretch"):
                                    memoria_attuale[nome] = {"attivo": True, "direzione": "SHORT", "tp": tp, "opp": opp, "dts": dts, "size": size, "stato": "IN_ATTESA", "storico_wip": [], "errore_avvio": False, "errore_ripristino": False, "comando_manuale": False, "msg_manuale": "", "tipo_strategia": "RANGE"}
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
                                    vecchio_wip.append(f"[{now_it().strftime('%d/%m %H:%M:%S')}] 🛑 Tasto STOP premuto. Macchinetta spenta.")
                                    memoria_attuale[nome] = {**dati_salvati, "attivo": False, "direzione": "", "stato": "IN_ATTESA", "kill_switch": True, "sospeso_weekend": False, "tp": tp, "opp": opp, "dts": dts, "size": size, "storico_wip": vecchio_wip, "errore_avvio": False, "errore_ripristino": False, "comando_manuale": False, "msg_manuale": "", "tipo_strategia": "RANGE"}
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
                                elif is_sosp_rollover: st.warning(f"🌙 IN PAUSA ROLLOVER ({direzione}) | In attesa delle 00:15")
                                elif stato_corrente == "FASE_2_STANDBY": st.markdown("<div style='background-color: #FFD700; color: #000000; padding: 10px; border-radius: 6px; font-weight: bold; margin-bottom: 1rem;'>⏳ IN ATTESA DI RIENTRO | Motore in Stand-By</div>", unsafe_allow_html=True)
                                else: st.success(f"🟢 ATTIVO ({direzione}) | Motore: {stato_corrente_disp}")
                            else: st.error(f"🔴 SPENTO | Motore: {stato_corrente_disp}")

                tutti_strumenti = ["AUD/NZD", "CAD/JPY", "EUR/USD", "GBP/JPY", "GBP/USD", "USD/CAD", "USD/CHF", "USD/JPY", "Spot Gold", "US 500 Cash"]
                for i in range(0, len(tutti_strumenti), 2):
                    c1, c2 = st.columns(2)
                    with c1:
                        crea_riquadro_strumento(tutti_strumenti[i], "Asset" if tutti_strumenti[i] in ["Spot Gold", "US 500 Cash"] else "Forex Mini", *( (100, 20, 10) if tutti_strumenti[i] in ["Spot Gold", "US 500 Cash"] else (50, 10, 5) ), 4)
                    with c2:
                        if i + 1 < len(tutti_strumenti):
                            crea_riquadro_strumento(tutti_strumenti[i+1], "Asset" if tutti_strumenti[i+1] in ["Spot Gold", "US 500 Cash"] else "Forex Mini", *( (100, 20, 10) if tutti_strumenti[i+1] in ["Spot Gold", "US 500 Cash"] else (50, 10, 5) ), 4)

            renderizza_dati_live()

    if tab_trend is not None:
        with tab_trend:
            @st.fragment(run_every=15)
            def renderizza_dati_trend():
                memoria_attuale = carica_memoria(conto_selezionato) 
                stato = leggi_stato_sistema(conto_selezionato)
                prezzi_bid_ask = stato.get("prezzi_bid_ask", {})
            
                col_titolo_main, col_btn_restart = st.columns([5, 1])
                with col_titolo_main:
                    st.markdown("<h1 style='color: #00BFFF; margin-top: -15px; white-space: nowrap;'>📈 Dashboard Trend (KJ55 / TK21)</h1>", unsafe_allow_html=True)
                with col_btn_restart:
                    st.write("") 

                st.markdown("---")





                radar_data, _ = carica_radar_trend_dash(conto_selezionato)

                def crea_riquadro_trend(nome, def_body=10, def_size=3, def_size_max=5, def_scala=1):
                    with st.container(border=True):
                        dati_salvati = memoria_attuale.get(nome, {})
                        stato_corrente = dati_salvati.get("stato", "FLAT")
                        stato_attivo = dati_salvati.get("attivo", False)
                        direzione = dati_salvati.get("direzione", "")
                        
                        tf_val = dati_salvati.get("timeframe", "MINUTE_5")
                        size_val = dati_salvati.get("size", def_size)
                        size_max_val = dati_salvati.get("size_max", def_size_max)
                        scala_val = dati_salvati.get("scala", def_scala)
                        auto_restart = dati_salvati.get("auto_restart", False)
                        tipo_strategia = dati_salvati.get("tipo_strategia", "RANGE")
                        
                        tf_map = {"MINUTE_5": "M5", "MINUTE_10": "M10", "HOUR": "H1", "HOUR_4": "H4", "DAY": "D1"}
                        tf_selected = st.session_state.get(f"tf_{conto_selezionato}_{nome}", tf_val)
                        tf_badge = tf_map.get(tf_selected, "M5")
                        
                        col_titolo, col_salva = st.columns([3, 1], vertical_alignment="center")
                        with col_titolo:
                            auto_restart = st.checkbox("Auto-Restart", value=dati_salvati.get("auto_restart", False), key=f"auto_{conto_selezionato}_{nome}")
                            
                            badge = "🟢 <b>[ Attivo ]</b>" if stato_attivo else "🔴 <b>[ Spento ]</b>"
                            titolo_html = formatta_titolo_con_bandiere_orizzontale(nome, badge)
                            st.markdown(titolo_html, unsafe_allow_html=True)
                            
                            bid = prezzi_bid_ask.get(nome, {}).get("bid", "-")
                            ask = prezzi_bid_ask.get(nome, {}).get("ask", "-")
                            
                            # Allineamento dinamico Kijun (KJ55) e Tenkan (TK21) con Radar Trend per il timeframe selezionato
                            current_kj = None
                            current_tk = None
                            if radar_data and nome in radar_data:
                                tf_info = radar_data[nome].get("timeframes", {}).get(tf_badge, {})
                                current_kj = tf_info.get("kj")
                                current_tk = tf_info.get("tk")
                            
                            px_ref = bid if isinstance(bid, (int, float)) else (ask if isinstance(ask, (int, float)) else None)
                            if current_kj is None or current_tk is None:
                                candele_loc = carica_candele_locali_dash(conto_selezionato, nome, tf_selected, px_live=px_ref)
                                if current_kj is None:
                                    current_kj = calcola_kj55_da_candele_dash(candele_loc, periods=55)
                                if current_tk is None:
                                    current_tk = calcola_kj55_da_candele_dash(candele_loc, periods=21)
                            
                            dec = CONFIG_STRUMENTI.get(nome, {}).get("decimali", 2)
                            kj_str = f"{current_kj:.{dec}f}" if current_kj is not None else "-"
                            tk_str = f"{current_tk:.{dec}f}" if current_tk is not None else "-"
                            st.markdown(f"<div style='font-size: 0.8rem; color: #aaa; margin-top:-10px; margin-bottom: 2px;'>Bid: {bid} | Ask: {ask}</div>", unsafe_allow_html=True)
                            st.markdown(f"<div style='font-size: 0.82rem; margin-bottom: 6px;'><b style='color: #FFD700;'>🟡 Kijun ({tf_badge}):</b> <span style='color: #FFFF00; font-weight: 500;'>{kj_str}</span> &nbsp;|&nbsp; <b style='color: #00BFFF;'>🔵 Tenkan ({tf_badge}):</b> <span style='color: #00BFFF;'>{tk_str}</span></div>", unsafe_allow_html=True)
                            
                        with col_salva:
                            if st.button("💾 Salva", key=f"SAVE_T_{conto_selezionato}_{nome}", width="stretch"):
                                memoria_attuale[nome] = {
                                    **dati_salvati,
                                    "timeframe": st.session_state.get(f"tf_{conto_selezionato}_{nome}", tf_val),
                                    "size": st.session_state.get(f"sz_{conto_selezionato}_{nome}", size_val),
                                    "size_max": st.session_state.get(f"szm_{conto_selezionato}_{nome}", size_max_val),
                                    "scala": st.session_state.get(f"sc_{conto_selezionato}_{nome}", scala_val),
                                    "auto_restart": auto_restart,
                                    "current_kj": current_kj,
                                    "current_tk": current_tk
                                }
                                salva_memoria(conto_selezionato, memoria_attuale)
                                st.rerun()
                            if st.button("📋 WIP", key=f"WIP_T_{conto_selezionato}_{nome}", width="stretch"):
                                mostra_diario_wip_trend(nome, dati_salvati.get("storico_wip_trend", []), conto=conto_selezionato)

                        c_r1, c_r2, c_r3, c_r4 = st.columns(4)
                        with c_r1:
                            tf_map = {"MINUTE_5": "M5", "MINUTE_10": "M10", "HOUR": "H1", "HOUR_4": "H4", "DAY": "D"}
                            tf_keys = list(tf_map.keys())
                            idx = tf_keys.index(tf_val) if tf_val in tf_keys else 0
                            st.selectbox("Timeframe", tf_keys, index=idx, format_func=lambda x: tf_map[x], key=f"tf_{conto_selezionato}_{nome}")
                        with c_r2:
                            st.number_input("Entry Size", value=int(size_val), min_value=1, step=1, key=f"sz_{conto_selezionato}_{nome}")
                        with c_r3:
                            st.number_input("Size Max", value=int(size_max_val), min_value=1, step=1, key=f"szm_{conto_selezionato}_{nome}")
                        with c_r4:
                            st.number_input("Scala", value=int(scala_val), min_value=1, step=1, key=f"sc_{conto_selezionato}_{nome}", help="Size di ciascun incremento")
                        
                        err_key = f"err_trend_{conto_selezionato}_{nome}"
                        if err_key in st.session_state and st.session_state[err_key]:
                            st.error(st.session_state[err_key])

                        msg_err_trend = dati_salvati.get("msg_manuale") or ("Errore avvio Trend" if dati_salvati.get("errore_avvio") else "")
                        if msg_err_trend and not stato_attivo:
                            st.error(f"🛑 **Allarme/Blocco Rilevato:** {msg_err_trend}")
                            if st.button("🗑️ RICONOSCI & RESETTA ALLARME", key=f"RST_ERR_T_{conto_selezionato}_{nome}", width="stretch"):
                                memoria_attuale[nome] = {**dati_salvati, "msg_manuale": "", "errore_avvio": False}
                                salva_memoria(conto_selezionato, memoria_attuale)
                                st.session_state[err_key] = ""
                                st.rerun()

                        px_live = None
                        try:
                            if bid != "-" and ask != "-":
                                px_live = (float(bid) + float(ask)) / 2.0
                        except Exception:
                            pass

                        is_long_bloccato = (current_kj is not None and px_live is not None and px_live < current_kj)
                        is_short_bloccato = (current_kj is not None and px_live is not None and px_live > current_kj)

                        if tipo_strategia == "RANGE" and stato_attivo:
                            st.warning("⚠️ L'asset è attualmente configurato e **ATTIVO in Trading Range**.")
                        elif not stato_attivo and not dati_salvati.get("da_chiudere_a_riapertura", False):
                            if current_kj is not None and px_live is not None:
                                if is_short_bloccato:
                                    st.markdown(f"<div style='font-size: 0.82rem; color: #FFA500; margin-bottom: 6px;'>🟡 <b>Prezzo Live ({px_live:.{dec}f}) &gt; Kijun ({current_kj:.{dec}f}):</b> Consentito solo <b>LONG</b> (SHORT bloccato da Kijun).</div>", unsafe_allow_html=True)
                                elif is_long_bloccato:
                                    st.markdown(f"<div style='font-size: 0.82rem; color: #FFA500; margin-bottom: 6px;'>🟡 <b>Prezzo Live ({px_live:.{dec}f}) &lt; Kijun ({current_kj:.{dec}f}):</b> Consentito solo <b>SHORT</b> (LONG bloccato da Kijun).</div>", unsafe_allow_html=True)

                            c_btn1, c_btn2 = st.columns(2)
                            with c_btn1:
                                help_l = f"Bloccato: Live ({px_live:.{dec}f}) < KJ ({current_kj:.{dec}f})" if is_long_bloccato else None
                                if st.button("🚀 AVVIA LONG", key=f"TL_{conto_selezionato}_{nome}", width="stretch", disabled=is_long_bloccato, help=help_l):
                                    if is_long_bloccato:
                                        st.session_state[err_key] = f"🛑 BLOCCO KIJUN: Impossibile avviare LONG! Il prezzo Live ({px_live:.{dec}f}) si trova sotto la Kijun ({current_kj:.{dec}f}). Per andare LONG il prezzo deve trovarsi sopra la Kijun."
                                        st.rerun()
                                    st.session_state[err_key] = ""
                                    memoria_attuale[nome] = {
                                        **dati_salvati, 
                                        "timeframe": st.session_state.get(f"tf_{conto_selezionato}_{nome}", tf_val),
                                        "size": st.session_state.get(f"sz_{conto_selezionato}_{nome}", size_val),
                                        "size_max": st.session_state.get(f"szm_{conto_selezionato}_{nome}", size_max_val),
                                        "scala": st.session_state.get(f"sc_{conto_selezionato}_{nome}", scala_val),
                                        "auto_restart": auto_restart,
                                        "attivo": True, 
                                        "direzione": "LONG", 
                                        "stato": "FLAT", 
                                        "tipo_strategia": "TREND", 
                                        "needs_manual_start": True,
                                        "da_chiudere_a_riapertura": False,
                                        "msg_manuale": "",
                                        "storico_wip_trend": [],
                                        "posizioni_core": [],
                                        "posizioni_incr": [],
                                        "trailing_sl_core": None,
                                        "trailing_sl_incr": None
                                    }
                                    salva_memoria(conto_selezionato, memoria_attuale)
                                    st.session_state.target_tab = "Trend"
                                    st.rerun()
                            with c_btn2:
                                help_s = f"Bloccato: Live ({px_live:.{dec}f}) > KJ ({current_kj:.{dec}f})" if is_short_bloccato else None
                                if st.button("🚀 AVVIA SHORT", key=f"TS_{conto_selezionato}_{nome}", width="stretch", disabled=is_short_bloccato, help=help_s):
                                    if is_short_bloccato:
                                        st.session_state[err_key] = f"🛑 BLOCCO KIJUN: Impossibile avviare SHORT! Il prezzo Live ({px_live:.{dec}f}) si trova sopra la Kijun ({current_kj:.{dec}f}). Per andare SHORT il prezzo deve trovarsi sotto la Kijun."
                                        st.rerun()
                                    st.session_state[err_key] = ""
                                    memoria_attuale[nome] = {
                                        **dati_salvati, 
                                        "timeframe": st.session_state.get(f"tf_{conto_selezionato}_{nome}", tf_val),
                                        "size": st.session_state.get(f"sz_{conto_selezionato}_{nome}", size_val),
                                        "size_max": st.session_state.get(f"szm_{conto_selezionato}_{nome}", size_max_val),
                                        "scala": st.session_state.get(f"sc_{conto_selezionato}_{nome}", scala_val),
                                        "auto_restart": auto_restart,
                                        "attivo": True, 
                                        "direzione": "SHORT", 
                                        "stato": "FLAT", 
                                        "tipo_strategia": "TREND", 
                                        "needs_manual_start": True,
                                        "da_chiudere_a_riapertura": False,
                                        "msg_manuale": "",
                                        "storico_wip_trend": [],
                                        "posizioni_core": [],
                                        "posizioni_incr": [],
                                        "trailing_sl_core": None,
                                        "trailing_sl_incr": None
                                    }
                                    salva_memoria(conto_selezionato, memoria_attuale)
                                    st.session_state.target_tab = "Trend"
                                    st.rerun()

                            if st.button("⚖️ AVVIO MULTICONTO (Trend + Range)", key=f"SYNC_TREND_BTN_{conto_selezionato}_{nome}", use_container_width=True):
                                st.session_state[f"sync_trend_open_{nome}"] = True
                                st.rerun()
                            
                            if st.session_state.get(f"sync_trend_open_{nome}", False):
                                dialog_sync_start_trend(conto_selezionato, nome)
                        else:
                            c_stop, c_info = st.columns([1, 3], vertical_alignment="center")
                            with c_stop:
                                if st.button("⏹️ STOP", key=f"TSTOP_{conto_selezionato}_{nome}", width="stretch"):
                                    st.session_state[err_key] = ""
                                    ora_str = now_it().strftime("%d/%m %H:%M:%S")
                                    ok_ig, msg_ig, rimaste = chiudi_posizioni_trend_su_ig(conto_selezionato, nome)
                                    storico = dati_salvati.get("storico_wip_trend", [])
                                    if ok_ig:
                                        storico.append(f"[{ora_str}] 🛑 STOP: Spento e chiuso su IG ({msg_ig})")
                                        memoria_attuale[nome] = {
                                            **dati_salvati, 
                                            "attivo": False,
                                            "stato": "FLAT",
                                            "direzione": "",
                                            "posizioni_core": [],
                                            "posizioni_incr": [],
                                            "trailing_sl_core": None,
                                            "trailing_sl_incr": None,
                                            "needs_manual_start": False,
                                            "da_chiudere_a_riapertura": False,
                                            "storico_wip_trend": storico[-30:],
                                            "msg_manuale": ""
                                        }
                                    else:
                                        storico.append(f"[{ora_str}] ⚠️ STOP Rifiutato su IG ({msg_ig}). Posizione in attesa di riapertura.")
                                        memoria_attuale[nome] = {
                                            **dati_salvati, 
                                            "attivo": False,
                                            "stato": "IN_ATTESA_CHIUSURA",
                                            "da_chiudere_a_riapertura": True,
                                            "needs_manual_start": False,
                                            "storico_wip_trend": storico[-30:],
                                            "msg_manuale": f"⚠️ Chiusura IG rifiutata ({msg_ig}). La posizione verrà liquidata automaticamente alla riapertura del mercato."
                                        }
                                    salva_memoria(conto_selezionato, memoria_attuale)
                                    st.rerun()
                            with c_info:
                                tf_display = tf_map.get(tf_val, tf_val)
                                pos_c = dati_salvati.get("posizioni_core", [])
                                pos_i = dati_salvati.get("posizioni_incr", [])
                                if dati_salvati.get("da_chiudere_a_riapertura") or stato_corrente == "IN_ATTESA_CHIUSURA":
                                    st.error(f"🔴 STOP RICHIESTO (Mercato Sospeso/Chiuso) | Posizione {direzione} in attesa liquidazione")
                                elif direzione in ("LONG", "SHORT") and (pos_c or pos_i):
                                    st.success(f"🟢 ATTIVO TREND ({direzione}) | ({tf_display})")
                                elif dati_salvati.get("needs_manual_start", False):
                                    st.info(f"🚀 AVVIO IN CORSO ({direzione})...")
                                else:
                                    st.warning(f"⏳ FLAT | ({tf_display})")
                        


                tutti_strumenti = ["AUD/NZD", "CAD/JPY", "EUR/USD", "GBP/JPY", "GBP/USD", "USD/CAD", "USD/CHF", "USD/JPY", "Spot Gold", "US 500 Cash"]
                for i in range(0, len(tutti_strumenti), 2):
                    c1, c2 = st.columns(2)
                    with c1:
                        crea_riquadro_trend(tutti_strumenti[i])
                    with c2:
                        if i + 1 < len(tutti_strumenti):
                            crea_riquadro_trend(tutti_strumenti[i+1])

            renderizza_dati_trend()

    if tab_restore is not None:
        with tab_restore:

            st.title("🛠️ Strumento di Recovery")
            st.markdown("Wizard guidato per l'inserimento manuale o la correzione tattica di un ordine mancante. Calcolato in tempo reale in base alla tua strategia.")

            col1, col2, col3 = st.columns(3)
            with col1:
                tutti_strumenti = ["AUD/NZD", "CAD/JPY", "EUR/USD", "GBP/JPY", "GBP/USD", "USD/CAD", "USD/CHF", "USD/JPY", "Spot Gold", "US 500 Cash"]
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
            
                # --- VALIDAZIONE LIVE ---
                t_epic = c.get("epic")
                pos_live = st.session_state.get("live_pos_data", [])
                ord_live = st.session_state.get("live_ord_data", [])
                
                core_ids = [p['position']['dealId'] for p in pos_live if p['market']['epic'] == t_epic and float(p['position']['size']) == s_core]
                has_core = len(core_ids) > 0
                
                ord_mezzo_count = len([o for o in ord_live if o['marketData']['epic'] == t_epic and float(o['workingOrderData']['orderSize']) == s_mezzo])
                pos_mezzo_count = len([p for p in pos_live if p['market']['epic'] == t_epic and float(p['position']['size']) == s_mezzo and p['position']['dealId'] not in core_ids])
                
                recovery_error = None
                if not has_core and r_anom not in ["Posizione TAGLIO CORE (A Mercato)", "Ordine ULTIMA (Pendente)"]:
                    recovery_error = "Nessuna posizione Core rilevata a mercato. Apri prima la posizione principale da IG."
                elif "MICRO" in r_anom and ord_mezzo_count > 0:
                    recovery_error = f"Esiste già un ordine pendente della stessa size ({s_mezzo})."
                elif "TICKET1" in r_anom and pos_mezzo_count > 0:
                    recovery_error = f"Esiste già una posizione a mercato della stessa size ({s_mezzo})."
                elif "SAT1 OCO" in r_anom and ord_mezzo_count >= 2:
                    recovery_error = f"Sono già presenti {ord_mezzo_count} ordini pendenti di size {s_mezzo}."
                elif "SAT2" in r_anom:
                    pos_quarto_count = len([p for p in pos_live if p['market']['epic'] == t_epic and float(p['position']['size']) == s_quarto])
                    if pos_quarto_count > 0:
                        recovery_error = f"Esiste già una posizione a mercato della size di SAT2 ({s_quarto})."

                if recovery_error:
                    st.error(f"🚫 **Recovery Bloccato:** {recovery_error}")
                elif "MICRO" in r_anom:
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
            
                if cmd_data and not recovery_error:
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
                        lines = [l.strip().replace("\r", " ").replace("\n", " ") for l in f.readlines() if l.strip()]
                    # Mostra prima le righe più recenti in alto
                    reversed_lines = list(reversed(lines))
                except FileNotFoundError:
                    reversed_lines = [f"> In attesa di connessione col Motore per {conto_selezionato}..."]
                
                def render_terminal_box(lista_righe, empty_msg="Nessun evento registrato in questa categoria."):
                    if not lista_righe:
                        st.markdown(f"<div style='color: #64748b; padding: 12px; font-style: italic;'>{empty_msg}</div>", unsafe_allow_html=True)
                        return
                    righe_html = []
                    for riga in lista_righe:
                        # Abbreviazione formato candela esteso se presente nello storico
                        riga = re.sub(r"Candela \((\w+)\) CHIUSA:[^()]*\(alle (\d{2}:\d{2}) ora italiana\)", r"Candela [\1] ore \2", riga)
                        riga_esc = riga.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                        # Evidenziazione pulita timestamp e strumento
                        riga_fmt = re.sub(
                            r"^(\[(?:\d{1,2}/\d{1,2}\s+)?\d{2}:\d{2}:\d{2}\])",
                            r"<span style='color: #64748b; font-weight: 500;'>\1</span>",
                            riga_esc
                        )
                        riga_fmt = re.sub(
                            r"(</span>\s*)(\[[A-Za-z0-9_/\s\.\-]+\])",
                            r"\1<span style='color: #38bdf8; font-weight: 600;'>\2</span>",
                            riga_fmt
                        )
                        # Evidenziazione timeframe candela
                        riga_fmt = re.sub(
                            r"(\[(?:M5|H1|H4|D|D1|MINUTE_5|HOUR|HOUR_4|DAY)\])",
                            r"<span style='color: #fb923c; font-weight: 600;'>\1</span>",
                            riga_fmt
                        )
                        riga_fmt = re.sub(
                            r"(\[PnL:\s*\+[^\]]+\])",
                            r"<span style='color: #4ade80; font-weight: 600;'>\1</span>",
                            riga_fmt
                        )
                        riga_fmt = re.sub(
                            r"(\[PnL:\s*\-[^\]]+\])",
                            r"<span style='color: #f87171; font-weight: 600;'>\1</span>",
                            riga_fmt
                        )
                        riga_fmt = re.sub(
                            r"(KJ(?:55)?:\s*[0-9\.]+)",
                            r"<span style='color: #FFFF00; font-weight: 600;'>\1</span>",
                            riga_fmt
                        )
                        riga_fmt = re.sub(
                            r"(TK:\s*[0-9\.]+)",
                            r"<span style='color: #00d2ff; font-weight: 600;'>\1</span>",
                            riga_fmt
                        )
                        righe_html.append(f"<div style='padding: 1px 0;'>{riga_fmt}</div>")
                    
                    logs_content = "".join(righe_html)
                    st.html(f"""
                        <div style='
                            background-color: #0f172a; 
                            color: #e2e8f0; 
                            font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace; 
                            font-size: 0.80rem; 
                            padding: 8px 12px; 
                            border-radius: 6px; 
                            border: 1px solid rgba(255, 255, 255, 0.08);
                            max-height: 520px; 
                            overflow-y: auto;
                            overflow-x: auto;
                            line-height: 1.25;
                            white-space: nowrap;
                        '>
                            {logs_content}
                        </div>
                    """)

                # Suddivisione in categorie
                candele_lines = []
                entrate_lines = []
                chiusure_lines = []
                varie_lines = []

                for riga in reversed_lines:
                    r_up = riga.upper()
                    # 1. Candele chiuse
                    if "CANDELA" in r_up:
                        candele_lines.append(riga)
                    # 2. Chiusure (uscite, TP, SL, bancomat, stop KJ/TK, ecc.)
                    elif any(k in r_up for k in [
                        "CHIUSURA", "CLOSE CORE", "CLOSE INCR", "TP INCR", "BANCOMAT", 
                        "FIFO INCR", "STOP TK", "STOP KJ", "TRAILING CORE", "PARACADUTE KJ",
                        "CHIUSO IN PROFITTO", "CHIUSO IN STOP LOSS", "CHIUSO IN LOSS", 
                        "TARGET FASE 1 RAGGIUNTO", "LIQUIDAT", "➡️ FLAT", "CHIUSURA POSIZIONI",
                        "PULIZIA [TICKET2]"
                    ]):
                        chiusure_lines.append(riga)
                    # 3. Possibili entrate (segnali Radar e ordini di ingresso/restart/reverse)
                    elif any(k in r_up for k in [
                        "POSSIBILE ENTRATA", "RADAR", "OPEN CORE", "OPEN INCR", 
                        "PRE-FLIGHT CHECK", "ENTRATA A MERCATO", "PIAZZAMENTO SAT1", 
                        "INSERISCO [SAT2]", "INSERISCO ORDINE [TICKET", "FLIP DEL [TICKET",
                        "ORDINE OVERGAIN", "ORDINE OVERLOSS", "GRIGLIA ACCETTATA",
                        "REVERSE", "RESTART CORE", "RESTART LONG", "RESTART SHORT"
                    ]):
                        entrate_lines.append(riga)
                    # 4. Varie (sistema, connessioni, rate limit, rollover, controlli tecnici)
                    else:
                        varie_lines.append(riga)

                sub_tabs = st.tabs([
                    "📋 Tutti", 
                    "🕯️ Candele chiuse", 
                    "🎯 Possibili entrate", 
                    "🛑 Chiusure", 
                    "⚙️ Varie"
                ])

                tab_sub_tutti, tab_sub_candele, tab_sub_entrate, tab_sub_chiusure, tab_sub_varie = sub_tabs

                with tab_sub_tutti:
                    st.caption(f"Mostrando tutti gli eventi ({len(reversed_lines)} righe)")
                    render_terminal_box(reversed_lines)

                with tab_sub_candele:
                    col_tf, col_info = st.columns([3, 7])
                    with col_tf:
                        tf_sel = st.selectbox(
                            "Filtra Timeframe:",
                            ["Tutti", "M5", "H1", "H4", "D"],
                            key=f"sel_tf_candele_{conto_selezionato}"
                        )

                    if tf_sel == "Tutti":
                        candele_filtrate = candele_lines
                    elif tf_sel == "M5":
                        candele_filtrate = [r for r in candele_lines if "[M5]" in r.upper() or "(M5)" in r.upper() or "MINUTE_5" in r.upper()]
                    elif tf_sel == "H1":
                        candele_filtrate = [r for r in candele_lines if "[H1]" in r.upper() or "(H1)" in r.upper() or "HOUR]" in r.upper() or "HOUR_1" in r.upper()]
                    elif tf_sel == "H4":
                        candele_filtrate = [r for r in candele_lines if "[H4]" in r.upper() or "(H4)" in r.upper() or "HOUR_4" in r.upper()]
                    elif tf_sel == "D":
                        candele_filtrate = [r for r in candele_lines if "[D]" in r.upper() or "[D1]" in r.upper() or "(D)" in r.upper() or "(D1)" in r.upper() or "DAY" in r.upper()]
                    else:
                        candele_filtrate = candele_lines

                    with col_info:
                        st.markdown(f"<div style='padding-top: 28px; color: #888; font-size: 0.82rem;'>Candele mostrate: <b>{len(candele_filtrate)}</b> (su {len(candele_lines)} chiuse totali)</div>", unsafe_allow_html=True)

                    render_terminal_box(candele_filtrate, empty_msg=f"Nessuna candela chiusa registrata per il Timeframe '{tf_sel}'.")

                with tab_sub_entrate:
                    st.caption(f"Eventi segnali / entrate a mercato: {len(entrate_lines)}")
                    render_terminal_box(entrate_lines, empty_msg="Nessuna possibile entrata o ordine registrato di recente.")

                with tab_sub_chiusure:
                    st.caption(f"Eventi uscite / chiusure / stop: {len(chiusure_lines)}")
                    render_terminal_box(chiusure_lines, empty_msg="Nessuna chiusura o stop registrato di recente.")

                with tab_sub_varie:
                    st.caption(f"Eventi operativi e di sistema: {len(varie_lines)}")
                    render_terminal_box(varie_lines, empty_msg="Nessun evento vario registrato di recente.")
            
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
                        
                        col1, col2, col3, col4 = st.columns([1, 1, 1, 1])
                        with col1:
                            if st.button("💾 Salva Permessi", key=f"salva_{u}", use_container_width=True):
                                auth_manager.aggiorna_conti_utente(u, sel_conti)
                                st.success(f"Permessi aggiornati per {u}")
                        with col2:
                            with st.popover("✏️ Modifica Nick", use_container_width=True):
                                new_nick = st.text_input("Nuovo Nickname", value=u, key=f"nick_input_{u}")
                                if st.button("Conferma Nick", key=f"btn_nick_{u}", use_container_width=True):
                                    if new_nick and new_nick.strip() != u:
                                        ok, msg = auth_manager.rinomina_utente(u, new_nick.strip())
                                        if ok:
                                            if st.session_state.get("user") == u:
                                                st.session_state.user = new_nick.strip()
                                            st.success(msg)
                                            st.rerun()
                                        else:
                                            st.error(msg)
                        with col3:
                            if st.button("🔑 Reset Password", key=f"reset_{u}", use_container_width=True):
                                auth_manager.modifica_password(u, "init")
                                st.success(f"Password per {u} resettata a 'init'.")
                        with col4:
                            if st.button("🗑️ Elimina", key=f"del_{u}", use_container_width=True):
                                ok, msg = auth_manager.elimina_utente(u)
                                if ok: st.success(msg)
                                else: st.error(msg)
                    else:
                        col1, col2, col3 = st.columns([1, 1, 1])
                        with col1:
                            with st.popover("✏️ Modifica Nick", use_container_width=True):
                                new_nick = st.text_input("Nuovo Nickname", value=u, key=f"nick_input_reg_{u}")
                                if st.button("Conferma Nick", key=f"btn_nick_reg_{u}", use_container_width=True):
                                    if new_nick and new_nick.strip() != u:
                                        ok, msg = auth_manager.rinomina_utente(u, new_nick.strip())
                                        if ok:
                                            if st.session_state.get("user") == u:
                                                st.session_state.user = new_nick.strip()
                                            st.success(msg)
                                            st.rerun()
                                        else:
                                            st.error(msg)
                        with col2:
                            if st.button("🔑 Reset Password", key=f"reset_reg_{u}", use_container_width=True):
                                auth_manager.modifica_password(u, "init")
                                st.success(f"Password per {u} resettata a 'init'.")
                        with col3:
                            if st.button("🗑️ Elimina Regista", key=f"del_reg_{u}", use_container_width=True):
                                ok, msg = auth_manager.elimina_utente(u)
                                if ok: st.success(msg)
                                else: st.error(msg)

    # --- TAB SIMULATORE ---
