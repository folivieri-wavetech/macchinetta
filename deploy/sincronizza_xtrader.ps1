param ()

# Sincronizzazione LEGGERA XTrader: copia solo XTrader.xlsx (e xtrader.py) nella PVC /data.
# Nessun commit, nessun riavvio di Dashboard o motori.
# Al termine invia una notifica push su ntfy (esito OK o errore).

$ROOT = Resolve-Path "$PSScriptRoot\.."
$KUBECTL = "$ROOT\kubectl.exe"
$KUBECONFIG = "$ROOT\local.yaml"

function Invia-Ntfy([string]$Titolo, [string]$Messaggio, [string]$Tag) {
    try {
        $topic = $null
        $envFile = Join-Path $ROOT "FIORDOK_DEMO\.env"
        if (Test-Path $envFile) {
            $riga = Get-Content $envFile | Where-Object { $_ -match '^\s*NTFY_TOPIC\s*=' } | Select-Object -First 1
            if ($riga) { $topic = ($riga -split '=', 2)[1].Trim().Trim('"') }
        }
        if (-not $topic) { $topic = "Macchinetta_Alert" }
        $orario = Get-Date -Format "HH:mm:ss"
        $body = [System.Text.Encoding]::UTF8.GetBytes("[$orario] $Messaggio")
        $headers = @{ "Title" = "[MACCHINETTA] $Titolo"; "Tags" = $Tag }
        Invoke-RestMethod -Uri "https://ntfy.sh/$topic" -Method Post -Body $body -Headers $headers -TimeoutSec 5 | Out-Null
    } catch {
        Write-Host "Notifica ntfy non inviata: $($_.Exception.Message)" -ForegroundColor DarkYellow
    }
}

$errFile = [System.IO.Path]::GetTempFileName()
$POD_DASH = "$(& $KUBECTL --kubeconfig=$KUBECONFIG get pod -n macchinetta -l component=dashboard --field-selector=status.phase=Running -o jsonpath="{.items[0].metadata.name}" 2>$errFile)".Trim()
$errTxt = Get-Content $errFile -Raw -ErrorAction SilentlyContinue
Remove-Item $errFile -ErrorAction SilentlyContinue
if ($POD_DASH -notmatch '^macchinetta-dashboard-[a-z0-9-]+$') {
    Write-Host "Impossibile trovare il pod Dashboard: $errTxt" -ForegroundColor Red
    if ("$errTxt" -match "Unauthorized|credentials|401") {
        Invia-Ntfy "SYNC XTRADER FALLITA" "Token kubeconfig scaduto (401). Serve nuovo KubeConfig da Rancher." "warning"
    } else {
        Invia-Ntfy "SYNC XTRADER FALLITA" "Pod Dashboard non trovato." "warning"
    }
    exit 1
}
Write-Host "Pod Dashboard: $POD_DASH" -ForegroundColor Yellow

Push-Location $ROOT
try {
    if (-not (Test-Path "XTrader.xlsx")) {
        Write-Host "XTrader.xlsx non trovato." -ForegroundColor Red
        Invia-Ntfy "SYNC XTRADER FALLITA" "XTrader.xlsx non trovato in locale." "warning"
        exit 1
    }
    & $KUBECTL --kubeconfig=$KUBECONFIG cp "XTrader.xlsx" "macchinetta/${POD_DASH}:/data/XTrader.xlsx" -c dashboard
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Copia XTrader.xlsx fallita." -ForegroundColor Red
        Invia-Ntfy "SYNC XTRADER FALLITA" "Copia XTrader.xlsx fallita." "warning"
        exit 1
    }
    $extra = ""
    if (Test-Path "xtrader.py") {
        & $KUBECTL --kubeconfig=$KUBECONFIG cp "xtrader.py" "macchinetta/${POD_DASH}:/data/xtrader.py" -c dashboard
        if ($LASTEXITCODE -eq 0) { $extra = " + xtrader.py" }
    }
    Write-Host "XTrader aggiornato sul server (nessun riavvio)." -ForegroundColor Green

    $fi = Get-Item "XTrader.xlsx"
    $salvato = $fi.LastWriteTime.ToString("HH:mm") + " del " + $fi.LastWriteTime.ToString("dd/MM")
    $kb = [math]::Round($fi.Length / 1KB)
    Invia-Ntfy "XTRADER AGGIORNATO" "XTrader.xlsx caricato sul server (salvato alle $salvato, $kb KB)$extra. Nessun riavvio, motori operativi." "white_check_mark"
} finally {
    Pop-Location
}
