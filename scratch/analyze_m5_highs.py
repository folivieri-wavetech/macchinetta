import json

with open('/data/FIORDOK_DEMO/candele_Spot_Gold_MINUTE_5.json') as f:
    candele = json.load(f)

sub55 = candele[-55:]
print('--- ULTIME 55 BARRE M5 PRESENTI NEL FILE ---')
print(f'Prima barra delle 55: {sub55[0].get("snapshotTime")}')
print(f'Ultima barra delle 55: {sub55[-1].get("snapshotTime")}')

high_bars = []
for i, c in enumerate(sub55):
    t = c.get('snapshotTime')
    h = c.get('highPrice',{}).get('bid')
    l = c.get('lowPrice',{}).get('bid')
    cl = c.get('closePrice',{}).get('bid')
    if h and h >= 4485:
        high_bars.append((i+1, t, h, l, cl))

print(f'\nBarre con High >= 4485 (totale {len(high_bars)}):')
for num, t, h, l, cl in high_bars:
    print(f'  Barra #{num:02d} alle {t} -> High: {h} | Low: {l} | Close: {cl}')

# Controlliamo anche se mancano le barre di stanotte (00:00 - 01:00)
print(f'\nNumero di barre datate 07/09 (stanotte): {sum(1 for c in candele if "2026/09/07" in c.get("snapshotTime", ""))}')
