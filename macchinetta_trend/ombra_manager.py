import os
import json
import time
import uuid
import datetime

try:
    from Sistema.fuso_orario import TZ_ITALIA, now_it
except ImportError:
    try:
        from fuso_orario import TZ_ITALIA, now_it
    except ImportError:
        try:
            from zoneinfo import ZoneInfo
            TZ_ITALIA = ZoneInfo("Europe/Rome")
        except Exception:
            TZ_ITALIA = datetime.timezone(datetime.timedelta(hours=1))
        def now_it():
            return datetime.datetime.now(TZ_ITALIA)

FILE_OMBRA = "ombra_trend.json"
CONTI_OMBRA_ABILITATI = ("DANY_DEMO", "BONGIOLO_DEMO", "FIORDOK_DEMO")


def _resolve_ombra_path(conto: str = None) -> str:
    """Restituisce il percorso del file ombra_trend.json per il conto specificato."""
    if conto and os.path.isdir(conto):
        return os.path.join(conto, FILE_OMBRA)
    if conto:
        return os.path.join(conto, FILE_OMBRA)
    return FILE_OMBRA


def carica_ombra(conto: str = None) -> dict:
    """Carica le operazioni Ombra attive e chiuse del conto."""
    path = _resolve_ombra_path(conto)
    default_data = {"attive": {}, "chiuse": []}
    if not os.path.exists(path):
        return default_data
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return default_data
        if "attive" not in data or not isinstance(data["attive"], dict):
            data["attive"] = {}
        if "chiuse" not in data or not isinstance(data["chiuse"], list):
            data["chiuse"] = []
        return data
    except Exception:
        return default_data


def salva_ombra(conto: str, data: dict) -> bool:
    """Salva atomicamente lo stato Ombra su disco."""
    path = _resolve_ombra_path(conto)
    parent = os.path.dirname(path)
    if parent and not os.path.exists(parent):
        try:
            os.makedirs(parent, exist_ok=True)
        except Exception:
            pass
    tmp = f"{path}.tmp.{os.getpid()}_{uuid.uuid4().hex[:8]}"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, path)
        return True
    except Exception:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except Exception:
            pass
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            return True
        except Exception:
            return False


def calcola_pnl_eur_ombra(
    nome: str,
    direction: str,
    entry_price: float,
    current_price: float,
    size: float,
    prezzi_live: dict,
    config_strumenti: dict,
    get_eur_rate_fn
) -> float:
    """Calcola il controvalore P/L in EUR per una posizione Ombra."""
    try:
        c_cfg = config_strumenti.get(nome, {})
        mult = float(c_cfg.get("moltiplicatore", 0.0001) or 0.0001)
        valore_punto = float(c_cfg.get("valore_punto", 1.0) or 1.0)
        valuta = c_cfg.get("valuta", "USD")
        rate = float(get_eur_rate_fn(valuta, prezzi_live or {}) or 1.0)
        entry_f = float(entry_price or 0.0)
        curr_f = float(current_price or 0.0)
        sz_f = float(size or 0.0)
        if entry_f <= 0 or curr_f <= 0 or sz_f <= 0:
            return 0.0
        raw_diff = (curr_f - entry_f) if str(direction).upper() == "LONG" else (entry_f - curr_f)
        return round((raw_diff / mult) * valore_punto * rate, 2)
    except Exception:
        return 0.0


def calcola_margine_ombra(campagna: dict, config_strumenti: dict) -> float:
    """Calcola il margine teorico utilizzato esclusivamente in Ombra (Core + Incrementi aperti)."""
    try:
        nome = campagna.get("nome", "")
        c_cfg = config_strumenti.get(nome, {})
        marg_u = float(c_cfg.get("margine_unitario", 300) or 300)
        tot_size = sum(float(p.get("size", 0) or 0) for p in campagna.get("posizioni_core", []))
        tot_size += sum(float(p.get("size", 0) or 0) for p in campagna.get("posizioni_incr", []))
        return round(tot_size * marg_u, 2)
    except Exception:
        return 0.0


