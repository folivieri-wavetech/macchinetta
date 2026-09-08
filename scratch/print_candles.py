import subprocess, sys

script = """
import json

with open("/data/DANY_DEMO/candele_USD_CHF_MINUTE_5.json") as f:
    candles = json.load(f)

print(f"Total candles: {len(candles)}")
for i, c in enumerate(candles):
    snap = c.get('snapshotTime')
    o = c.get('openPrice', {}).get('bid')
    h = c.get('highPrice', {}).get('bid')
    l = c.get('lowPrice', {}).get('bid')
    cl = c.get('closePrice', {}).get('bid')
    print(f"[{i:2d}] {snap} | O={o} H={h} L={l} C={cl}")
"""

out = subprocess.run(['kubectl.exe', '--kubeconfig=local.yaml', '-n', 'macchinetta', 'exec', 'deployment/macchinetta-dashboard', '--', 'python3', '-c', script], capture_output=True, text=True)
print(out.stdout)
