$KUBECTL = ".\kubectl.exe"
$KUBECONFIG = ".\local.yaml"

$pod = (& $KUBECTL --kubeconfig=$KUBECONFIG get pod -n macchinetta -l component=dashboard --field-selector=status.phase=Running -o jsonpath="{.items[0].metadata.name}")

& $KUBECTL --kubeconfig=$KUBECONFIG exec $pod -n macchinetta -c dashboard -- python -c "
import json
with open('/data/FIORDOK_DEMO/radar_trend.json') as f:
    d = json.load(f)
r = d.get('radar_trend', {})
print('Strumenti in radar_trend:', list(r.keys()))
for k, v in r.items():
    if 'Gold' in k:
        print(f'{k}: {json.dumps(v, indent=2)}')
"
