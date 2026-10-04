"""
Sottomodulo XTrader.

Legge il file XTrader.xlsx (foglio "REALE X 4") e mostra l'ultima Giornata valida.
Una Giornata = 3 righe consecutive (B..AD) a partire dalla riga 12 (12-14, 15-17, ...).
La prima Giornata con cella AB vuota sulla prima riga chiude l'elenco.

Parser xlsx basato solo su libreria standard (zipfile + xml), nessuna dipendenza esterna.
"""
import os
import re
import zipfile
import xml.etree.ElementTree as ET

import streamlit as st

XTRADER_FILE = "XTrader.xlsx"
XTRADER_SHEET = "REALE X 4"
PRIMA_RIGA = 12

_NS = {
    "m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "rel": "http://schemas.openxmlformats.org/package/2006/relationships",
}


def _trova_file():
    base = os.path.dirname(os.path.abspath(__file__))
    for p in (os.path.join(base, XTRADER_FILE), XTRADER_FILE, os.path.join("/data", XTRADER_FILE)):
        if os.path.exists(p):
            return p
    return None


def _leggi_foglio(path, sheet_name):
    """Ritorna dict {'B12': valore, ...} con i valori (cache) delle celle del foglio."""
    with zipfile.ZipFile(path) as z:
        shared = []
        if "xl/sharedStrings.xml" in z.namelist():
            root = ET.fromstring(z.read("xl/sharedStrings.xml"))
            for si in root.findall("m:si", _NS):
                shared.append("".join(t.text or "" for t in si.iter("{%s}t" % _NS["m"])))

        wb = ET.fromstring(z.read("xl/workbook.xml"))
        rid = None
        for s in wb.find("m:sheets", _NS):
            if s.get("name", "").strip().upper() == sheet_name.upper():
                rid = s.get("{%s}id" % _NS["r"])
                break
        if rid is None:
            raise ValueError(f"Foglio '{sheet_name}' non trovato")

        rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
        target = None
        for r in rels.findall("rel:Relationship", _NS):
            if r.get("Id") == rid:
                target = r.get("Target")
                break
        target = target.lstrip("/")
        if not target.startswith("xl/"):
            target = "xl/" + target

        root = ET.fromstring(z.read(target))
        celle = {}
        for c in root.iter("{%s}c" % _NS["m"]):
            ref = c.get("r")
            t = c.get("t")
            v = c.find("m:v", _NS)
            if t == "inlineStr":
                is_ = c.find("m:is", _NS)
                val = "".join(x.text or "" for x in is_.iter("{%s}t" % _NS["m"])) if is_ is not None else None
            elif v is None or v.text is None:
                continue
            elif t == "s":
                val = shared[int(v.text)]
            elif t in ("str", "e"):
                val = v.text
            elif t == "b":
                val = v.text == "1"
            else:
                try:
                    f = float(v.text)
                    val = int(f) if f.is_integer() else f
                except ValueError:
                    val = v.text
            celle[ref] = val
        return celle


def _vuota(v):
    return v is None or (isinstance(v, str) and v.strip() == "")


def trova_giornate(celle):
    """Ritorna la lista delle righe iniziali delle Giornate valide (12, 15, 18, ...)."""
    giornate = []
    r = PRIMA_RIGA
    while not _vuota(celle.get(f"AB{r}")):
        giornate.append(r)
        r += 3
    return giornate


def estrai_giornata(celle, r0):
    """Estrae i valori della tabella riepilogo per la Giornata che inizia alla riga r0."""
    r1, r2 = r0 + 1, r0 + 2
    g = lambda col, riga: celle.get(f"{col}{riga}")
    extra = {
        "P": g("C", r1), "W": g("D", r1), "L": g("E", r1), "% W": g("F", r1),
        "TOT.": g("X", r0), "MD +": g("I", r1), "MD -": g("J", r1),
        "EV W": g("M", r1), "EV L": g("N", r1), "% EV": g("B", r0),
    }
    copilota = {
        "P": g("O", r1), "W": g("P", r1), "L": g("Q", r1), "% W": g("R", r1),
        "TOT.": g("X", r2), "MD +": g("V", r1), "MD -": g("W", r1),
        "EV W": None, "EV L": None, "% EV": None,
    }
    return {"data": g("AB", r0), "EXTRA": extra, "COPILOTA": copilota}


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _fmt(col, v):
    if _vuota(v):
        return ""
    n = _num(v)
    if n is None:
        return str(v)
    if col in ("% W", "% EV"):
        return f"{round(n * 100):d}%"
    if col == "TOT.":
        s = f"{n:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        if s.endswith(",00"):
            s = s[:-3]
        return f"{s} €"
    if col in ("MD +", "MD -"):
        return f"{n:.2f}".replace(".", ",")
    return f"{int(n)}" if n.is_integer() else f"{n}".replace(".", ",")


