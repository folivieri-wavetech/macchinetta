# Regole di Deployment per Macchinetta IG

Quando l'utente richiede di "deployare", "sincronizzare il server" o "spingere le modifiche in produzione", **devi seguire rigorosamente e in autonomia questa procedura**. Non chiedere spiegazioni all'utente su come si fa, hai tutto qui.

## Architettura e Contesto
- Questa applicazione gira su un cluster Kubernetes gestito da Rancher (`macchinetta.wavetech.it`).
- Non abbiamo bisogno di rebuildare l'immagine Docker per aggiornare il codice Python (a meno che non cambino le dipendenze native in `requirements.txt`).
- Il codice live è ospitato in un Persistent Volume (PVC) montato sotto `/data`. 
- Il file `local.yaml` presente nella cartella principale è il `kubeconfig` valido per accedere al server.

## Procedura di Deploy Ufficiale
Per sincronizzare le modifiche sul server, esegui i seguenti passaggi in sequenza usando i tuoi tool (es. `run_command` in PowerShell):

1. **Commit su GitHub:**
   Assicurati di committare le tue modifiche locali su GitHub prima di procedere.
   ```powershell
   git add .
   git commit -m "Descrizione delle modifiche"
   git push origin master
   ```

2. **Esecuzione dello script di Sincronizzazione:**
   Lancia lo script PowerShell già pronto che si occupa di copiare i file (`Dashboard.py`, `Motore.py`, ecc.) dentro la PVC del server.
   ```powershell
   powershell -ExecutionPolicy Bypass -File .\deploy\sincronizza.ps1
   ```
   *Nota: Se lo script fallisce perché tenta di copiare l'intera cartella `Sistema` nidificandola, usa `kubectl cp` per copiare esplicitamente i singoli file modificati.*

3. **Riavvio dei Motori (Rollout Restart):**
   Lo script `sincronizza.ps1` riavvia solo la Dashboard. **Tu DEVI sempre riavviare anche i motori** affinché le modifiche al motore vengano recepite.
   Usa questo comando esatto:
   ```powershell
   .\kubectl.exe --kubeconfig=.\local.yaml rollout restart deploy/macchinetta-motore-bongiolo deploy/macchinetta-motore-dany deploy/macchinetta-motore-fiordok -n macchinetta
   ```

## Note in caso di pacchetti mancanti
Se hai aggiunto una libreria a `requirements.txt` (es. `werkzeug`), l'immagine Docker non la conterrà finché l'amministratore non farà il rebuild. 
In tal caso, fai un `pip install <libreria> -t /data/libs` usando `kubectl exec` sul pod della Dashboard, e assicurati che `Dashboard.py` o `Motore.py` abbiano `sys.path.append("/data/libs")`.


## Gestione Scadenza Token Kubeconfig
Il token di Kubernetes generato da Rancher ha una scadenza di 30 giorni. Se durante un deploy o una copia file ricevi un errore di tipo Forbidden o Unauthorized da parte di Kubernetes:
1. **NON dire all'utente di contattare l'amministratore.**
2. Informa l'utente che il token è scaduto e chiedigli di fornirti il nuovo contenuto del file kubeconfig (tramite copia e incolla).
3. Una volta ricevuto, sovrascrivi integralmente il contenuto del file local.yaml presente nella root del progetto con il nuovo testo fornito.
4. Riprova l'operazione di deploy o kubectl: funzionerà immediatamente.
