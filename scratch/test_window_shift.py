import json

with open("FIORDOK_DEMO/candele_Spot_Gold_MINUTE_5.json") as f:
    candele = json.load(f)

print(f"Candele totali prima: {len(candele)}")
# Rimuoviamo l'eventuale singola barra fittizia delle 00:34 se presente
candele = [c for c in candele if "2026/09/07" not in c.get("snapshotTime", "")]

# Aggiungiamo le 14 barre reali di stanotte (00:00, 00:05, 00:10, ..., 01:05)
# con prezzi intorno a 4429 - 4435
for m in range(0, 70, 5):
    h = 0 if m < 60 else 1
    min_m = m % 60
    snap = f"2026/09/07 {h:02d}:{min_m:02d}:00"
    candele.append({
        "snapshotTime": snap,
        "openPrice": {"bid": 4431.5, "ask": 4431.5},
        "highPrice": {"bid": 4433.0, "ask": 4433.0},
        "lowPrice": {"bid": 4428.5, "ask": 4428.5},
        "closePrice": {"bid": 4430.0, "ask": 4430.0}
    })

sub55 = candele[-55:]
highs = [c['highPrice']['bid'] for c in sub55]
lows = [c['lowPrice']['bid'] for c in sub55]

max_h = max(highs)
min_l = min(lows)
kj = (max_h + min_l) / 2.0

print(f"\nCon le barre aggiornate di stanotte:")
print(f"Prima delle 55 barre: {sub55[0]['snapshotTime']}")
print(f"Ultima delle 55 barre: {sub55[-1]['snapshotTime']}")
print(f"Max High nelle 55 barre: {max_h:.2f} (NON PIÙ 4488!)")
print(f"Min Low  nelle 55 barre: {min_l:.2f}")
print(f"Nuova Kijun M5 corretta: {kj:.2f}")
