param (
    [string]$MessaggioCommit = "Aggiornamento codice e sincronizzazione server"
)

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "1. VERIFICA SINTASSI PYTHON" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
python -m py_compile Dashboard.py Motore.py Motore_Trend.py
if ($LASTEXITCODE -ne 0) {
    Write-Host "Errore di sintassi Python. Sincronizzazione interrotta." -ForegroundColor Red
    exit 1
}
Write-Host "Sintassi Python OK." -ForegroundColor Green

Write-Host "`n==========================================" -ForegroundColor Cyan
Write-Host "2. GIT COMMIT E PUSH" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
git add .
$status = git status --porcelain
if ($status) {
    git commit -m "$MessaggioCommit"
    git push origin master
    Write-Host "Push su GitHub (master) completato." -ForegroundColor Green
} else {
    Write-Host "Nessun cambiamento da committare su Git." -ForegroundColor Yellow
}

Write-Host "`n==========================================" -ForegroundColor Cyan
Write-Host "3. COPIA FILE NELLA PVC KUBERNETES (/data)" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan

$ROOT = Resolve-Path "$PSScriptRoot\.."
$KUBECTL = "$ROOT\kubectl.exe"
$KUBECONFIG = "$ROOT\local.yaml"

$POD_DASH = (& $KUBECTL --kubeconfig=$KUBECONFIG get pod -n macchinetta -l component=dashboard --field-selector=status.phase=Running -o jsonpath="{.items[0].metadata.name}")
if (-not $POD_DASH) {
    # Fallback se in fase di rollout
    $POD_DASH = (& $KUBECTL --kubeconfig=$KUBECONFIG get pod -n macchinetta -l component=dashboard -o jsonpath="{.items[0].metadata.name}")
}
if (-not $POD_DASH) {
    Write-Host "Nessun pod Dashboard trovato nel namespace macchinetta." -ForegroundColor Red
    exit 1
}
Write-Host "Trovato pod Dashboard: $POD_DASH" -ForegroundColor Yellow

Push-Location $ROOT
try {
    & $KUBECTL --kubeconfig=$KUBECONFIG cp Dashboard.py "macchinetta/${POD_DASH}:/data/Dashboard.py"
    & $KUBECTL --kubeconfig=$KUBECONFIG cp Motore.py "macchinetta/${POD_DASH}:/data/Motore.py"
    & $KUBECTL --kubeconfig=$KUBECONFIG cp Motore_Trend.py "macchinetta/${POD_DASH}:/data/Motore_Trend.py"
    Get-ChildItem -Path "macchinetta_trend" -File | ForEach-Object {
        & $KUBECTL --kubeconfig=$KUBECONFIG cp $_.FullName "macchinetta/${POD_DASH}:/data/macchinetta_trend/$($_.Name)"
    }
    & $KUBECTL --kubeconfig=$KUBECONFIG cp Sistema/auth_manager.py "macchinetta/${POD_DASH}:/data/Sistema/auth_manager.py"
    Write-Host "File propagati correttamente nella PVC condivisa (/data)." -ForegroundColor Green
} finally {
    Pop-Location
}

Write-Host "`n==========================================" -ForegroundColor Cyan
Write-Host "4. ROLLOUT RESTART DEI DEPLOYMENT" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
& $KUBECTL --kubeconfig=$KUBECONFIG apply -f deploy/motore.yaml -n macchinetta
& $KUBECTL --kubeconfig=$KUBECONFIG rollout restart deploy/macchinetta-dashboard -n macchinetta
& $KUBECTL --kubeconfig=$KUBECONFIG rollout restart deploy/macchinetta-motore-bongiolo deploy/macchinetta-motore-dany deploy/macchinetta-motore-fiordok -n macchinetta
& $KUBECTL --kubeconfig=$KUBECONFIG rollout status deploy/macchinetta-dashboard -n macchinetta --timeout=120s

Write-Host "`n==========================================" -ForegroundColor Cyan
Write-Host "5. VERIFICA HEALTH CHECK" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
$health = curl.exe -k -s -o /dev/null -w "%{http_code}" https://macchinetta.wavetech.it/_stcore/health
if ($health -eq "200") {
    Write-Host "Dashboard attiva e raggiungibile con successo (HTTP 200) su https://macchinetta.wavetech.it" -ForegroundColor Green
} else {
    Write-Host "Health check ha restituito HTTP $health (attendi qualche secondo)." -ForegroundColor Yellow
}
