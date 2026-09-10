$ROOT = "C:\Users\Fiordok\Desktop\Macchinetta_IG"
$KUBECTL = "$ROOT\kubectl.exe"
$KUBECONFIG = "$ROOT\local.yaml"

$pod = (& $KUBECTL --kubeconfig=$KUBECONFIG get pod -n macchinetta -l component=dashboard -o jsonpath='{.items[0].metadata.name}')
Write-Host "Trovato pod dashboard: $pod"

# Tar candele
tar -cf "candele_bundle.tar" candele_*.json

# Copia tar su pod ed estrai in tutte le destinazioni
& $KUBECTL --kubeconfig=$KUBECONFIG -n macchinetta cp candele_bundle.tar "${pod}:/data/candele_bundle.tar" -c dashboard

& $KUBECTL --kubeconfig=$KUBECONFIG exec $pod -n macchinetta -c dashboard -- sh -c "
tar -xf /data/candele_bundle.tar -C /data/
mkdir -p /data/Logs_e_Cache /data/FIORDOK_DEMO /data/DANY_DEMO /data/BONGIOLO_DEMO
tar -xf /data/candele_bundle.tar -C /data/Logs_e_Cache/
tar -xf /data/candele_bundle.tar -C /data/FIORDOK_DEMO/
tar -xf /data/candele_bundle.tar -C /data/DANY_DEMO/
tar -xf /data/candele_bundle.tar -C /data/BONGIOLO_DEMO/
rm -f /data/candele_bundle.tar
"

Remove-Item -Path "$ROOT\candele_bundle.tar" -Force -ErrorAction SilentlyContinue
Write-Host "✅ Candele sincronizzate con successo su tutti i percorsi PVC (/data, Logs_e_Cache, FIORDOK_DEMO, DANY_DEMO, BONGIOLO_DEMO)!"
