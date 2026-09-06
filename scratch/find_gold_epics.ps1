$KUBECTL = ".\kubectl.exe"
$KUBECONFIG = ".\local.yaml"

$pod = (& $KUBECTL --kubeconfig=$KUBECONFIG get pod -n macchinetta -l component=dashboard --field-selector=status.phase=Running -o jsonpath="{.items[0].metadata.name}")

& $KUBECTL --kubeconfig=$KUBECONFIG exec $pod -n macchinetta -c dashboard -- python -c "
import requests, json
from Sistema.auth_manager import get_ig_headers

headers = get_ig_headers('FIORDOK_DEMO')
url = 'https://demo-api.ig.com/gateway/deal/markets?searchTerm=Gold'
r = requests.get(url, headers=headers)
if r.status_code == 200:
    markets = r.json().get('markets', [])
    for m in markets[:15]:
        print(f\"{m.get('instrumentName')} | Epic: {m.get('epic')} | Type: {m.get('instrumentType')} | Bid: {m.get('bid')} | Offer: {m.get('offer')}\")
else:
    print('Error:', r.status_code, r.text)
"
