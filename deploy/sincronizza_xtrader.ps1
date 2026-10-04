param ()

# Sincronizzazione LEGGERA XTrader: copia solo XTrader.xlsx (e xtrader.py) nella PVC /data.
# Nessun commit, nessun riavvio di Dashboard o motori.

$ROOT = Resolve-Path "$PSScriptRoot\.."
$KUBECTL = "$ROOT\kubectl.exe"
$KUBECONFIG = "$ROOT\local.yaml"

$POD_DASH = (& $KUBECTL --kubeconfig=$KUBECONFIG get pod -n macchinetta -l component=dashboard --field-selector=status.phase=Running -o jsonpath="{.items[0].metadata.name}" 2>&1)
if ($LASTEXITCODE -ne 0 -or -not $POD_DASH -or $POD_DASH -match "error|Unauthorized|credentials") {
    Write-Host "Impossibile trovare il pod Dashboard: $POD_DASH" -ForegroundColor Red
    exit 1
}
$POD_DASH = $POD_DASH.Trim()
Write-Host "Pod Dashboard: $POD_DASH" -ForegroundColor Yellow

Push-Location $ROOT
try {
    if (-not (Test-Path "XTrader.xlsx")) {
        Write-Host "XTrader.xlsx non trovato." -ForegroundColor Red
        exit 1
    }
    & $KUBECTL --kubeconfig=$KUBECONFIG cp "XTrader.xlsx" "macchinetta/${POD_DASH}:/data/XTrader.xlsx" -c dashboard
    if ($LASTEXITCODE -ne 0) { Write-Host "Copia XTrader.xlsx fallita." -ForegroundColor Red; exit 1 }
    if (Test-Path "xtrader.py") {
        & $KUBECTL --kubeconfig=$KUBECONFIG cp "xtrader.py" "macchinetta/${POD_DASH}:/data/xtrader.py" -c dashboard
    }
    Write-Host "XTrader aggiornato sul server (nessun riavvio)." -ForegroundColor Green
} finally {
    Pop-Location
}
