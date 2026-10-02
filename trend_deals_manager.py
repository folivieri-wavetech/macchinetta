import os
import json
import time
import logging

logger = logging.getLogger("TrendDealsManager")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

TREND_DEALS_FILENAME = "trend_active_deals.json"

def get_trend_deals_file(account_dir: str = None) -> str:
    """Restituisce il percorso del file di stato persistente dei deal registrati da Trend."""
    if account_dir:
        return os.path.join(account_dir, TREND_DEALS_FILENAME)
    return TREND_DEALS_FILENAME

def carica_deal_trend(account_dir: str = None) -> dict:
    """Carica il dizionario {epic: [deal_id, ...]} dal file persistente."""
    fpath = get_trend_deals_file(account_dir)
    if not os.path.exists(fpath):
        return {}
    for _ in range(5):
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                d = json.load(f)
                if isinstance(d, dict):
                    return d
                return {}
        except Exception:
            time.sleep(0.05)
    return {}

def salva_deal_trend(account_dir: str, data: dict) -> bool:
    """Salva il dizionario dei deal Trend in modo atomico su disco."""
    fpath = get_trend_deals_file(account_dir)
    target_dir = os.path.dirname(fpath)
    if target_dir and not os.path.exists(target_dir):
        try:
            os.makedirs(target_dir, exist_ok=True)
        except Exception:
            pass
    tmp_path = f"{fpath}.tmp.{os.getpid()}.{time.time()}"
    for _ in range(5):
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, fpath)
            return True
        except Exception:
            time.sleep(0.05)
    if os.path.exists(tmp_path):
        try:
            os.remove(tmp_path)
        except Exception:
            pass
    return False

def registra_deal_trend(account_dir: str, epic: str, deal_id: str, label: str = "") -> bool:
    """Registra in modo permanente un nuovo dealId generato da Trend per quell'epic."""
    if not epic or not deal_id:
        return False
    deal_s = str(deal_id).strip()
    epic_s = str(epic).strip()
    data = carica_deal_trend(account_dir)
    if epic_s not in data:
        data[epic_s] = []
    if deal_s not in data[epic_s]:
        data[epic_s].append(deal_s)
        ok = salva_deal_trend(account_dir, data)
        if ok:
            logger.info(f"🏷️ [TREND MARCHIO REGISTRATO] Conto: {account_dir} | Epic: {epic_s} | dealId: {deal_s} | {label}")
            return True
    return True

def rimuovi_deal_trend(account_dir: str, epic: str, deal_id: str, label: str = "") -> bool:
    """Rimuove un dealId dal registro di Trend quando la posizione viene chiusa."""
    if not deal_id:
        return False
    deal_s = str(deal_id).strip()
    epic_s = str(epic).strip() if epic else None
    data = carica_deal_trend(account_dir)
    modificato = False
    
    if epic_s and epic_s in data:
        if deal_s in data[epic_s]:
            data[epic_s].remove(deal_s)
            modificato = True
        if not data[epic_s]:
            del data[epic_s]
    else:
        # Cerca su tutti gli epic se epic_s non fornito o non trovato
        for ep, d_list in list(data.items()):
            if deal_s in d_list:
                d_list.remove(deal_s)
                modificato = True
                if not d_list:
                    del data[ep]
                    
    if modificato:
        ok = salva_deal_trend(account_dir, data)
        if ok:
            logger.info(f"🏷️ [TREND MARCHIO RIMOSSO] Conto: {account_dir} | dealId: {deal_s} | {label}")
            return True
    return False

def get_tutti_deal_trend_account(account_dir: str = None) -> set:
    """Restituisce un set con tutti i dealId attualmente registrati e attivi per Trend su questo conto."""
    data = carica_deal_trend(account_dir)
    tutti = set()
    for ep, deals in data.items():
        if isinstance(deals, list):
            for d in deals:
                if d:
                    tutti.add(str(d).strip())
    return tutti

def is_deal_trend(account_dir: str, deal_id: str, epic: str = None) -> bool:
    """Verifica istantaneamente se un dealId appartiene alla strategia Trend."""
    if not deal_id:
        return False
    deal_s = str(deal_id).strip()
    data = carica_deal_trend(account_dir)
    if epic:
        return deal_s in data.get(str(epic).strip(), [])
    for d_list in data.values():
        if deal_s in d_list:
            return True
    return False

def sincronizza_deal_trend_con_ig(account_dir: str = None, deal_ids_live_ig: set = None) -> bool:
    """Rimuove dal registro i deal che non risultano piu aperti su IG (es. chiusi da SL, TP o a mano)."""
    if deal_ids_live_ig is None:
        return False
    data = carica_deal_trend(account_dir)
    if not data:
        return False
    modificato = False
    for epic, deals in list(data.items()):
        if isinstance(deals, list):
            deals_vivi = [d for d in deals if str(d).strip() in deal_ids_live_ig]
            if len(deals_vivi) != len(deals):
                rimossi = set(deals) - set(deals_vivi)
                if deals_vivi:
                    data[epic] = deals_vivi
                else:
                    del data[epic]
                modificato = True
                logger.info(f"🧹 [TREND SYNC IG] Rimossi deal non più aperti su IG ({epic}): {rimossi}")
    if modificato:
        return salva_deal_trend(account_dir, data)
    return False

