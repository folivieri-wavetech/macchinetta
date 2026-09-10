$KUBECTL = ".\kubectl.exe"
$KUBECONFIG = ".\local.yaml"
$pod = (& $KUBECTL --kubeconfig=$KUBECONFIG get pod -n macchinetta -l component=dashboard -o jsonpath='{.items[0].metadata.name}')

Write-Host "Copia su pod $pod..."
& $KUBECTL --kubeconfig=$KUBECONFIG -n macchinetta cp Motore_Trend.py "${pod}:/data/Motore_Trend.py" -c dashboard
& $KUBECTL --kubeconfig=$KUBECONFIG -n macchinetta cp Sistema/sync_settimanale.py "${pod}:/data/Sistema/sync_settimanale.py" -c dashboard
Write-Host "✅ Copia completata!"
