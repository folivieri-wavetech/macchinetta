import json

# Leggiamo dal pod via kubectl
import subprocess

cmd = ["kubectl", "--kubeconfig", "local.yaml", "exec", "-n", "macchinetta", "deployment/macchinetta-dashboard", "-c", "dashboard", "--", "cat", "/data/DANY_DEMO/hyper_us500_m5_state.json"]
res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
if res.returncode == 0:
    data = json.loads(res.stdout)
    candles = data.get("m5_candles", [])
    print(f"Totale candele: {len(candles)}")
    for i, c in enumerate(candles):
        # Calcoliamo KJ55 su finestra di 55 candele
        if i >= 54:
            window = candles[i-54:i+1]
            highs = [x["high"] for x in window]
            lows = [x["low"] for x in window]
            kj = (max(highs) + min(lows)) / 2.0
        else:
            kj = None
        t = c.get("time", "")
        # Mostriamo candele tra le 18:00 e le 19:30
        if "18:" in t or "19:" in t:
            print(f"{t} | O: {c['open']:.2f} H: {c['high']:.2f} L: {c['low']:.2f} C: {c['close']:.2f} | KJ55: {kj:.2f if kj else 'N/A'}")
else:
    print("Errore kubectl:", res.stderr)
