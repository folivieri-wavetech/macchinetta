# Regole Operative Progetto Macchinetta IG

## 🔄 1. Sincronizzazione e Deploy Server Kubernetes (Produzione)
- **DIVIETO DI DEPLOY AUTOMATICO SENZA CONFERMA:** Non avviare MAI la sincronizzazione/deploy in autonomia dopo una modifica al codice. Chiedi SEMPRE preventivamente conferma all'utente ("Vuoi che sincronizzi il server ora?"). Un riavvio intempestivo dei pod mentre una candela M5 (o altro TF) è in corso di chiusura può causare disallineamenti operativi gravi.
- **Raggruppamento Modifiche (Batching):** Possiamo accumulare modifiche multiple in locale, verificarle con i test unitari e la compilazione, e sincronizzare il server in un unico passaggio solo quando l'utente decide di rilasciare il pacchetto.
- **Autorizzazione Implicita al Deploy:** Solo quando l'utente dice esplicitamente "sincronizza server" (o simile, oppure risponde affermativamente alla richiesta di deploy), si procede all'istante: il server è attivo, operativo e i permessi sul namespace `macchinetta` sono abilitati al 100%.
- **Metodo Ufficiale di Deploy:** Non si usa Docker (la virtualizzazione non è attiva sul PC ed è stata concordata e confermata la modalità diretta PVC/Kubernetes). I pod eseguono il codice direttamente dal volume condiviso Longhorn (`/data`).
- **Comando Unico di Sincronizzazione:**
  Per aggiornare il server, eseguire sempre:
  ```powershell
  powershell -ExecutionPolicy Bypass -File .\deploy\sincronizza.ps1 -MessaggioCommit "Descrizione modifiche"
  ```
  Questo script si occupa in automatico di:
  1. Verificare la sintassi Python (`py_compile`).
  2. Eseguire commit e push su GitHub (`master`).
  3. Copiare i file modificati (`Dashboard.py`, `Motore.py`, `Motore_Trend.py`, `hyper_tab.py`, `macchinetta_trend/`, `Sistema/`, ecc.) nella PVC `/data/` tramite `kubectl cp`.
  4. Riavviare i deployment (`kubectl rollout restart`).
  5. Eseguire l'health check HTTP su `https://macchinetta.wavetech.it`.

---

## 🔑 2. Gestione Token Profilo "marco" (`local.yaml`)
- Il kubeconfig si trova in `local.yaml` e usa il token associato all'utente **`marco`** (`u-659xm`).
- **Scadenza o Invalidazione del Token (Unauthorized / 401):**  
  Se un comando `kubectl` fallisce per token scaduto (`Unauthorized`, `401`):
  - Chiedi **direttamente ed esclusivamente all'utente** di inviarti la nuova configurazione / nuovo token per `local.yaml`.
  - L'utente accede a Rancher, fa "Copy KubeConfig" e te lo manda immediatamente senza scomodare nessun altro.
  - Una volta fornito dall'utente, sovrascrivi `local.yaml` con il nuovo contenuto e procedi subito con la sincronizzazione.

---

## 🛑 3. Disciplina Operativa Assoluta
- **DIVIETO DI CONGETTURE O TEORIE:**
  - Nessuna supposizione, discussione o congettura su server, ruoli, permessi o architettura.
  - L'amministratore sa esattamente cosa fare e ha impostato i permessi necessari: l'assistente esegue rigorosamente e celermente quanto ordinato dall'utente.

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

---

## 🚨 5. Parola Chiave di Sblocco Immediato: "REGOLE SERVER"
Se l'utente mi scrive semplicemente:
**`REGOLE SERVER`**

Alla ricezione di questo comando, devo:
1. **Zittirmi immediatamente** su qualsiasi commento o teoria.
2. **Riapplicare all'istante le regole**:
   - Regola 1: Il server è attivo e si sincronizza con `deploy\sincronizza.ps1`.
   - Regola 2: Se il token scade (401), si chiede solo all'utente.
   - Regola 3: Massima disciplina operativa senza congetture.
3. **Eseguire subito `deploy\sincronizza.ps1`** senza fare ulteriori domande o commenti inutili.

---

## 🛑 6. Distinzione Chiamate API IG: Operatività vs Dati Storici
- **OPERATIVITÀ A MERCATO (LIBERA):** Sei assolutamente libero e autorizzato a eseguire tutte le chiamate API necessarie per la normale operatività di trading: apertura/chiusura ordini a mercato, modifica stop loss, take profit, lettura posizioni aperte, streaming prezzi tick-by-tick.
- **DATI STORICI E CANDELE (DIVIETO ASSOLUTO SENZA AUTORIZZAZIONE):** Non sei ASSOLUTAMENTE libero di fare chiamate REST a IG per scaricare dati storici, candele, prezzi passati (`/gateway/deal/prices`) o qualsiasi richiesta che consumi quota dati e rischi di mandare il conto in errore 403 (allowance overflow).
- **PROCEDURA OBBLIGATORIA PER DATI STORICI:**
  1. L'assistente chiede preventivamente l'autorizzazione all'utente ("Posso richiedere dati storici candele a IG?").
  2. L'utente fa fare una verifica preventiva delle quote.
  3. Solo dopo l'esplicita autorizzazione dell'utente si può procedere; **altrimenti si sta fermi**.
- **UNICO CONTO AUTORIZZATO:** Quando autorizzato, l'unico ed esclusivo conto da utilizzare è **FIORDOK_DEMO** (MAI `DANY_DEMO` o altri conti). Nessun rischio di 403, poiché IG contatta direttamente l'utente via telefono.
