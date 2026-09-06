import subprocess, sys

script = """
import sys, json, os, glob
sys.argv = ['Motore_Trend.py', 'FIORDOK_DEMO']
sys.path.append('/data')
import Motore_Trend

with open('/data/FIORDOK_DEMO/radar_trend.json') as f:
    rad = json.load(f)
print('FIORDOK_DEMO radar_trend for USD/JPY:')
print(json.dumps(rad.get('radar_trend', {}).get('USD/JPY', {}), indent=2))

for tf in ['MINUTE_5', 'HOUR', 'HOUR_4', 'DAY']:
    fnames = glob.glob('/data/*/candele_USD_JPY_' + tf + '.json')
    print('=== TF:', tf, '(Files:', len(fnames), ') ===')
    for fn in fnames:
        with open(fn) as f: d = json.load(f)
        kj = Motore_Trend.calcola_kj55_da_candele(d, 55)
        first_t = d[0].get('snapshotTime') if d else None
        last_t = d[-1].get('snapshotTime') if d else None
        print(' ', fn, 'len:', len(d), 'KJ:', kj, 'first:', first_t, 'last:', last_t)
"""

out = subprocess.run(['kubectl.exe', '--kubeconfig=local.yaml', '-n', 'macchinetta', 'exec', 'deployment/macchinetta-dashboard', '--', 'python3', '-c', script], capture_output=True)
sys.stdout.buffer.write(out.stdout)
if out.stderr:
    sys.stderr.buffer.write(out.stderr)
