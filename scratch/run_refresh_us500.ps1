$KUBECTL = ".\kubectl.exe"
$KUBECONFIG = ".\local.yaml"

$pod = (& $KUBECTL --kubeconfig=$KUBECONFIG get pod -n macchinetta -l component=dashboard --field-selector=status.phase=Running -o jsonpath="{.items[0].metadata.name}")

& $KUBECTL --kubeconfig=$KUBECONFIG cp scratch/refresh_us500_all.py "macchinetta/${pod}:/tmp/refresh_us500_all.py" -c dashboard
& $KUBECTL --kubeconfig=$KUBECONFIG exec $pod -n macchinetta -c dashboard -- python /tmp/refresh_us500_all.py
