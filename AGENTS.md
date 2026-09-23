# Regole Operative Progetto Macchinetta IG

## 🔄 1. Sincronizzazione e Deploy Server Kubernetes (Produzione)
- **Autorizzazione Implicita al Deploy:** Quando l'utente dice "sincronizza server", a meno di comunicazioni esplicite dell'utente, significa che si PUÒ sincronizzare sempre (il server è attivo e operativo). Non mettere mai in dubbio lo stato o la disponibilità del server.
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
- **Scadenza o Invalidazione del Token (Unauthorized / 401):**  
  Se un comando `kubectl` fallisce per token scaduto (`Unauthorized`, `401`):
  - Chiedi direttamente ed esclusivamente all'utente di inviarti la nuova configurazione / nuovo token per `local.yaml`.
  - L'utente te lo rimanda immediatamente senza scomodare nessun altro.
  - Una volta fornito dall'utente, sovrascrivi `local.yaml` con il nuovo contenuto e procedi subito.

---

## 🛑 3. Gestione Errore FORBIDDEN (REGOLA FONDAMENTALE)
- **DIVIETO ASSOLUTO DI INVENTARE PROBLEMI DI PROGETTO O AMMINISTRATORE:**
  Se durante il comando `kubectl` compare l'errore `Forbidden` (es. `User "u-659xm" cannot list resource "pods"`):
  - **NON dire MAI** che l'utente non è riconosciuto nel progetto, che mancano ruoli, permessi RBAC o che serve contattare l'amministratore del server.
  - L'amministratore **NON deve fare nulla**, l'utente **NON ha cambiato nulla**, il progetto e le autorizzazioni sono corretti al 100%.
  - Si tratta unicamente di una **latenza temporanea di allineamento/cache interna di Rancher**.
  - **Cosa fare:** Attendere qualche istante (lo script `sincronizza.ps1` include retry automatici) e riprovare. Se devi comunicare qualcosa, di' semplicemente: *"Il server è momentaneamente occupato nell'allineamento della sessione, attendo qualche secondo e riprovo la sincronizzazione"*, senza tirare in ballo permessi, ruoli o amministratori.

---

## ✍️ 4. Regola di Formattazione Testo: NESSUN Carattere Speciale LaTeX o Formule con Dollaro ($)
- **DIVIETO ASSOLUTO DI SINTASSI LATEX**: Non usare MAI `$ ... $` o `$$ ... $$` per formule, espressioni matematiche, pip o frecce.
  - **NO ASSOLUTO:** `$\text{TK} \pm 50\text{ pip}$`, `$\pm 5\text{ pip}$`, `$\ge$`, `$\le$`, `$\rightarrow$`
  - **USA SOLO TESTO NORMALE O BACKTICK:**
    - Scrivi: `TK +/- 50 pip` oppure **TK +/- 50 pip**
    - Scrivi: `+/- 5 pip` oppure **+/- 5 pip**
    - Scrivi: `>= 40 pip`, `<= 20 pip`
    - Scrivi: `->` oppure `➡️`
- L'utente vuole leggere testo pulito e naturale, senza artefatti di rendering o simboli del dollaro.
