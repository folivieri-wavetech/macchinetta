$KUBECTL = ".\kubectl.exe"
$KUBECONFIG = ".\local.yaml"

$pod = (& $KUBECTL --kubeconfig=$KUBECONFIG get pod -n macchinetta -l component=dashboard --field-selector=status.phase=Running -o jsonpath="{.items[0].metadata.name}")

& $KUBECTL --kubeconfig=$KUBECONFIG exec $pod -n macchinetta -c dashboard -- python -c "
import json
with open('/data/FIORDOK_DEMO/candele_Spot_Gold_MINUTE_5.json') as f:
    candele = json.load(f)

print(f'Totale candele M5: {len(candele)}')
for i, c in enumerate(candele):
    t = c.get('snapshotTime')
    o = c.get('openPrice',{}).get('bid')
    h = c.get('highPrice',{}).get('bid')
    l = c.get('lowPrice',{}).get('bid')
    cl = c.get('closePrice',{}).get('bid')
    print(f'[{i:03d}] {t} -> O: {o} | H: {h} | L: {l} | C: {cl}')
"
