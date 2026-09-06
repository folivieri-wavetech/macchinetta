$KUBECTL = ".\kubectl.exe"
$KUBECONFIG = ".\local.yaml"

$pod = (& $KUBECTL --kubeconfig=$KUBECONFIG get pod -n macchinetta -l component=dashboard --field-selector=status.phase=Running -o jsonpath="{.items[0].metadata.name}")

& $KUBECTL --kubeconfig=$KUBECONFIG exec $pod -n macchinetta -c dashboard -- python -c "
import json
with open('/data/FIORDOK_DEMO/candele_Spot_Gold_MINUTE_5.json') as f:
    d = json.load(f)
print('Sample candle:', json.dumps(d[-1], indent=2))
"