def crea_operazione_ombra(
    conto: str,
    nome: str,
    timeframe: str,
    direzione: str,
    size: float,
    entry_price: float,
    data_inizio_str: str,
    size_max: float = 10.0,
    scala: int = 2,
    min_body: int = 10
) -> str:
    """Crea e registra una nuova operazione Core Ombra sul conto demo."""
    oid = f"OMBRA_{uuid.uuid4().hex[:8].upper()}"
    now_ts = time.time()
    ora_str = now_it().strftime("%d/%m %H:%M:%S")
    dir_clean = str(direzione).upper().strip()
    sz_clean = float(size)
    sz_max_clean = float(max(float(size_max), sz_clean))
    scala_clean = int(max(1, int(scala)))
    entry_clean = float(entry_price)

    campagna = {
        "id": oid,
        "nome": nome,
        "timeframe": timeframe,
        "direzione": dir_clean,
        "size": sz_clean,
        "size_max": sz_max_clean,
        "scala": scala_clean,
        "min_body": int(min_body),
        "entry_price": entry_clean,
        "data_inizio": str(data_inizio_str),
        "created_ts": now_ts,
        "posizioni_core": [
            {
                "entry": entry_clean,
                "size": sz_clean,
                "type": "core",
                "direction": dir_clean,
                "ticket": f"{oid}_CORE",
                "opened_at": now_ts
            }
        ],
        "posizioni_incr": [],
        "pnl_realizzato_inc_eur": 0.0,
        "trailing_sl_incr": None,
        "trailing_sl_core": None,
        "signal_candle_active": False,
        "signal_stop_price": None,
        "signal_candle_tk_active": False,
        "signal_stop_price_tk": None,
        "current_tk": None,
        "current_kj": None,
        "last_candle_time": "",
        "storico": [
            f"[{ora_str}] 👤 Avvio Ombra Core {dir_clean} ({sz_clean:g}) @ {entry_clean} (Rif. Data: {data_inizio_str})"
        ]
    }

    data = carica_ombra(conto)
    data["attive"][oid] = campagna
    salva_ombra(conto, data)
    return oid


def chiudi_ombra_su_storico(
    conto: str,
    oid: str,
    close_price: float,
    motivo: str,
    prezzi_live: dict,
    config_strumenti: dict,
    get_eur_rate_fn,
    pnl_core_override: float = None,
    updated_campagna: dict = None
) -> bool:
    """Sposta una campagna Ombra attiva nello storico delle chiuse calcolando i P/L finali."""
    data = carica_ombra(conto)
    campagna = data["attive"].pop(oid, None)
    if not campagna:
        return False
    if updated_campagna:
        campagna = updated_campagna

    nome = campagna.get("nome", "")
    ora_str = now_it().strftime("%d/%m %H:%M:%S")
    data_chiusura_str = now_it().strftime("%Y-%m-%d %H:%M:%S")

    core_list = campagna.get("posizioni_core", [])
    incr_list = campagna.get("posizioni_incr", [])
    px_close = float(close_price or 0.0)
    if px_close <= 0 and isinstance((prezzi_live or {}).get(nome), (int, float)):
        px_close = float(prezzi_live[nome])
    if px_close <= 0:
        px_close = float(campagna.get("entry_price", 0.0) or 0.0)

    if pnl_core_override is not None:
        pnl_core_eur = round(float(pnl_core_override), 2)
    else:
        pnl_core_eur = 0.0
        for cp in core_list:
            pnl_core_eur += calcola_pnl_eur_ombra(
                nome,
                cp.get("direction", campagna.get("direzione", "LONG")),
                cp.get("entry", campagna.get("entry_price", 0.0)),
                px_close,
                cp.get("size", campagna.get("size", 1.0)),
                prezzi_live,
                config_strumenti,
                get_eur_rate_fn
            )
        pnl_core_eur = round(pnl_core_eur, 2)

    pnl_inc_aperti_eur = 0.0
    for ip in incr_list:
        pnl_inc_aperti_eur += calcola_pnl_eur_ombra(
            nome,
            ip.get("direction", campagna.get("direzione", "LONG")),
            ip.get("entry", 0.0),
            px_close,
            ip.get("size", 1.0),
            prezzi_live,
            config_strumenti,
            get_eur_rate_fn
        )

    pnl_inc_tot_eur = round(float(campagna.get("pnl_realizzato_inc_eur", 0.0) or 0.0) + pnl_inc_aperti_eur, 2)
    pnl_totale_eur = round(pnl_core_eur + pnl_inc_tot_eur, 2)

    storico = list(campagna.get("storico", []))
    storico.append(f"[{ora_str}] 🏁 Chiusura Ombra Core ({motivo}) @ {px_close} [PnL Totale: {pnl_totale_eur:+.2f} €]")

    record_chiuso = {
        "id": oid,
        "nome": nome,
        "timeframe": campagna.get("timeframe", "HOUR"),
        "direzione": campagna.get("direzione", "LONG"),
        "size": float(campagna.get("size", 1.0)),
        "entry_price": float(campagna.get("entry_price", 0.0)),
        "close_price": px_close,
        "data_inizio": campagna.get("data_inizio", ""),
        "data_chiusura": data_chiusura_str,
        "motivo_chiusura": motivo,
        "pnl_core_eur": pnl_core_eur,
        "pnl_inc_eur": pnl_inc_tot_eur,
        "pnl_totale_eur": pnl_totale_eur,
        "storico": storico[-50:]
    }
    data["chiuse"].insert(0, record_chiuso)
    data["chiuse"] = data["chiuse"][:200]
    return salva_ombra(conto, data)


def elimina_storico_ombra(conto: str, oid: str = None) -> bool:
    """Elimina una singola voce o l'intero storico delle operazioni Ombra chiuse."""
    data = carica_ombra(conto)
    if oid:
        data["chiuse"] = [c for c in data["chiuse"] if c.get("id") != oid]
    else:
        data["chiuse"] = []
    return salva_ombra(conto, data)
