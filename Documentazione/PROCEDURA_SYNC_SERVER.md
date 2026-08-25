# 🔄 PROCEDURA MASTER DI SINCRONIZZAZIONE E DEPLOY SERVER

Questo documento descrive il meccanismo esatto e completo da seguire ogni volta che si deve sincronizzare il codice locale con il server di produzione su Kubernetes (Rancher K3s `macchinetta.wavetech.it`).

---

## ⚡ COMANDO RAPIDO UNIFICATO
Per eseguire tutti i passi in modo automatico:
```powershell
powershell -ExecutionPolicy Bypass -File .\deploy\sincronizza.ps1 -MessaggioCommit "Descrizione modifiche"
```

---

## 📋 I 5 PASSAGGI DELLA PROCEDURA COMPLETA

### 1. Test Sintassi Python
Prima di qualsiasi operazione, verificare che il codice sia privo di errori di sintassi:
```powershell
python -m py_compile Dashboard.py Dashboard_Simulatore.py Motore.py
```

### 2. Commit e Push su GitHub
Salvare e inviare le modifiche al repository remoto:
```powershell
git add .
git commit -m "Descrizione della modifica"
git push origin master
```

### 3. Propagazione del Codice nella PVC Condivisa (`/data`)
Poiché i pod leggono il codice dalla PVC Longhorn (`/data`) e non ricostruiscono il codice all'avvio:
```powershell
# 1. Recupera il nome del pod Dashboard attivo
$POD_DASH = (.\kubectl.exe --kubeconfig=.\local.yaml get pod -n macchinetta -l component=dashboard -o jsonpath='{.items[0].metadata.name}')

# 2. Copia i file modificati nella PVC (/data/)
.\kubectl.exe --kubeconfig=.\local.yaml cp Dashboard.py "macchinetta/${POD_DASH}:/data/Dashboard.py"
.\kubectl.exe --kubeconfig=.\local.yaml cp Dashboard_Simulatore.py "macchinetta/${POD_DASH}:/data/Dashboard_Simulatore.py"
.\kubectl.exe --kubeconfig=.\local.yaml cp Motore.py "macchinetta/${POD_DASH}:/data/Motore.py"
```

### 4. Riavvio (Rollout Restart) dei Pod
Per far caricare il nuovo codice dall'interprete Python in esecuzione:
```powershell
# Riavvia la Dashboard:
.\kubectl.exe --kubeconfig=.\local.yaml rollout restart deploy/macchinetta-dashboard -n macchinetta
.\kubectl.exe --kubeconfig=.\local.yaml rollout status deploy/macchinetta-dashboard -n macchinetta --timeout=120s

# Se è stato modificato Motore.py, riavvia anche i motori:
.\kubectl.exe --kubeconfig=.\local.yaml rollout restart deploy/macchinetta-motore-bongiolo deploy/macchinetta-motore-dany deploy/macchinetta-motore-fiordok -n macchinetta
```

### 5. Verifica Health Check
Controllare che la Dashboard risponda con codice HTTP 200:
```powershell
curl.exe -k -s -o /dev/null -w "%{http_code}" https://macchinetta.wavetech.it/_stcore/health
```

---

## 🔑 RIFERIMENTI RAPIDI INFRASTRUTTURA
- **Host Web:** `https://macchinetta.wavetech.it`
- **Kubeconfig Locale:** `.\local.yaml`
- **Eseguibile Kubectl Locale:** `.\kubectl.exe`
- **Namespace Kubernetes:** `macchinetta`
- **PVC Condivisa:** `macchinetta-data` montata su `/data`
