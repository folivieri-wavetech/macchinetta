# Regola di Deploy e Sincronizzazione Server

Ogni volta che l'utente chiede di sincronizzare, pubblicare o aggiornare il server, oppure menziona la frase **"Sincronizza Server"** o **"Procedura Sincronizzazione Server"**, seguire rigorosamente i 5 passi descritti in `Documentazione/PROCEDURA_SYNC_SERVER.md` oppure eseguire lo script dedicato:

```powershell
powershell -ExecutionPolicy Bypass -File .\deploy\sincronizza.ps1 -MessaggioCommit "<messaggio>"
```

I passi eseguiti sono:
1. Verifica sintassi Python (`python -m py_compile`)
2. Commit e Push su GitHub (`git add`, `git commit`, `git push origin master`)
3. Copia dei file aggiornati nella PVC del pod Dashboard (`.\kubectl.exe --kubeconfig=.\local.yaml cp ...`)
4. Rollout restart dei deployment (`.\kubectl.exe --kubeconfig=.\local.yaml rollout restart ...`)
5. Verifica Health Check (`curl.exe ... https://macchinetta.wavetech.it/_stcore/health`)
