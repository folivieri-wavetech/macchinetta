import subprocess

script = """
import requests, json

# Read token
with open('/data/DANY_DEMO/token_ig.json') as f:
    tok = json.load(f)

cst = tok['CST']
sec = tok['X-SECURITY-TOKEN']
headers = {
    'X-IG-API-KEY': 'YOUR_KEY', # let's check .env
    'CST': cst,
    'X-SECURITY-TOKEN': sec,
    'Version': '3'
}

# Let's use Motore_Trend scarica_candele directly
import sys
sys.path.append('/data')
sys.argv = ['Motore_Trend.py', 'DANY_DEMO']
import Motore_Trend
h = Motore_Trend.ottieni_headers_ig()
prices = Motore_Trend.scarica_candele('CS.D.USDCHF.MINI.IP', 'MINUTE_5', limit=60, headers=h)
print(f"Prices fetched: {len(prices) if isinstance(prices, list) else prices}")
if isinstance(prices, list) and prices:
    print("First candle:", prices[0]['snapshotTime'])
    print("Last candle:", prices[-1]['snapshotTime'])
    recent21 = prices[-21:]
    highs = [float(c['highPrice']['bid']) for c in recent21]
    lows = [float(c['lowPrice']['bid']) for c in recent21]
    h21 = max(highs)
    l21 = min(lows)
    tk21 = (h21 + l21) / 2
    print(f"Recent 21: MinLow={l21:.5f}, MaxHigh={h21:.5f} -> TK={tk21:.5f}")

    recent55 = prices[-55:]
    h55 = max(float(c['highPrice']['bid']) for c in recent55)
    l55 = min(float(c['lowPrice']['bid']) for c in recent55)
    kj55 = (h55 + l55) / 2
    print(f"Recent 55: MinLow={l55:.5f}, MaxHigh={h55:.5f} -> KJ={kj55:.5f}")
"""

out = subprocess.run(['kubectl.exe', '--kubeconfig=local.yaml', '-n', 'macchinetta', 'exec', 'deployment/macchinetta-dashboard', '--', 'python3', '-c', script], capture_output=True, text=True)
print(out.stdout)
if out.stderr:
    print(out.stderr)
