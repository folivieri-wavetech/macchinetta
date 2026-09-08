---
description: Regole di ferro per la gestione della quota dati storici IG (/prices) e accumulo candele live.
---

# Regola di Ferro: Quota IG e Accumulo Candele Live

## 1. Limite Quota IG Settimanale
* I conti IG hanno un tetto massimo di **10.000 punti dati storici a settimana** (reset la domenica notte).
* L'endpoint `/prices` consuma punti proporzionali al `limit`.
* Una volta esaurita la quota, IG restituisce HTTP 403 `exceeded-account-historical-data-allowance` fino al reset settimanale.

## 2. Divieto Assoluto di Polling Continuo su `/prices`
* **MAI** interrogare l'endpoint `/prices` di IG ad ogni chiusura candela (M5, H1, H4, D1).
* Interrogare 10 strumenti ogni 5 minuti consuma 5.760 punti/giorno, bruciando la quota in meno di 48 ore.
* A regime continuo, le candele devono essere formate e chiuse al **100% dall'accumulo locale dei tick streaming di IG** (`prezzi_live` via Lightstreamer), che è gratuito, illimitato e non consuma quota.

## 3. Chiamata Seed UNA TANTUM all'Avvio
* Se i file JSON locali non hanno almeno 55 candele (necessarie per Donchian TK 21 e KJ 55), viene eseguita una sola chiamata iniziale con `limit=60`.
* 10 strumenti * 60 = 600 punti consumati su 10.000 (consumo pari al 6%).
* **Regola Multi-Pod (PVC condivisa):** Solo il pod principale effettua il download; gli altri pod attendono e leggono il file condiviso dalla PVC `/data`, consumando 0 chiamate API.

## 4. MAI usare servizi terzi non autorizzati
* Non usare Yahoo Finance né altri feed esterni per il trading live. Lo streaming tick di IG è l'unica fonte di verità del broker.

## 5. Procedura Lunedì (Reset Quota)
* Alla riapertura settimanale, non scaricare a raffica:
  * Se i file locali sono già popolati, proseguire con l'accumulo live.
  * Se serve colmare il gap del weekend, fare una singola chiamata una tantum per strumento (`limit=60`) e poi passare all'accumulo live.
