# PROCEDURA DI AUTENTICAZIONE E GESTIONE LOGIN BETFAIR.IT

Questo documento descrive in dettaglio l'architettura, i **soggetti** (entità e attori) coinvolti, le modalità di connessione e i meccanismi di mantenimento e rinnovo della sessione implementati per l'integrazione con l'Exchange di **Betfair.it**.

---

## 1. I "Soggetti" Coinvolti nell'Autenticazione

Il processo di connessione e autorizzazione sicura alle API di Betfair richiede il coordinamento di 6 soggetti fondamentali:

```
[Soggetto 1: Developer / App Key] ──┐
                                     ├──> [Soggetto 3: Gateway Identity SSO (.it)] ──> [Soggetto 5: Session Token]
[Soggetto 2: Utente / Conto Gioco] ──┤                                                        │
                                     │                                                        ▼
[Soggetto 4: Certificati SSL Client]─┘                                            [Soggetto 6: Exchange Gateway]
                                                                                   (Betting & Account API)
```

### Soggetto 1: L'Applicazione Sviluppatore (`App Key`)
* **Ruolo**: Identifica univocamente l'applicazione client registrata sul portale sviluppatori di Betfair.
* **Parametro**: `BETFAIR_APP_KEY` (inviata come header HTTP `X-Application`).
* **Tipologia di Chiave**:
  * **Delayed Key**: Dati quote ritardati, utilizzabile per sviluppo iniziale o test statici.
  * **Live Key**: Dati in tempo reale tick-by-tick e autorizzazione all'invio di ordini a mercato.
* **Specificità italiana**: La chiave deve essere generata ed essere valida per il circuito regolamentato italiano **Betfair.it** (ADM).

### Soggetto 2: L'Utente e il Conto Gioco (`Account Gioco`)
* **Ruolo**: Il titolare del conto Betfair su cui vengono effettuate le operazioni, verificate le disponibilità e piazzate le scommesse.
* **Parametri**: `BETFAIR_USERNAME` (email o nickname) e `BETFAIR_PASSWORD`.
* **Giurisdizione**: Conto verificato e residente in Italia, soggetto alle regole ADM (puntata minima di 2,00 EUR / 200 centesimi per scommesse tradizionali, gestione esposizione e autolimitazioni).

### Soggetto 3: Il Gateway di Identità Nazionale (`Identity SSO .it`)
* **Ruolo**: Il server Betfair deputato a validare l'identità dell'utente, l'App Key e a rilasciare il token di sessione.
* **Peculiarità Fondamentale**: A differenza dei conti globali (`.com`), i conti italiani devono autenticarsi **esclusivamente** sui domini `.it`.
* **Endpoint dedicati**:
  * Login standard (API Login): `https://identitysso.betfair.it/api/login`
  * Login certificato (CertLogin): `https://identitysso-cert.betfair.it/api/certlogin`
  * Mantenimento sessione (KeepAlive): `https://identitysso.betfair.it/api/keepAlive`
  * Chiusura sessione (Logout): `https://identitysso.betfair.it/api/logout`

### Soggetto 4: I Certificati SSL Client (Autenticazione Non-Interattiva)
* **Ruolo**: Coppia di chiavi crittografiche (Mutual TLS / mTLS) usata per autenticare processi automatici, demoni o bot 24/7 senza necessità di interazione umana o sfide captcha.
* **Componenti**:
  * Certificato Pubblico: file `.crt` (caricato anche nella sezione *API Security* del profilo Betfair).
  * Chiave Privata: file `.key` (conservata localmente in modo sicuro e mai condivisa).
* **Parametri nel codice**: `BETFAIR_CERT_FILE` e `BETFAIR_KEY_FILE` (opzionali; se omessi il client ricade automaticamente sul Login standard).

### Soggetto 5: Il Session Token (`ssoid` / `X-Authentication`)
* **Ruolo**: Il "lasciapassare" temporaneo generato dal server di autenticazione a fronte di credenziali valide.
* **Utilizzo**: Viene salvato in memoria nel client (`self.session_token`) e iniettato come header HTTP `X-Authentication` in ogni singola richiesta operativa.
* **Ciclo di vita**: Ha una validità massima standard di **8 ore (28.800 secondi)**. Se il conto rimane inattivo può scadere prima, a meno che non intervenga il KeepAlive.

### Soggetto 6: L'Exchange Gateway (Betting & Account API)
* **Ruolo**: I server applicativi di Betfair che gestiscono l'effettiva operatività di trading e consultazione:
  * **Betting API**: `https://api.betfair.com/exchange/betting/json-rpc/v1` (navigazione mercati, quote, ladder, immissione ordini, cancellazioni).
  * **Account API**: `https://api.betfair.com/exchange/account/json-rpc/v1` (saldo disponibile, esposizione corrente, dettagli conto).
* **Requisiti di accesso**: Accettano chiamate solo se provviste congiuntamente di `X-Application` (Soggetto 1) e `X-Authentication` (Soggetto 5).

---

## 2. Metodi di Login Implementati nel Software

La classe `BetfairClient` in `betfair_client.py` supporta tre livelli di accesso coordinati in cascata:

