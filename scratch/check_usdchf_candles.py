import subprocess, sys

script = """
import json, glob, os

def check_file(path):
    if not os.path.exists(path):
        print("Not found:", path)
        return
    with open(path) as f:
        candles = json.load(f)
    print(f"File: {path}, Total candles: {len(candles)}")
    if not candles:
        return
    print(f"First candle: {candles[0].get('snapshotTime')}, Last candle: {candles[-1].get('snapshotTime')}")
    
    # Calculate Donchian for various periods on bid/mid
    for p in [9, 21, 26, 55]:
        recent = candles[-p:] if len(candles) >= p else candles
        highs = [float(c.get('highPrice', {}).get('bid', c.get('high', 0))) for c in recent]
        lows = [float(c.get('lowPrice', {}).get('bid', c.get('low', 0))) for c in recent]
        h = max(highs)
        l = min(lows)
        mid = (h + l) / 2
        print(f"Period {p:2d}: MinLow={l:.5f}, MaxHigh={h:.5f}, Mediana={mid:.5f}")

print("=== DANY_DEMO ===")
check_file("/data/DANY_DEMO/candele_USD_CHF_MINUTE_5.json")

print("\\n=== Checking other accounts or Logs_e_Cache ===")
for p in glob.glob("/data/*/candele_USD_CHF_MINUTE_5.json"):
    if "DANY_DEMO" not in p:
        check_file(p)
"""

out = subprocess.run(['kubectl.exe', '--kubeconfig=local.yaml', '-n', 'macchinetta', 'exec', 'deployment/macchinetta-dashboard', '--', 'python3', '-c', script], capture_output=True, text=True)
print(out.stdout)
if out.stderr:
    print(out.stderr, file=sys.stderr)
