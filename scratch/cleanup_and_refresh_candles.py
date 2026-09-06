import subprocess, sys

script = """
import os, sys, json, glob
sys.argv = ['Motore_Trend.py', 'FIORDOK_DEMO']
sys.path.append('/data')
import Motore_Trend

accs = ['DANY_DEMO', 'FIORDOK_DEMO', 'BONGIOLO_DEMO']
tfs = ['MINUTE_5', 'HOUR', 'HOUR_4', 'DAY']
strums = list(Motore_Trend.CONFIG_STRUMENTI.keys())

print('1. Cleaning up corrupt/mismatched candle files...')
for acc in accs:
    for nome in strums:
        clean = nome.replace('/', '_').replace(' ', '_')
        for tf in tfs:
            fpath = os.path.join('/data', acc, f'candele_{clean}_{tf}.json')
            if os.path.exists(fpath):
                try:
                    with open(fpath) as fp: d = json.load(fp)
                    if not Motore_Trend.is_valid_candele(d, tf):
                        print(f'Deleting invalid candle file: {fpath}')
                        os.remove(fpath)
                except Exception as e:
                    print(f'Error reading {fpath}: {e}')
                    if os.path.exists(fpath):
                        os.remove(fpath)

print('2. Downloading fresh accurate candles for all instruments & timeframes...')
for acc in accs:
    for nome in strums:
        for tf in tfs:
            clean = nome.replace('/', '_').replace(' ', '_')
            fpath = os.path.join('/data', acc, f'candele_{clean}_{tf}.json')
            if not os.path.exists(fpath):
                c_yh = Motore_Trend.scarica_candele_yahoo(nome, tf)
                if c_yh and len(c_yh) >= 10:
                    try:
                        with open(fpath, 'w') as fp:
                            json.dump(c_yh[-100:], fp, indent=2)
                        print(f'Saved fresh {nome} {tf} ({len(c_yh)} bars) to {acc}')
                    except Exception as e:
                        print(f'Error saving {fpath}: {e}')

print('3. Recalculating radar trend...')
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

print('DONE!')
"""

out = subprocess.run(['kubectl.exe', '--kubeconfig=local.yaml', '-n', 'macchinetta', 'exec', 'deployment/macchinetta-dashboard', '--', 'python3', '-c', script], capture_output=True)
sys.stdout.buffer.write(out.stdout)
if out.stderr:
    sys.stderr.buffer.write(out.stderr)
