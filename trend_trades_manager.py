import os
import json
import re
import time
import datetime
try:
    from zoneinfo import ZoneInfo
    TZ_ITALIA = ZoneInfo("Europe/Rome")
except Exception:
    TZ_ITALIA = datetime.timezone(datetime.timedelta(hours=2))

def now_it():
    return datetime.datetime.now(TZ_ITALIA)

FILE_TREND_TRADES = "trend_trades_history.json"
FILE_MEMORIA_TREND = "memoria_trend.json"
FILE_MEMORIA = "memoria_parametri.json"

TUTTI_STRUMENTI_TREND = [
    "AUD/NZD", "CAD/JPY", "EUR/JPY", "GBP/JPY", "GBP/USD", 
    "USD/CAD", "USD/CHF", "USD/JPY", "Spot Gold", "US 500 Cash", "CHF/JPY"
]

def _resolve_history_path(conto: str = None) -> str:
    """Restituisce il percorso corretto del file trend_trades_history.json."""
    if conto and os.path.isdir(conto):
        return os.path.join(conto, FILE_TREND_TRADES)
    # Se il conto è già la directory corrente o siamo nel pod del conto
    if os.path.exists(FILE_MEMORIA_TREND) or os.path.exists(FILE_MEMORIA) or os.path.exists(FILE_TREND_TRADES):
        return FILE_TREND_TRADES
    if conto:
        return os.path.join(conto, FILE_TREND_TRADES)
    return FILE_TREND_TRADES

def _resolve_memoria_path(conto: str = None) -> str:
    """Restituisce il percorso di memoria_trend.json (o fallback a memoria_parametri.json)."""
    if conto and os.path.isdir(conto):
        p_trend = os.path.join(conto, FILE_MEMORIA_TREND)
        if os.path.exists(p_trend):
            return p_trend
        return os.path.join(conto, FILE_MEMORIA)
    if os.path.exists(FILE_MEMORIA_TREND):
        return FILE_MEMORIA_TREND
    return FILE_MEMORIA

def salva_trade_chiuso_trend(conto: str, trade_dict: dict) -> bool:
    """Salva in modo persistente un trade concluso in trend_trades_history.json."""
    filepath = _resolve_history_path(conto)
    try:
        now_str = now_it().strftime("%Y-%m-%d %H:%M:%S")
        tc = trade_dict.get("time_close") or now_str
        to = trade_dict.get("time_open") or ""
        
        trade_id = trade_dict.get("id") or str(int(time.time() * 1000))
        item = {
            "id": trade_id,
            "time_open": to,
            "time_close": tc,
            "instrument": trade_dict.get("instrument", "--"),
            "epic": trade_dict.get("epic", "--"),
            "direction": trade_dict.get("direction", "--"),
            "contracts": float(trade_dict.get("contracts", 1.0)),
            "open_price": float(trade_dict.get("open_price", 0.0) or 0.0),
            "close_price": float(trade_dict.get("close_price", 0.0) or 0.0),
            "pnl_eur": round(float(trade_dict.get("pnl_eur", 0.0) or 0.0), 2),
            "deal_id": trade_dict.get("deal_id", "--"),
            "reason": trade_dict.get("reason", "Chiusura Trend")
        }

        trades = []
        if os.path.exists(filepath):
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    trades = json.load(f)
                    if not isinstance(trades, list):
                        trades = []
            except Exception:
                trades = []

        # Evita duplicati identici se già salvato
        is_dup = False
        for t in trades:
            if (item["deal_id"] not in ("--", "") and 
                t.get("deal_id") == item["deal_id"]):
                is_dup = True
                break
            if (t.get("instrument") == item["instrument"] and 
                t.get("time_close") == item["time_close"] and 
                abs(t.get("pnl_eur", 0.0) - item["pnl_eur"]) < 0.01 and 
                t.get("reason") == item["reason"]):
                is_dup = True
                break

        if not is_dup:
            trades.insert(0, item)
            trades = deduplica_trades_trend(trades)[:2000] # Limite max 2000 trade

            tmp_path = f"{filepath}.tmp.{os.getpid()}"
            try:
                with open(tmp_path, "w", encoding="utf-8") as f:
                    json.dump(trades, f, indent=2)
                os.replace(tmp_path, filepath)
            except Exception:
                with open(filepath, "w", encoding="utf-8") as f:
                    json.dump(trades, f, indent=2)
        return True
    except Exception as e:
        print(f"Errore salvataggio trade Trend in {filepath}: {e}")
        return False