COLONNE = ["P", "W", "L", "% W", "TOT.", "MD +", "MD -", "EV W", "EV L", "% EV"]


def calcola_totali(celle, giornate):
    """Somma tutte le Giornate. %W = W/P, %EV = EV W/EV L, MD+/MD- = medie pesate su W/L."""
    tot = {}
    for strat in ("EXTRA", "COPILOTA"):
        acc = {k: 0.0 for k in ("P", "W", "L", "TOT.", "EV W", "EV L")}
        somma_plus = somma_minus = 0.0
        ha_ev = False
        for r0 in giornate:
            d = estrai_giornata(celle, r0)[strat]
            for k in acc:
                n = _num(d[k])
                if n is not None:
                    acc[k] += n
                    if k in ("EV W", "EV L"):
                        ha_ev = True
            w, l = _num(d["W"]) or 0.0, _num(d["L"]) or 0.0
            somma_plus += (_num(d["MD +"]) or 0.0) * w
            somma_minus += (_num(d["MD -"]) or 0.0) * l
        res = dict(acc)
        res["% W"] = acc["W"] / acc["P"] if acc["P"] else None
        res["MD +"] = somma_plus / acc["W"] if acc["W"] else None
        res["MD -"] = somma_minus / acc["L"] if acc["L"] else None
        if ha_ev:
            res["% EV"] = acc["EV W"] / acc["EV L"] if acc["EV L"] else None
        else:
            res["EV W"] = res["EV L"] = res["% EV"] = None
        tot[strat] = res
    return tot


_CSS = """
<style>
.xt-wrap { background: linear-gradient(145deg,#0b0b0b,#161616); border: 2px solid #FFD700;
           border-radius: 12px; padding: 14px 18px; box-shadow: 0 0 22px rgba(255,215,0,0.25);
           margin-bottom: 18px; }
.xt-title { color:#FFD700; font-size:1.35rem; font-weight:900; letter-spacing:1px; margin-bottom:10px; }
.xt-title span { color:#ccc; font-size:1rem; font-weight:600; margin-left:10px; }
table.xt-tab { width:100%; border-collapse:collapse; font-size:1.15rem; }
table.xt-tab th { color:#FFD700; background:#1f1a00; padding:10px 8px; text-align:center;
                  border-bottom:2px solid #FFD700; white-space:nowrap; font-weight:800; }
table.xt-tab th.xt-mdp { min-width:80px; }
table.xt-tab td { color:#f2f2f2; padding:10px 8px; text-align:center; border-bottom:1px solid #333;
                  white-space:nowrap; font-weight:600; }
table.xt-tab tr:hover td { background:#1c1c1c; }
td.xt-strat { color:#FFD700 !important; font-weight:900 !important; text-align:left !important; }
td.xt-pos { color:#22c55e !important; font-weight:800 !important; }
td.xt-neg { color:#ef4444 !important; font-weight:800 !important; }
table.xt-tab th.xt-sep, table.xt-tab td.xt-sep { border-left:2px solid #8a7400; }
.xt-small { padding: 10px 14px; }
.xt-small .xt-title { font-size:1.15rem; margin-bottom:8px; }
.xt-small table.xt-tab { font-size:0.98rem; }
.xt-small table.xt-tab th, .xt-small table.xt-tab td { padding:7px 6px; }
.xt-mini { padding: 6px 10px; margin-bottom: 8px; border-width:1px; box-shadow: 0 0 8px rgba(255,215,0,0.15); }
.xt-mini .xt-title { font-size:0.85rem; margin-bottom:4px; }
.xt-mini .xt-title span { font-size:0.8rem; }
.xt-mini table.xt-tab { font-size:0.75rem; }
.xt-mini table.xt-tab th, .xt-mini table.xt-tab td { padding:3px 4px; }
.xt-mini table.xt-tab th { border-bottom-width:1px; }
.xt-mini table.xt-tab th.xt-mdp { min-width:50px; }
.xt-sez { color:#FFD700; font-size:0.95rem; font-weight:800; margin:14px 0 8px 2px; letter-spacing:1px; }
</style>
"""


