import sys, json, os, glob
sys.argv = ['Motore_Trend.py', 'FIORDOK_DEMO']
sys.path.insert(0, '/data')
sys.path.insert(0, '.')
import Motore_Trend
from ig_request_manager import ig_api_request

h = Motore_Trend.ottieni_headers_ig()
h["Version"] = "3"
h["Accept"] = "application/json; charset=UTF-8"
for nome, epic in [('Spot Gold', 'CS.D.CFEGOLD.CBE.IP'), ('Oil - US Crude', 'CC.D.CL.UBE.IP')]:
    clean = nome.replace('/', '_').replace(' ', '_')
    url = f"https://demo-api.ig.com/gateway/deal/prices/{epic}?resolution=HOUR&max=60&pageSize=0"
    r = ig_api_request('GET', url, headers=h, timeout=12, logger_func=lambda t, m: print(f"[{t}] {m}"))
    st = r.status_code if r else 'None'
    print(f"Req {nome}: status={st}")
    if r and r.status_code == 200:
        prices = r.json().get('prices', [])
        print(f"  Prices ricevuti da IG: {len(prices)}")
        if len(prices) >= 20:
            pulite = [c for c in prices if " 23:00:00" not in c.get("snapshotTime", "")]
            print(f"  Prices dopo filtro 23:00: {len(pulite)}")
            p_first = pulite[0].get("snapshotTime")
            p_last = pulite[-1].get("snapshotTime")
            print(f"  Prima: {p_first} | Ultima: {p_last}")
            kj = Motore_Trend.calcola_kj55_da_candele(pulite, 55)
            tk = Motore_Trend.calcola_kj55_da_candele(pulite, 21)
            atr = Motore_Trend.calcola_atr_da_candele(pulite, 21)
            dec = Motore_Trend.CONFIG_STRUMENTI.get(nome, {}).get("decimali", 1)
            print(f"  Valori calcolati -> KJ55: {kj:.{dec}f} | TK21: {tk:.{dec}f} | ATR21: {atr:.{dec}f}")