### Metodo 1: API Login Diretto (`login_api()`)
Ideale per sessioni operative desktop con credenziali dirette.
* **Target**: `https://identitysso.betfair.it/api/login`
* **Metodo HTTP**: `POST`
* **Headers**:
  * `X-Application`: App Key
  * `Content-Type`: `application/x-www-form-urlencoded`
  * `Accept`: `application/json`
* **Payload (Body)**:
  * `username`: username / email del conto
  * `password`: password in chiaro su canale TLS protetto
* **Esito positivo**:
  ```json
  {
    "token": "AK257K9e...O00Js=",
    "product": "...",
    "status": "SUCCESS"
  }
  ```

### Metodo 2: CertLogin con SSL Mutual TLS (`login_cert()`)
Progettato per bot e script continui con certificato client registrato.
* **Target**: `https://identitysso-cert.betfair.it/api/certlogin`
* **Metodo HTTP**: `POST`
* **TLS Client**: `cert=(cert_file, key_file)`
* **Headers**: identici all'API Login
* **Payload (Body)**: `username` e `password`
* **Esito positivo**:
  ```json
  {
    "sessionToken": "imwMJKqD...+O5r4=",
    "loginStatus": "SUCCESS"
  }
  ```

### Metodo 3: Auto-Login Intelligente (`auto_login()`)
È il metodo standard richiamato all'avvio dell'applicazione o dai thread di background:
1. Controlla se sono stati configurati i percorsi di `cert_file` e `key_file` e se entrambi i file esistono fisicamente sul disco.
2. Se presenti -> esegue `login_cert()`.
3. Se assenti o non validi -> esegue `login_api()`.
4. Salva il token risultante, imposta il timestamp di creazione (`token_created_at`) e rende il client immediatamente operativo.

---

## 3. Gestione e Manutenzione della Sessione nel Tempo

Per evitare interruzioni improvvise durante il monitoraggio dei mercati o l'esecuzione automatica delle strategie (BTS), sono stati implementati tre presidi di resilienza:

### A. KeepAlive Periodico (`keep_alive()`)
* **Endpoint**: `https://identitysso.betfair.it/api/keepAlive` (chiamata GET).
* **Scopo**: Segnala a Betfair che la sessione è viva, impedendo la disconnessione forzata per inattività.
* **Risultato**: Aggiorna il timestamp di attività della sessione.

### B. Monitoraggio Scadenza Naturale (`get_token_expiry_info()`)
* Calcola con precisione il tempo residuo prima della scadenza delle 8 ore standard.
* Restituisce:
  * `active`: stato di validità della sessione.
  * `expires_at`: orario stimato di scadenza.
  * `remaining_seconds`: secondi mancanti.
  * `formatted_remaining`: stringa leggibile (es. `7h 45m`).
  * `needs_renewal`: flag booleano che diventa `True` quando mancano meno di 30 minuti alla scadenza.

### C. Rinnovo Preventivo Trasparente (`check_and_renew_token()`)
* Un worker in background interroga periodicamente `check_and_renew_token(lead_time_minutes=30)`.
* Quando mancano meno di 30 minuti alla fine del ciclo delle 8 ore, il sistema esegue un nuovo `auto_login()` in sottofondo, sostituendo il session token senza mai far cadere i loop di polling quote, la UI di Streamlit o i manager degli ordini.

### D. Ripristino Automatico su Errore (`Auto-Recovery`)
Nelle chiamate JSON-RPC alle API Betting e Account, se Betfair restituisce l'errore:
* `INVALID_SESSION_INFORMATION`
* oppure `NO_APP_KEY` / `SECURITY_RESTRICTED`

Il client effettua istantaneamente un tentativo di `auto_login()` e riesegue la richiesta prima di sollevare eccezioni o fermare il ciclo.

---

## 4. Configurazione Locale e Sicurezza

Le credenziali e le impostazioni di connessione sono conservate in modo rigoroso e protetto:

### File `.env` (locale su macchina)
```env
# Configurazione Betfair.it API
BETFAIR_APP_KEY=tuo_app_key_qui
BETFAIR_USERNAME=tuo_username_qui
BETFAIR_PASSWORD=tua_password_qui

# Opzionale: percorsi certificati SSL se si usa CertLogin
# BETFAIR_CERT_FILE=certs/client-2048.crt
# BETFAIR_KEY_FILE=certs/client-2048.key
```

### File `.gitignore`
Il file `.gitignore` del repository esclude tassativamente:
* File `.env`
* Cartelle `certs/`, chiavi `.key`, certificati `.crt` e `.pem`
* Qualsiasi file di log o dump contenente token di sessione completi

---

## 5. Script di Collaudo Rapido (`test_login.py`)

Per verificare in ogni momento la validità delle credenziali e lo stato dei server Betfair.it è disponibile lo script di test da riga di comando:

```bash
# Esecuzione usando le variabili definite in .env
python test_login.py

# Oppure esecuzione con parametri espliciti
python test_login.py --app-key <KEY> --username <USER> --password <PASS>
```

Lo script esegue la sequenza completa in 3 passi:
1. **Autenticazione**: invio richiesta a `identitysso.betfair.it` ed estrazione del Session Token.
2. **Account API**: verifica chiamata `getAccountFunds` (saldo disponibile ed esposizione).
3. **Betting API**: verifica chiamata `listEventTypes` (elenco mercati sportivi attivi sull'Exchange).