def _tabella_html(titolo, sottotitolo, dati, extra_cls=""):
    righe_html = ""
    for strat in ("EXTRA", "COPILOTA"):
        celle_html = f"<td class='xt-strat'>{strat}</td>"
        for col in COLONNE:
            val = _fmt(col, dati[strat][col])
            classi = []
            if col == "TOT.":
                n = _num(dati[strat][col])
                if n is not None and n != 0:
                    classi.append("xt-pos" if n > 0 else "xt-neg")
            if col == "EV W":
                classi.append("xt-sep")
            cls = f" class='{' '.join(classi)}'" if classi else ""
            celle_html += f"<td{cls}>{val}</td>"
        righe_html += f"<tr>{celle_html}</tr>"
    def _th(c):
        if c == "MD +":
            return f"<th class='xt-mdp'>{c}</th>"
        if c == "EV W":
            return f"<th class='xt-sep'>{c}</th>"
        return f"<th>{c}</th>"
    head = "<th>STRATEGIA</th>" + "".join(_th(c) for c in COLONNE)
    return (f'<div class="xt-wrap {extra_cls}"><div class="xt-title">{titolo} <span>{sottotitolo}</span></div>'
            f'<table class="xt-tab"><thead><tr>{head}</tr></thead><tbody>{righe_html}</tbody></table></div>')


def renderizza_xtrader():
    path = _trova_file()
    if not path:
        st.error(f"⚠️ File {XTRADER_FILE} non trovato.")
        return
    try:
        celle = _leggi_foglio(path, XTRADER_SHEET)
    except Exception as e:
        st.error(f"⚠️ Errore lettura {XTRADER_FILE}: {e}")
        return

    giornate = trova_giornate(celle)
    if not giornate:
        st.warning("Nessuna Giornata valida trovata.")
        return

    totali = calcola_totali(celle, giornate)
    ultima = estrai_giornata(celle, giornate[-1])
    prima = estrai_giornata(celle, giornate[0])

    def _badge(v):
        c = "#22c55e" if v > 0 else ("#ef4444" if v < 0 else "#ccc")
        return f"<b style='color:{c}; margin-left:18px;'>Totale: {_fmt('TOT.', v)}</b>"

    tot_all = (_num(totali["EXTRA"]["TOT."]) or 0.0) + (_num(totali["COPILOTA"]["TOT."]) or 0.0)
    html = _CSS
    html += _tabella_html("🚀 XTRADER TOTALI",
                          f"{len(giornate)} giornate: dal {prima['data']} al {ultima['data']}{_badge(tot_all)}", totali)
    tot_giorno = (_num(ultima["EXTRA"]["TOT."]) or 0.0) + (_num(ultima["COPILOTA"]["TOT."]) or 0.0)
    html += _tabella_html("🚀 XTRADER", f"Ultima giornata: {ultima['data']}{_badge(tot_giorno)}", ultima, "xt-small")

    if len(giornate) > 1:
        html += "<div class='xt-sez'>📅 GIORNATE PRECEDENTI</div>"
        for r0 in reversed(giornate[:-1]):
            d = estrai_giornata(celle, r0)
            t = (_num(d["EXTRA"]["TOT."]) or 0.0) + (_num(d["COPILOTA"]["TOT."]) or 0.0)
            html += _tabella_html(str(d["data"]), _badge(t), d, "xt-mini")
    st.markdown(html, unsafe_allow_html=True)
