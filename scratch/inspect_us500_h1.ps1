$KUBECTL = ".\kubectl.exe"
$KUBECONFIG = ".\local.yaml"

$pod = (& $KUBECTL --kubeconfig=$KUBECONFIG get pod -n macchinetta -l component=dashboard --field-selector=status.phase=Running -o jsonpath="{.items[0].metadata.name}")

& $KUBECTL --kubeconfig=$KUBECONFIG exec $pod -n macchinetta -c dashboard -- python -c "
import json

with open('/data/FIORDOK_DEMO/candele_US_500_Cash_HOUR.json') as f:
    candele = json.load(f)

print(f'Totale candele US 500 H1: {len(candele)}')
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
print(f'\nMax High: {max(highs)} (Barra #{highs.index(max(highs))+1} alle {sub55[highs.index(max(highs))].get(\"snapshotTime\")})')
print(f'Min Low:  {min(lows)} (Barra #{lows.index(min(lows))+1} alle {sub55[lows.index(min(lows))].get(\"snapshotTime\")})')
print(f'KJ (55) = ({max(highs)} + {min(lows)}) / 2 = {(max(highs)+min(lows))/2}')
"
