---
description: Critical rules for interacting with the IG API, specifically regarding historical data allowances and race conditions.
---

# IG API Quota & Historical Data Handling

## 1. Weekly Historical Data Allowance
IG Demo accounts have a strict historical data allowance of 10,000 data points per week. 
The `/prices` endpoint consumes this quota. Once exhausted, IG returns HTTP 403 `exceeded-account-historical-data-allowance` for the rest of the week (until reset on Sunday night).

## 2. Pod Race Condition Warning
The system runs multiple Kubernetes pods (e.g., FIORDOK, DANY, BONGIOLO). 
If these pods start simultaneously and the historical JSON files are missing from the shared PVC (`/data`), they will all attempt to download history at the same time.
- 10 instruments * 4 timeframes * 100 candles * 3 pods = 12,000 requests.
- This will instantly blow the weekly quota in a single second.

## 3. The Enforced Solution
To prevent this, `Motore_Trend.py` implements a staggered startup delay (`time.sleep`) based on the account name when downloading 100 candles. 
- Only one pod fetches the history.
- The other pods wait, check the shared PVC to see if the file is populated, and then read it directly, bypassing the API.

## 4. NEVER Delete Historical JSONs
NEVER delete the `candele_*.json` files from the PVC during the week unless you have a specific, safe plan to restore them without using the IG API, as doing so will force the system to attempt a fetch and potentially hit the quota limit.

## 5. Synthetic Fallback
If the quota is exhausted, `Motore_Trend.py` falls back to synthesizing candles tick-by-tick from live prices. It is critical that these synthesized candles are saved back to disk (`salva_candele_locali`) to prevent the historical data from freezing in time.
