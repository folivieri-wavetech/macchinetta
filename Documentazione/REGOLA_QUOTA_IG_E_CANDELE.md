# Regola di Ferro: Gestione Quota IG e Storico Candele

## Contesto e Limiti del Broker (IG)
* **Tetto settimanale IG:** 10.000 punti dati storici a settimana per conto/chiave API.
* **Reset della quota:** Ogni domenica notte (tra le 22:00 e le 00:00 UTC).
* **Endpoint che consuma la quota:** `GET /prices` (ogni candela richiesta consuma punti proporzionali al `limit`).
* **Streaming Lightstreamer:** Gratuito, illimitato e attivo 24/7 (zero consumo di quota).

---

## Le 3 Regole Fondamentali

### 1. ZERO chiamate periodiche a `/prices`
È severamente vietato interrogare l'endpoint `/prices` ad ogni candela (M5, H1, H4, D1).
* 10 strumenti * 288 candele M5/giorno * 2 punti = 5.760 punti/giorno.
* Chiamare periodicamente IG esaurisce la quota in meno di 48 ore.
* A regime continuo, le candele vengono **costruite e chiuse al 100% dall'accumulo locale dei tick streaming di IG** (`prezzi_live`), con costo API = 0.

### 2. Chiamata "Seed" UNA TANTUM all'avvio
Se lo storico locale è vuoto (es. prima installazione da zero):
* Si effettua **una sola chiamata per strumento** con `limit=60` (bastano 55 candele per la Kijun-sen a 55 periodi).
* 10 strumenti * 60 candele = **600 punti consumati** (il 6% del tetto settimanale di 10.000, lasciando il 94% di sicurezza).
* **Regola Multi-Pod (PVC condivisa):** Solo il pod principale (`FIORDOK`) effettua la chiamata; gli altri pod (`DANY` e `BONGIOLO`) attendono e leggono lo stesso file JSON da `/data`, consumando 0 chiamate API.

### 3. Procedura di Colmatura Gap (dopo fermo macchina prolungato)
Se il motore rimane spento per diverse ore:
* Calcola esattamente il numero di candele mancanti dall'ultimo timestamp registrato.
* Effettua una sola chiamata con `limit = min(gap_candele, 60)`.
* Riprende immediatamente l'accumulo live dallo streaming.

---

## Procedura per Lunedì Prossimo (Reset Quota)
Quando la quota si resetta la domenica notte / lunedì mattina:
1. Verificare lo stato della quota eseguendo il controllo centralizzato (`ig_quota_status.json`).
2. Se i file locali hanno accumulato candele durante la settimana, **NON serve scaricare nulla**: lo storico è già continuo e intatto.
3. Se serve una sincronizzazione di controllo, lanciare una scansione controllata `limit=60` una sola volta per allineare eventuali buchi del weekend.
4. Mantenere l'accumulo live streaming attivo senza mai riattivare il polling continuo su `/prices`.
