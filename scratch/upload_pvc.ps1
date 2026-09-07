$ROOT = "C:\Users\Fiordok\Desktop\Macchinetta_IG"
$KUBECTL = "$ROOT\kubectl.exe"
$KUBECONFIG = "$ROOT\local.yaml"

$POD_DASH = (& $KUBECTL --kubeconfig=$KUBECONFIG get pod -n macchinetta -l component=dashboard --field-selector=status.phase=Running -o jsonpath="{.items[0].metadata.name}")

$DESTS = @("FIORDOK_DEMO", "DANY_DEMO", "BONGIOLO_DEMO")
$FILES = Get-ChildItem -Path "generati" -Filter "*.json"

foreach ($dest in $DESTS) {
    & $KUBECTL --kubeconfig=$KUBECONFIG exec $POD_DASH -n macchinetta -- sh -c "mkdir -p /data/$dest"
    
    foreach ($f in $FILES) {
        $src = "generati/" + $f.Name
        $dst = "macchinetta/${POD_DASH}:/data/$dest/" + $f.Name
        Write-Host "Copia in $dest -> $($f.Name)"
        & $KUBECTL --kubeconfig=$KUBECONFIG cp $src $dst
    }
}
Write-Host "Tutti i file copiati con successo."
