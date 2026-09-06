$KUBECTL = ".\kubectl.exe"
$KUBECONFIG = ".\local.yaml"

$pod = (& $KUBECTL --kubeconfig=$KUBECONFIG get pod -n macchinetta -l component=dashboard --field-selector=status.phase=Running -o jsonpath="{.items[0].metadata.name}")
Write-Host "Pod: $pod"

& $KUBECTL --kubeconfig=$KUBECONFIG cp scratch/verify_gold_pod.py "macchinetta/${pod}:/tmp/verify_gold_pod.py" -c dashboard
& $KUBECTL --kubeconfig=$KUBECONFIG exec $pod -n macchinetta -c dashboard -- python /tmp/verify_gold_pod.py
