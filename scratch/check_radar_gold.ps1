$KUBECTL = ".\kubectl.exe"
$KUBECONFIG = ".\local.yaml"

$pod = (& $KUBECTL --kubeconfig=$KUBECONFIG get pod -n macchinetta -l component=dashboard --field-selector=status.phase=Running -o jsonpath="{.items[0].metadata.name}")

& $KUBECTL --kubeconfig=$KUBECONFIG exec $pod -n macchinetta -c dashboard -- python -c "
import json

for acc in ['FIORDOK_DEMO', 'DANY_DEMO', 'BONGIOLO_DEMO']:
    print(f'=== RADAR TREND PER {acc} ===')
    try:
        with open(f'/data/{acc}/radar_trend.json') as f:
            radar = json.load(f)
        gold = radar.get('Spot Gold')
        print('Spot Gold radar_trend.json:', json.dumps(gold, indent=2))
    except Exception as e:
        print('Errore lettura radar_trend.json:', e)
"