def deduplica_trades_trend(trades: list) -> list:
    """
    Rimuove trade duplicati:
    1. Se per lo stesso strumento e periodo (entro 300 secondi) esistono sia un trade reale (con deal_id o id nativo)
       sia un trade estratto da WIP (id fittizio 'wip_...'), tiene esclusivamente il trade reale.
    2. Se per lo stesso deal_id valido esistono più record, tiene solo il primo.
    3. Se due record hanno stesso strumento, time_close, pnl_eur e reason, tiene solo il primo.
    """
    if not trades:
        return []

    reals = [t for t in trades if not str(t.get("id", "")).startswith("wip_")]
    wips = [t for t in trades if str(t.get("id", "")).startswith("wip_")]

    visti_deal = set()
    reals_unici = []
    for r in reals:
        d_id = r.get("deal_id", "--")
        if d_id and d_id != "--":
            if d_id in visti_deal:
                continue
            visti_deal.add(d_id)
        reals_unici.append(r)

    wips_filtrati = []
    for w in wips:
        w_inst = w.get("instrument")
        try:
            w_time = datetime.datetime.fromisoformat(w.get("time_close", ""))
        except Exception:
            w_time = None
        w_pnl = float(w.get("pnl_eur", 0.0) or 0.0)

        is_clone = False
        if w_time is not None:
            for r in reals_unici:
                if r.get("instrument") != w_inst:
                    continue
                try:
                    r_time = datetime.datetime.fromisoformat(r.get("time_close", ""))
                except Exception:
                    continue
                r_pnl = float(r.get("pnl_eur", 0.0) or 0.0)
                # Stesso strumento entro 300s e PnL entro 3.0 €
                if abs((r_time - w_time).total_seconds()) <= 300 and abs(r_pnl - w_pnl) <= 3.0:
                    is_clone = True
                    break
        if not is_clone:
            wips_filtrati.append(w)

    unione = reals_unici + wips_filtrati
    visti_chiavi = set()
    risultato = []
    for t in sorted(unione, key=lambda x: str(x.get("time_close", "")), reverse=True):
        k = (t.get("instrument"), t.get("time_close"), round(float(t.get("pnl_eur", 0.0) or 0.0), 2), t.get("reason"))
        if k in visti_chiavi:
            continue
        visti_chiavi.add(k)
        risultato.append(t)

    return risultato

