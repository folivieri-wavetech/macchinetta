$dashPod = (.\kubectl.exe --kubeconfig=.\local.yaml -n macchinetta get pods -l component=dashboard -o jsonpath='{.items[0].metadata.name}')
Write-Host "Trovato pod Dashboard: $dashPod"

$accounts = @("FIORDOK_DEMO", "DANY_DEMO", "BONGIOLO_DEMO")
$timeframes = @("MINUTE_5", "HOUR", "HOUR_4", "DAY")

foreach ($acc in $accounts) {
    foreach ($tf in $timeframes) {
        $src = "FIORDOK_DEMO/candele_GBP_JPY_${tf}.json"
        $dst = "${dashPod}:/data/${acc}/candele_GBP_JPY_${tf}.json"
        Write-Host "Copia $src in $dst..."
        .\kubectl.exe --kubeconfig=.\local.yaml -n macchinetta cp $src $dst -c dashboard
    }
}

Write-Host "Copia Dashboard.py, Motore.py e Motore_Trend.py..."
.\kubectl.exe --kubeconfig=.\local.yaml -n macchinetta cp Dashboard.py "${dashPod}:/data/Dashboard.py" -c dashboard
.\kubectl.exe --kubeconfig=.\local.yaml -n macchinetta cp Motore.py "${dashPod}:/data/Motore.py" -c dashboard
.\kubectl.exe --kubeconfig=.\local.yaml -n macchinetta cp Motore_Trend.py "${dashPod}:/data/Motore_Trend.py" -c dashboard

Write-Host "Copia ed esecuzione applica_gbpjpy_server.py..."
.\kubectl.exe --kubeconfig=.\local.yaml -n macchinetta cp scratch/applica_gbpjpy_server.py "${dashPod}:/data/applica_gbpjpy_server.py" -c dashboard
.\kubectl.exe --kubeconfig=.\local.yaml -n macchinetta exec deploy/macchinetta-dashboard -c dashboard -- python3 /data/applica_gbpjpy_server.py

Write-Host "Completato con successo!"
