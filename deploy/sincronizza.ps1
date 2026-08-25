param (
    [string]$MessaggioCommit = "Aggiornamento codice e sincronizzazione server"
)

$ErrorActionPreference = "Stop"

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "🚀 1. VERIFICA SINTASSI PYTHON" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
python -m py_compile Dashboard.py Dashboard_Simulatore.py Motore.py
if ($LASTEXITCODE -ne 0) {
    Write-Error "❌ Errore di sintassi Python. Sincronizzazione interrotta."
    exit 1
}
Write-Host "✅ Sintassi Python OK." -ForegroundColor Green

Write-Host "`n==========================================" -ForegroundColor Cyan
Write-Host "📦 2. GIT COMMIT E PUSH" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
git add .
$status = git status --porcelain
if ($status) {
    git commit -m "$MessaggioCommit"
    git push origin master
    Write-Host "✅ Push su GitHub (master) completato." -ForegroundColor Green
} else {
    Write-Host "ℹ️ Nessun cambiamento da committare su Git." -ForegroundColor Yellow
}

Write-Host "`n==========================================" -ForegroundColor Cyan
Write-Host "🌐 3. COPIA FILE NELLA PVC KUBERNETES (/data)" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan

$POD_DASH = (.\kubectl.exe --kubeconfig=.\local.yaml get pod -n macchinetta -l component=dashboard -o jsonpath='{.items[0].metadata.name}')
if (-not $POD_DASH) {
    Write-Error "❌ Nessun pod Dashboard trovato nel namespace 'macchinetta'."
    exit 1
}
Write-Host "Trovato pod Dashboard: $POD_DASH" -ForegroundColor Yellow

.\kubectl.exe --kubeconfig=.\local.yaml cp Dashboard.py "macchinetta/${POD_DASH}:/data/Dashboard.py"
.\kubectl.exe --kubeconfig=.\local.yaml cp Dashboard_Simulatore.py "macchinetta/${POD_DASH}:/data/Dashboard_Simulatore.py"
.\kubectl.exe --kubeconfig=.\local.yaml cp Motore.py "macchinetta/${POD_DASH}:/data/Motore.py"
Write-Host "✅ File propagati correttamente nella PVC condivisa (/data)." -ForegroundColor Green

Write-Host "`n==========================================" -ForegroundColor Cyan
Write-Host "🔄 4. ROLLOUT RESTART DEI DEPLOYMENT" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
.\kubectl.exe --kubeconfig=.\local.yaml rollout restart deploy/macchinetta-dashboard -n macchinetta
.\kubectl.exe --kubeconfig=.\local.yaml rollout status deploy/macchinetta-dashboard -n macchinetta --timeout=120s

Write-Host "`n==========================================" -ForegroundColor Cyan
Write-Host "🩺 5. VERIFICA HEALTH CHECK" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
$health = curl.exe -k -s -o /dev/null -w "%{http_code}" https://macchinetta.wavetech.it/_stcore/health
if ($health -eq "200") {
    Write-Host "🎉 Dashboard attiva e raggiungibile con successo (HTTP 200) su https://macchinetta.wavetech.it" -ForegroundColor Green
} else {
    Write-Host "⚠️ Health check ha restituito HTTP $health (attendi qualche secondo)." -ForegroundColor Yellow
}