def _estrai_trades_da_storico_wip(conto: str = None) -> list:
    """Estrae lo storico delle chiusure registrate in storico_wip_trend di ciascuno strumento."""
    mem_path = _resolve_memoria_path(conto)
    if not os.path.exists(mem_path):
        return []
    
    extracted = []
    try:
        with open(mem_path, "r", encoding="utf-8") as f:
            memoria = json.load(f)
    except Exception:
        return []

    anno_corrente = now_it().year

    for strum, dati in memoria.items():
        if not isinstance(dati, dict):
            continue
        storico = dati.get("storico_wip_trend", [])
        if not storico:
            continue
        
        dir_t = dati.get("direzione", "LONG")
        sz_default = float(dati.get("size", dati.get("size_i", 1.0)))

        for riga in storico:
            m_pnl = re.search(r"\[PnL:\s*([+-]?\d+(?:[\.,]\d+)?)\s*€\]", riga)
            if not m_pnl:
                continue
            
            pnl_val = float(m_pnl.group(1).replace(",", "."))

            # Estrai data/ora [DD/MM HH:MM:SS] o [YYYY-MM-DD HH:MM:SS]
            m_time = re.search(r"\[(\d{1,2}/\d{1,2}(?:/\d{2,4})?\s+\d{2}:\d{2}:\d{2})\]", riga)
            if m_time:
                raw_time = m_time.group(1)
                parts = raw_time.split(" ")
                date_part = parts[0]
                time_part = parts[1]
                dp = date_part.split("/")
                if len(dp) == 2:
                    d_day, d_mon = int(dp[0]), int(dp[1])
                    d_year = anno_corrente
                else:
                    d_day, d_mon = int(dp[0]), int(dp[1])
                    d_year = int(dp[2]) if len(dp[2]) == 4 else (2000 + int(dp[2]))
                time_close = f"{d_year:04d}-{d_mon:02d}-{d_day:02d} {time_part}"
            else:
                m_time_iso = re.search(r"\[(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\]", riga)
                time_close = m_time_iso.group(1) if m_time_iso else now_it().strftime("%Y-%m-%d %H:%M:%S")

            # Estrai Prezzo di chiusura: a 209.50 oppure @ 209.50
            m_px = re.search(r"(?:a|@)\s+([0-9]+(?:\.[0-9]+)?)", riga)
            close_px = float(m_px.group(1)) if m_px else 0.0

            # Estrai contratti (size)
            m_sz = re.search(r"\(([0-9]+(?:\.[0-9]+)?)\)", riga)
            contracts = float(m_sz.group(1)) if m_sz else sz_default

            # Estrai motivo
            clean_msg = re.sub(r"^\[.*?\]\s*", "", riga).strip()
            clean_msg = re.sub(r"\s*\[PnL:.*?\]", "", clean_msg).strip()
            clean_msg = clean_msg.replace("➡️ FLAT", "").strip()

            extracted.append({
                "id": f"wip_{abs(hash(strum + time_close + str(pnl_val)))}",
                "time_open": "",
                "time_close": time_close,
                "instrument": strum,
                "epic": dati.get("epic", "--"),
                "direction": dir_t,
                "contracts": contracts,
                "open_price": 0.0,
                "close_price": close_px,
                "pnl_eur": round(pnl_val, 2),
                "deal_id": "--",
                "reason": clean_msg or "Chiusura Trend"
            })

    return extracted

def carica_trades_trend(conto: str = None) -> list:
    """Carica la lista ordinata (la più recente per prima, la più vecchia per ultima) dei trade chiusi Trend."""
    filepath = _resolve_history_path(conto)
    trades = []
    
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    trades = data
        except Exception:
            trades = []

    # Bootstrap da storico_wip solo se l'archivio è completamente vuoto
    if not trades:
        wip_trades = _estrai_trades_da_storico_wip(conto)
        if wip_trades:
            trades = wip_trades

    # Deduplica sempre per proteggere da cloni o disallineamenti
    trades_puliti = deduplica_trades_trend(trades)

    # Se la lista è cambiata (es. duplicati rimossi o bootstrap iniziale), aggiorna il file su disco
    if len(trades_puliti) != len(trades) or (not os.path.exists(filepath) and trades_puliti):
        try:
            tmp_path = f"{filepath}.tmp.{os.getpid()}"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(trades_puliti, f, indent=2)
            os.replace(tmp_path, filepath)
        except Exception:
            try:
                with open(filepath, "w", encoding="utf-8") as f:
                    json.dump(trades_puliti, f, indent=2)
            except Exception:
                pass

    return trades_puliti

def azzera_trades_trend(conto: str = None, strumento: str = None) -> bool:
    """Azzera l'archivio trade (globale o per singolo strumento)."""
    filepath = _resolve_history_path(conto)
    if not os.path.exists(filepath):
        return True
    try:
        if strumento:
            trades = carica_trades_trend(conto)
            rimasti = [t for t in trades if t.get("instrument") != strumento]
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(rimasti, f, indent=2)
        else:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump([], f, indent=2)
        return True
    except Exception as e:
        print(f"Errore azzeramento trade Trend: {e}")
        return False
