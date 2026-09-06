$KUBECTL = ".\kubectl.exe"
$KUBECONFIG = ".\local.yaml"

$pod = (& $KUBECTL --kubeconfig=$KUBECONFIG get pod -n macchinetta -l component=dashboard --field-selector=status.phase=Running -o jsonpath="{.items[0].metadata.name}")

& $KUBECTL --kubeconfig=$KUBECONFIG exec $pod -n macchinetta -c dashboard -- python -c "
import json
with open('/data/FIORDOK_DEMO/stato_motore_trend.json') as f:
    d = json.load(f)
print('Prezzi live in FIORDOK_DEMO stato_motore_trend:', json.dumps(d.get('prezzi_live', {}), indent=2))
"
