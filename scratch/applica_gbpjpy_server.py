import json
import os

def aggiorna():
    accounts = ['FIORDOK_DEMO', 'DANY_DEMO', 'BONGIOLO_DEMO']
    for acc in accounts:
        mem_file = f'/data/{acc}/memoria_parametri.json'
        if not os.path.exists(mem_file):
            print(f'File {mem_file} non trovato.')
            continue
            
        with open(mem_file, 'r') as f:
            mem = json.load(f)
            
        if 'EUR/GBP' in mem:
            del mem['EUR/GBP']
            
        c_m5 = []
        c_path = f'/data/{acc}/candele_GBP_JPY_MINUTE_5.json'
        if os.path.exists(c_path):
            with open(c_path) as f:
                c_m5 = json.load(f)
                
        kj_m5 = None
        tk_m5 = None
        if len(c_m5) >= 55:
            sub55 = c_m5[-55:]
            kj_m5 = (max(c['highPrice']['bid'] for c in sub55) + min(c['lowPrice']['bid'] for c in sub55)) / 2.0
        if len(c_m5) >= 21:
            sub21 = c_m5[-21:]
            tk_m5 = (max(c['highPrice']['bid'] for c in sub21) + min(c['lowPrice']['bid'] for c in sub21)) / 2.0
            
        mem['GBP/JPY'] = {
            "attivo": False,
            "direzione": "SHORT",
            "tp": 80,
            "opp": 20,
            "dts": 15,
            "size": 3,
            "stato": "FLAT",
            "storico_wip": [],
            "errore_avvio": False,
            "errore_ripristino": False,
            "comando_manuale": False,
            "msg_manuale": "",
            "prezzo_base": 0.0,
            "sospeso_rollover": False,
            "rollover_snapshot": {},
            "tentativi_ripristino": 0,
            "pausa_mercato": False,
            "stats": {
                "Micro": {"pnl": 0.0, "totale": 0, "profit": 0, "loss": 0},
                "Flip": {"pnl": 0.0, "totale": 0, "profit": 0, "loss": 0},
                "Ticket1": {"pnl": 0.0, "totale": 0, "profit": 0, "loss": 0},
                "Ticket2": {"pnl": 0.0, "totale": 0, "profit": 0, "loss": 0},
                "OverGain": {"pnl": 0.0, "totale": 0, "profit": 0, "loss": 0},
                "OverLoss": {"pnl": 0.0, "totale": 0, "profit": 0, "loss": 0},
                "Ultima": {"pnl": 0.0, "totale": 0, "profit": 0, "loss": 0},
                "Fase3": {"pnl": 0.0, "totale": 0, "profit": 0, "loss": 0},
                "Assicurazione": {"pnl": 0.0, "totale": 0, "profit": 0, "loss": 0}
            },
            "ticket2_active": False,
            "kill_switch": False,
            "sospeso_weekend": False,
            "tipo_strategia": "TREND",
            "allarme_distanza": False,
            "timeframe": "MINUTE_5",
            "size_max": 5,
            "scala": 1,
            "min_body": 5,
            "auto_restart": False,
            "storico_wip_trend": [],
            "posizioni_core": [],
            "posizioni_incr": [],
            "trailing_sl_core": None,
            "trailing_sl_incr": None,
            "needs_manual_start": False,
            "current_tk": tk_m5,
            "current_kj": kj_m5,
            "last_candle_time": c_m5[-1]['snapshotTime'] if c_m5 else ""
        }
        
        with open(mem_file, 'w') as f:
            json.dump(mem, f, indent=4)
        print(f"[OK] {acc}: memoria_parametri.json aggiornata con GBP/JPY (totale {len(mem)} strumenti).")
        
        for tf in ['MINUTE_5', 'HOUR', 'HOUR_4', 'DAY']:
            old_f = f'/data/{acc}/candele_EUR_GBP_{tf}.json'
            if os.path.exists(old_f):
                try:
                    os.remove(old_f)
                    print(f"Rimosso vecchio file {old_f}")
                except Exception as e:
                    print(f"Errore rimozione {old_f}: {e}")

if __name__ == "__main__":
    aggiorna()
