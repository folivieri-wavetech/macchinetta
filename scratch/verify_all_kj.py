import subprocess, sys

script = """
import os, sys, json
sys.argv = ['Motore_Trend.py', 'FIORDOK_DEMO']
sys.path.append('/data')
import Motore_Trend

with open('/data/FIORDOK_DEMO/radar_trend.json') as f:
    rad = json.load(f).get('radar_trend', {})

header = f"{'STRUMENTO':<14} | {'LIVE':<9} | {'KJ M5':<10} | {'KJ H1':<10} | {'KJ H4':<10} | {'KJ D1':<10} | {'DIST M5':<7} | {'DIST H1':<7}"
print(header)
print('-'*90)
for nome in Motore_Trend.CONFIG_STRUMENTI:
    info = rad.get(nome, {})
    px = info.get('prezzo', '-')
    tfs = info.get('timeframes', {})
    m5 = tfs.get('M5', {})
    h1 = tfs.get('H1', {})
    h4 = tfs.get('H4', {})
    d1 = tfs.get('D1', {})
    dec = Motore_Trend.CONFIG_STRUMENTI[nome]['decimali']
    
    def fk(v): 
        return f"{v:.{dec}f}" if (v is not None and isinstance(v, (int, float))) else '-'
    
    row = f"{nome:<14} | {px:<9} | {fk(m5.get('kj')):<10} | {fk(h1.get('kj')):<10} | {fk(h4.get('kj')):<10} | {fk(d1.get('kj')):<10} | {str(m5.get('dist_pips')):<7} | {str(h1.get('dist_pips')):<7}"
    print(row)
"""

out = subprocess.run(['kubectl.exe', '--kubeconfig=local.yaml', '-n', 'macchinetta', 'exec', 'deployment/macchinetta-dashboard', '--', 'python3', '-c', script], capture_output=True)
sys.stdout.buffer.write(out.stdout)
if out.stderr:
    sys.stderr.buffer.write(out.stderr)
