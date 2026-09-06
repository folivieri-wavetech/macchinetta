import subprocess, sys

script = """
import os, sys, json
sys.argv = ['Motore_Trend.py', 'FIORDOK_DEMO']
sys.path.append('/data')
import Motore_Trend

accs = ['DANY_DEMO', 'FIORDOK_DEMO', 'BONGIOLO_DEMO']
tfs = ['MINUTE_5', 'HOUR', 'HOUR_4', 'DAY']
strums = list(Motore_Trend.CONFIG_STRUMENTI.keys())

for nome in strums:
    clean = nome.replace('/', '_').replace(' ', '_')
    for tf in tfs:
        c_yh = Motore_Trend.scarica_candele_yahoo(nome, tf)
        if c_yh and len(c_yh) >= 10:
            for acc in accs:
                fpath = os.path.join('/data', acc, 'candele_' + clean + '_' + tf + '.json')
                with open(fpath, 'w') as fp:
                    json.dump(c_yh[-100:], fp, indent=2)
            last_snap = c_yh[-1].get('snapshotTime')
            print('Refreshed ' + nome + ' ' + tf + ': ' + str(len(c_yh)) + ' bars, last: ' + str(last_snap))

for acc in accs:
    p_mem = os.path.join('/data', acc, 'memoria_parametri.json')
    mem = {}
    if os.path.exists(p_mem):
        with open(p_mem) as fp: mem = json.load(fp)
    p_st = os.path.join('/data', acc, 'stato_sistema.json')
    px_live = {}
    if os.path.exists(p_st):
        with open(p_st) as fp: px_live = json.load(fp).get('prezzi_live', {})
    if px_live:
        Motore_Trend.aggiorna_radar_trend(px_live, mem)

print('ALL FRESH CANDLES STORED AND RADAR RECALCULATED!')
"""

out = subprocess.run(['kubectl.exe', '--kubeconfig=local.yaml', '-n', 'macchinetta', 'exec', 'deployment/macchinetta-dashboard', '--', 'python3', '-c', script], capture_output=True)
sys.stdout.buffer.write(out.stdout)
if out.stderr:
    sys.stderr.buffer.write(out.stderr)
