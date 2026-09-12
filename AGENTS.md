# Regole Operative Progetto Macchinetta IG

## 🔄 1. Sincronizzazione e Deploy Server Kubernetes (Produzione)
- **Non usare Docker e non fare build di immagini/VM:** Su questa macchina Windows non è installato Docker e l'infrastruttura di produzione non usa VM dirette.
- **Architettura di produzione:** Il cluster è Kubernetes K3s (Rancher `rancher.wavetech.it`), namespace `macchinetta`. I pod eseguono il codice direttamente dal volume condiviso Longhorn (`/data`).
- **Comando Unico di Sincronizzazione:**
  Per aggiornare il server, eseguire sempre:
  ```powershell
  powershell -ExecutionPolicy Bypass -File .\deploy\sincronizza.ps1 -MessaggioCommit "Descrizione modifiche"
  ```
  Questo script si occupa in automatico di:
  1. Verificare la sintassi Python (`py_compile`).
  2. Eseguire il commit e push su GitHub (`master`).
  3. Copiare i file modificati (`Dashboard.py`, `Motore.py`, `Motore_Trend.py`, `macchinetta_trend/`, ecc.) nella PVC `/data/` tramite `kubectl cp`.
  4. Riavviare selettivamente i pod (`kubectl rollout restart`).
  5. Eseguire l'health check HTTP su `https://macchinetta.wavetech.it`.

---

## 🔑 2. Gestione Token Profilo "marco" (`local.yaml`)
- Il kubeconfig si trova in `local.yaml` e usa il token associato all'utente **`marco`** (`u-659xm`).
- **Scadenza o Invalidazione del Token:**  
  Se un comando `kubectl` fallisce per token scaduto, non autorizzato (`Unauthorized`, `401`, o token invalido):
  - **NON tentare modifiche manuali o procedure alternative.**
  - **Chiedi direttamente all'utente di inviarti la nuova configurazione / nuovo token per `local.yaml`.**
  - Una volta fornito dall'utente, sovrascrivi `local.yaml` con il nuovo contenuto e ritesta subito con `.\kubectl.exe --kubeconfig=.\local.yaml get pods -n macchinetta`.

---

## 🕯️ 3. Regola Chiusura Mercati Venerdì Sera (23:00) per H4 e Daily
- **Chiusura Weekend:** Il venerdì sera alle 23:00 (ora italiana) IG chiude tutti i mercati per il weekend.
- **Chiusura Anticipata H4 e D1:** Esclusivamente il venerdì sera, la candela **H4 (iniziata alle 21:00)** e la candela **Daily (D1 del venerdì)** devono **chiudersi tassativamente alle 23:00** e NON attendere le 01:00 del sabato mattina.
- **Implementazione nel codice:**
  - In `Motore_Trend.py` (`aggiorna_candele_live_stream`), la variabile `is_venerdi_23 = (now_t.weekday() == 4 and now_t.hour == 23)` impone la chiusura di H4 e D1 alle 23:00:00 consolidando i prezzi (O, H, L, C) dalle candele H1 orarie del venerdì.
  - La funzione di safeguard `garantisce_candele_venerdi_chiuse()` verifica e consolida automaticamente le candele H4 e D1 del venerdì alle 23:00 per tutto il fine settimana, evitando buchi o attese fino al sabato.

