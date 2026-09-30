import subprocess, json

cmd = ['kubectl', '--kubeconfig', 'local.yaml', 'exec', '-n', 'macchinetta', 'deployment/macchinetta-dashboard', '-c', 'dashboard', '--', 'cat', '/data/DANY_DEMO/hyper_us500_m5_state.json']
res = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')
d = json.loads(res.stdout)
candles = d.get('candles', [])
print('Numero candele M10:', len(candles))
for c in candles:
    t = c.get('time', '')
    if any(h in t for h in ['18:', '19:', '20:', '21:']):
        print(f"{t} | O: {c.get('open')} H: {c.get('high')} L: {c.get('low')} C: {c.get('close')} | KJ55: {c.get('kj55')}")
