$KUBECTL = ".\kubectl.exe"
$KUBECONFIG = ".\local.yaml"

$pod = (& $KUBECTL --kubeconfig=$KUBECONFIG get pod -n macchinetta -l component=dashboard --field-selector=status.phase=Running -o jsonpath="{.items[0].metadata.name}")

& $KUBECTL --kubeconfig=$KUBECONFIG exec $pod -n macchinetta -c dashboard -- python -c "
import json

with open('/data/FIORDOK_DEMO/candele_Spot_Gold_HOUR.json') as f:
    candele = json.load(f)

print(f'Totale candele Spot Gold H1: {len(candele)}')
sub55 = candele[-55:]
print(f'Prima barra delle 55: {sub55[0].get(\"snapshotTime\")}')
print(f'Ultima barra delle 55: {sub55[-1].get(\"snapshotTime\")}')

for i, c in enumerate(sub55):
    t = c.get('snapshotTime')
    h = c.get('highPrice',{}).get('bid') or c.get('highPrice',{}).get('mid')
    l = c.get('lowPrice',{}).get('bid') or c.get('lowPrice',{}).get('mid')
    cl = c.get('closePrice',{}).get('bid') or c.get('closePrice',{}).get('mid')
    print(f'[{i+1:02d}] {t} -> H: {h} | L: {l} | C: {cl}')

highs = [float(c.get('highPrice',{}).get('bid') or c.get('highPrice',{}).get('mid')) for c in sub55]
lows = [float(c.get('lowPrice',{}).get('bid') or c.get('lowPrice',{}).get('mid')) for c in sub55]
max_h = max(highs)
min_l = min(lows)
idx_max = highs.index(max_h)
idx_min = lows.index(min_l)
print(f'\nMax High: {max_h} (Barra #{idx_max+1} alle {sub55[idx_max].get(\"snapshotTime\")})')
print(f'Min Low:  {min_l} (Barra #{idx_min+1} alle {sub55[idx_min].get(\"snapshotTime\")})')
print(f'KJ (55) = ({max_h} + {min_l}) / 2 = {(max_h+min_l)/2}')
"
