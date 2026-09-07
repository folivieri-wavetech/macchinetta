 = "C:\Users\Fiordok\Desktop\Macchinetta_IG"
 = "\kubectl.exe"
 = "\local.yaml"

 = (&  --kubeconfig= get pod -n macchinetta -l component=dashboard --field-selector=status.phase=Running -o jsonpath="{.items[0].metadata.name}")

# Fetch live price from stato_sistema.json
&  --kubeconfig= exec  -n macchinetta -- cat /data/DANY_DEMO/stato_sistema.json > scratch/stato_dany.json

# Fetch M5 candles for USDJPY
&  --kubeconfig= exec  -n macchinetta -- cat /data/DANY_DEMO/candele_USD_JPY_MINUTE_5.json > scratch/candele_dany_usdjpy.json
