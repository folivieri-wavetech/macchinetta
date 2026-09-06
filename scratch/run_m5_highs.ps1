$KUBECTL = ".\kubectl.exe"
$KUBECONFIG = ".\local.yaml"

$pod = (& $KUBECTL --kubeconfig=$KUBECONFIG get pod -n macchinetta -l component=dashboard --field-selector=status.phase=Running -o jsonpath="{.items[0].metadata.name}")

& $KUBECTL --kubeconfig=$KUBECONFIG cp scratch/analyze_m5_highs.py "macchinetta/${pod}:/tmp/analyze_m5_highs.py" -c dashboard
& $KUBECTL --kubeconfig=$KUBECONFIG exec $pod -n macchinetta -c dashboard -- python /tmp/analyze_m5_highs.py
