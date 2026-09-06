$KUBECTL = ".\kubectl.exe"
$KUBECONFIG = ".\local.yaml"

$pod = (& $KUBECTL --kubeconfig=$KUBECONFIG get pod -n macchinetta -l component=dashboard --field-selector=status.phase=Running -o jsonpath="{.items[0].metadata.name}")

& $KUBECTL --kubeconfig=$KUBECONFIG exec $pod -n macchinetta -c dashboard -- python -c "
import json

with open('/data/FIORDOK_DEMO/candele_Spot_Gold_MINUTE_5.json') as f:
    candele = json.load(f)

sub55 = candele[-55:]
print('--- ULTIME 55 BARRE M5 NEL DATABASE ---')
for i, c in enumerate(sub55):
    t = c.get('snapshotTime')
    h = c.get('highPrice',{}).get('bid')
    l = c.get('lowPrice',{}).get('bid')
    cl = c.get('closePrice',{}).get('bid')
    if h >= 4485:
        print(f'Barra #{i+1} ({t}) -> HIGH ELEVATO: {h} | L: {l} | C: {cl}')

print(f'\nPrima delle 55 barre: {sub55[0].get(\"snapshotTime\")}')
print(f'Ultima delle 55 barre: {sub55[-1].get(\"snapshotTime\")}')
"
