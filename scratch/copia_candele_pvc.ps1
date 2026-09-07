$KUBECTL = ".\kubectl.exe"
$KUBECONFIG = ".\local.yaml"

$pod = (& $KUBECTL --kubeconfig=$KUBECONFIG get pod -n macchinetta -l component=dashboard --field-selector=status.phase=Running -o jsonpath='{.items[0].metadata.name}')
if (-not $pod) {
    Write-Host "Pod dashboard non trovato"
    exit 1
}

Write-Host "Pod Dashboard: $pod"

$accounts = @("FIORDOK_DEMO", "DANY_DEMO", "BONGIOLO_DEMO")
foreach ($acc in $accounts) {
    Write-Host "Copia file per $acc..."
    $files = Get-ChildItem -Path $acc -Filter "candele_*.json"
    foreach ($f in $files) {
        # Copia solo se non è M5 (lasciamo M5 intatto con i dati IG!)
        if ($f.Name -notmatch "MINUTE_5") {
            & $KUBECTL --kubeconfig=$KUBECONFIG cp "$acc/$($f.Name)" "macchinetta/${pod}:/data/$acc/$($f.Name)"
        }
    }
}

Write-Host "Tutte le candele Forex H1, H4, D1 sono state copiate nella PVC /data!"
