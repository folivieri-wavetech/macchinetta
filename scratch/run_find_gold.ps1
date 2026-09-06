$KUBECTL = ".\kubectl.exe"
$KUBECONFIG = ".\local.yaml"

$pod = (& $KUBECTL --kubeconfig=$KUBECONFIG get pod -n macchinetta -l app=macchinetta-motore-fiordok --field-selector=status.phase=Running -o jsonpath="{.items[0].metadata.name}")
Write-Host "Target Pod: $pod"

& $KUBECTL --kubeconfig=$KUBECONFIG cp scratch/find_gold.py "macchinetta/${pod}:/tmp/find_gold.py" -c motore
& $KUBECTL --kubeconfig=$KUBECONFIG exec $pod -n macchinetta -c motore -- python /tmp/find_gold.py
