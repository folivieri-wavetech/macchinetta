import subprocess, sys

script = """
import json, glob
for p in glob.glob('/data/*/memoria_parametri.json'):
    with open(p) as f:
        d = json.load(f)
    print('===', p, '===')
    for k, v in d.items():
        if v.get('tipo_strategia') == 'TREND' or v.get('timeframe') or v.get('attivo'):
            print(f"{k}: Strat={v.get('tipo_strategia')} TF={v.get('timeframe')} Attivo={v.get('attivo')} Stato={v.get('stato')} TK={v.get('current_tk')} KJ={v.get('current_kj')} LastCandle={v.get('last_candle_time')}")
"""

out = subprocess.run(['kubectl.exe', '--kubeconfig=local.yaml', '-n', 'macchinetta', 'exec', 'deployment/macchinetta-dashboard', '--', 'python3', '-c', script], capture_output=True, text=True)
print(out.stdout)
if out.stderr:
    print(out.stderr, file=sys.stderr)
