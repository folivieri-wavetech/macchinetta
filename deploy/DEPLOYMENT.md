# Deploy — Macchinetta (namespace `macchinetta`)

> Documento operativo per aggiornare il progetto **Macchinetta** (bot di trading IG Markets)
> in esecuzione su Rancher/K3s nel namespace `macchinetta`, host `https://macchinetta.wavetech.it`.
> Pensato per essere eseguito da un agente AI: contiene comandi esatti, vincoli e storico dei fix.

---

## 1. Panoramica

Il sistema è composto da:

| Componente | Tipo | Descrizione |
|---|---|---|
| **Dashboard** | Deployment `macchinetta-dashboard` | App Streamlit (`Dashboard.py`), porta 8501, esposta su `macchinetta.wavetech.it` |
| **Motore BONGIOLO** | Deployment `macchinetta-motore-bongiolo` | Esegue `Motore.py BONGIOLO_DEMO` |
| **Motore DANY** | Deployment `macchinetta-motore-dany` | Esegue `Motore.py DANY_DEMO` |
| **Motore FIORDOK** | Deployment `macchinetta-motore-fiordok` | Esegue `Motore.py FIORDOK_DEMO` |
| **PVC `macchinetta-data`** | RWX su Longhorn (2Gi) | Condivisa da TUTTI i pod; contiene codice eseguito + dati runtime |
| **Secret `macchinetta-secrets`** | Kubernetes Secret | Credenziali IG dei conti + login Dashboard |
| **ConfigMap `macchinetta-init`** | Script `seed.sh` | Init container: semina codice nella PVC e inietta `.env` |

### Flusso dati

- I **Motori** interrogano le API IG (`https://demo-api.ig.com/gateway/deal`) e scrivono, nella propria cartella conto
  (`/data/<CONTO>/`): `memoria_parametri.json`, `stato_sistema.json`, `storico_operazioni.csv`, `token_ig.json`, `console_live.log`.
- La **Dashboard** NON parla con IG: legge i file dalla PVC condivisa (tab aggiornati ogni 15s via `@st.fragment(run_every=15)`).
- La Dashboard monta la PVC su `/data` e usa `workingDir=/data`; il conto selezionato è la cartella `/data/<CONTO>`.

---

## 2. Prerequisiti e accesso

- **Kubeconfig**: `/Users/francescoolivieri/Desktop/macchinetta/local.yaml`
  (Rancher, cluster `rancher.wavetech.it/k8s/clusters/local`, context `local`).
  Usare sempre: `export KUBECONFIG=/Users/francescoolivieri/Desktop/macchinetta/local.yaml`
- **Cluster**: singolo nodo `rancher-wavetech` → **amd64** (K3s v1.34.3). Il Mac locale è **arm64**.
- **Registry**: `docker.wavetech.it` (pull/push già autenticato via Docker Desktop).
- **Repo**: `https://github.com/folivieri-wavetech/macchinetta.git` (branch `master`).

> ⚠️ **Vincolo architettura**: l'immagine DEVE essere multi-arch `linux/amd64,linux/arm64`,
> altrimenti `exec format error` sul nodo amd64 (mac arm64 → immagine arm64 pura).

---

## 3. Struttura dei file di deploy

Tutti i file sotto `/deploy/` del repo (da applicare con `kubectl apply -f <file>`):

| File | Contenuto |
|---|---|
| `namespace.yaml` | Namespace `macchinetta` |
| `pvc.yaml` | PVC `macchinetta-data`, RWX, `longhorn`, 2Gi |
| `configmap-init.yaml` | `seed.sh` — init container di seeding |
| `dashboard.yaml` | Deployment + Service `macchinetta-dashboard` (80→8501) |
| `motore.yaml` | 3 Deployment dei motori (uno per conto) |
| `ingress.yaml` | Host `macchinetta.wavetech.it`, TLS `macchinetta-dashboard-tls`, issuer `letsencrypt-prod` |

Altri file: `Dockerfile`, `requirements.txt`, `.dockerignore`.

### Come funziona il seeding della PVC (CRITICO)

`seed.sh` (ConfigMap `macchinetta-init`) eseguito dall'init container di OGNI pod:

```sh
if [ ! -f /data/Dashboard.py ]; then
  cp -a /app/. /data/            # copia il progetto SOLO se la PVC è vuota
fi
for c in BONGIOLO DANY FIORDOK; do
  printf '%s\n' "$env_content" > "/data/${c}_DEMO/.env"   # sempre: riscrive .env dal Secret
done
```

Conseguenze:
1. **Il codice NON si propaga automaticamente**: `cp -a` avviene solo la prima volta.
   Le immagini nuove NON aggiornano `/data/Dashboard.py` / `/data/Motore.py`.
2. I file `.env` vengono invece REWRITTEN a ogni avvio del pod dal Secret → per cambiare
   le credenziali IG basta aggiornare il Secret e riavviare i pod.

---

## 4. Workflow di aggiornamento (passo-passo)

### 4.1 Modifica del codice

1. Lavorare sul clone locale del repo (qui: `/var/folders/.../opencode/macchinetta`).
2. Modificare `Dashboard.py` / `Motore.py` / `Simulatore_*.py` / `requirements.txt` ecc.
3. Verifica sintassi: `python3 -m py_compile Dashboard.py Motore.py`.

### 4.2 Build e push dell'immagine (multi-arch)

```bash
# se il builder "multi" non esiste:
docker buildx create --name multi --driver docker-container --use

docker buildx build --builder multi \
  --platform linux/amd64,linux/arm64 \
  -t docker.wavetech.it/macchinetta:latest \
  -t docker.wavetech.it/macchinetta:$(date +%Y%m%d%H%M) \
  --push .
```

### 4.3 Propagare il codice nella PVC

L'immagine da sola NON basta. Dopo il push, sincronizzare i file cambiati nella PVC:

```bash
POD_DASH=$(kubectl get pod -n macchinetta -l component=dashboard -o jsonpath='{.items[0].metadata.name}')

# file "di codice" che i pod eseguono da /data
kubectl cp Dashboard.py "macchinetta/$POD_DASH:/data/Dashboard.py"
kubectl cp Motore.py    "macchinetta/$POD_DASH:/data/Motore.py"
# (la PVC è RWX condivisa: scrivere da un pod aggiorna per tutti)
```

Alternativa "resync totale" (riscrive tutta la struttura dal codice immagine):

```bash
kubectl exec -n macchinetta "$POD_DASH" -- rm -f /data/Dashboard.py /data/Motore.py
kubectl rollout restart deploy -n macchinetta
# l'init del pod che riparte ri-esegue cp -a /app/. /data/
```

### 4.4 Rollout (Regola Riavvi Selettivi)

> ⚠️ **IMPORTANTE:** Per evitare disconnessioni inutili all'utente o riavvii dei bot non necessari, applicare sempre la regola del riavvio selettivo.

- **Se si è modificato SOLTANTO il Core/Motore (`Motore.py`, etc.):**
  Riavviare unicamente i motori, lasciando inalterata la Dashboard.
  ```bash
  kubectl rollout restart deploy/macchinetta-motore-bongiolo deploy/macchinetta-motore-dany deploy/macchinetta-motore-fiordok -n macchinetta
  ```

- **Se si è modificata SOLTANTO l'Interfaccia (`Dashboard.py`, `Dashboard_Simulatore.py`, etc.):**
  Riavviare unicamente la Dashboard, lasciando in esecuzione i motori.
  ```bash
  kubectl rollout restart deploy/macchinetta-dashboard -n macchinetta
  kubectl rollout status deploy/macchinetta-dashboard -n macchinetta --timeout=180s
  ```

- **Se si sono modificati ENTRAMBI:**
  Riavviare tutti i deployment usando entrambi i comandi.


### 4.5 Verifica

```bash
# versione Streamlit realmente in esecuzione
kubectl exec -n macchinetta deploy/macchinetta-dashboard -- python -c "import streamlit; print(streamlit.__version__)"

# salute app
curl -s -o /dev/null -w "%{http_code}\n" https://macchinetta.wavetech.it/_stcore/health   # 200

# motori connessi a IG
kubectl logs -n macchinetta deploy/macchinetta-motore-bongiolo --tail=20 | grep -i "connesso\|errore"

# file generati nella PVC
kubectl exec -n macchinetta deploy/macchinetta-dashboard -- ls -la /data/FIORDOK_DEMO/
```

Checklist finale:
- [ ] `/_stcore/health` → 200
- [ ] Dashboard raggiungibile e login OK (`Marco` / dal Secret)
- [ ] 3 motori `1/1 Running` e log `Connesso a IG con successo!`
- [ ] File runtime presenti in `/data/<CONTO>/` (aggiornamento mtime recente)
- [ ] Nessuna eccezione nei log della Dashboard

---

## 5. Credenziali e Secret

Secret: `kubectl get secret macchinetta-secrets -n macchinetta -o yaml`

| Chiave | Contenuto |
|---|---|
| `BONGIOLO_DEMO_ENV` | Contenuto del file `.env` del conto BONGIOLO_DEMO |
| `DANY_DEMO_ENV` | Contenuto del file `.env` del conto DANY_DEMO |
| `FIORDOK_DEMO_ENV` | Contenuto del file `.env` del conto FIORDOK_DEMO |
| `DASHBOARD_USER` | Utente login Dashboard |
| `DASHBOARD_PASSWORD` | Password login Dashboard |

Il `.env` di un conto usa le chiavi lette da `Motore.py` (`dotenv_values(".env")`):

```
IG_USERNAME=...
IG_PASSWORD=...
IG_API_KEY=...
NTFY_TOPIC=...
```

Per aggiornare un `.env`: modificare il Secret (vedi `kubectl create secret generic ... --from-literal`) e riavviare i pod
(l'init container riscrive `/data/<CONTO>/.env` a ogni avvio).

---

## 6. Fix applicati al primo avvio (storico — NON rimuovere)

Questi sono i fix necessari per far girare il progetto sul container Linux.

### F1. `Motore.py` — import `winsound` (Windows-only) 🔴 critico
- **Problema**: `import winsound` fa crashare il Motore su Linux (`python:3.11-slim`).
- **Fix**: import condizionale in `try/except ImportError` e `suona_drumroll()` che fa no-op se `winsound is None`.
- **File**: `Motore.py` (~righe 9-25).

### F2. `Dashboard.py` — credenziali login da ambiente 🔴 critico
- **Problema**: credenziali Dashboard hardcoded nel sorgente.
- **Fix**: `CREDENTIALS = {os.getenv("DASHBOARD_USER","Marco"): os.getenv("DASHBOARD_PASSWORD","Bolzano&1971")}`.
- **File**: `Dashboard.py` riga ~20. Il Secret `macchinetta-secrets` le fornisce a runtime.

### F3. `requirements.txt` — bump Streamlit `1.37.0` → `1.50.0` 🔴 critico
- **Problema**: `Dashboard.py` usa `st.button(..., width="stretch", ...)` (~13 punti: righe 288, 940,
  956, 1007, 1020, 1055, 1063, 1068, 1075, 1080, 1093, 1101, 1107, 1112) e `use_container_width=True`
  (riga 915). Il parametro `width` è stato introdotto in **Streamlit 1.48** → con 1.37.0 crash:
  `TypeError: ButtonMixin.button() got an unexpected keyword argument 'width'`.
- **Fix**: `streamlit==1.50.0` (range sicuro 1.48–1.51; da 1.52 `use_container_width` viene rimosso).
- **File**: `requirements.txt`.

### F4. `Dashboard.py` — banner Sintesi con HTML non renderizzato 🟠 non bloccante
- **Problema**: su Streamlit 1.50 il parser markdown NON rende più il blocco HTML multilinea del banner
  del tab Sintesi (mostrava il codice HTML come testo; tutti gli altri `unsafe_allow_html` funzionavano).
- **Fix**: sostituito `st.markdown(f"""...""", unsafe_allow_html=True)` con `st.html(f"""...""")`
  (riga ~819) — API raccomandata da Streamlit per HTML grezzo.
- **File**: `Dashboard.py`.

### F5. Multi-arch image 🔴 critico (infrastruttura)
- **Problema**: primo build solo `linux/arm64` (Mac) → `exec format error` sul nodo amd64.
- **Fix**: build multi-arch `linux/amd64,linux/arm64` con `docker buildx build --builder multi ... --push`.

---

## 7. Operazioni ricorrenti

### Log della Dashboard
```bash
kubectl logs -n macchinetta deploy/macchinetta-dashboard --tail=50
```

### Log di un Motore
```bash
kubectl logs -n macchinetta deploy/macchinetta-motore-bongiolo --tail=50
```

### Rollback
- Immagini versionate con timestamp: le precedenti restano sul registry (`docker.wavetech.it/macchinetta:<ts>`).
- Per ripristinare codice: ricopiare la versione voluta in `/data` via `kubectl cp` e `rollout restart`.

### Aggiungere un nuovo conto
1. Aggiungere la chiave `<NOME>_DEMO_ENV` al Secret `macchinetta-secrets`.
2. Aggiungere `<NOME>` al loop `for c in ...` di `deploy/configmap-init.yaml`.
3. Nuovo Deployment motore in `deploy/motore.yaml` (copy-paste di uno esistente, cambiando
   nome, label `account`, e `command: ["python","/data/Motore.py","<NOME>_DEMO"]`).
4. `kubectl apply -f deploy/configmap-init.yaml -f deploy/motore.yaml` + restart dashboard.

### Commit su GitHub
I file infra (`Dockerfile`, `requirements.txt`, `.dockerignore`, `deploy/`) e i fix F1-F4
**non sono ancora committati** (stato: `M Dashboard.py`, `M Motore.py`, `?? Dockerfile ...`).
Prima volta: `git add` + commit con messaggio tipo `deploy: containerizzazione Kubernetes (namespace macchinetta)`.

---

## 8. Troubleshooting

| Sintomo | Causa probabile | Soluzione |
|---|---|---|
| `exec format error` al deploy | immagine solo arm64 | rebuild multi-arch (sez. 4.2) |
| Dashboard ancora vecchia dopo rebuild | codice non propagato in PVC (sez. 4.3) | `kubectl cp` i file in `/data` + rollout |
| `TypeError: ... unexpected keyword argument 'width'` | Streamlit < 1.48 | verificare `streamlit.__version__`; bump requirements (F3) |
| Banner Sintesi mostra HTML grezzo | parser markdown 1.50 su blocco multilinea | usare `st.html` (F4) |
| `st.session_state has no key "$$WIDGET_ID..."` | sessione browser obsoleta dopo rollout | refresh F5 / nuova sessione |
| Motore crash `import winsound` | winsound non esiste su Linux | fix F1 presente |
| Motore "già in esecuzione" | lock socket 127.0.0.1 ancora attivo | attendere rilascio o riavviare il pod |
| Certificato non emesso | ingress/app non pronto | verificare `kubectl get certificate -n macchinetta`, logs cert-manager |

---

## 9. Riferimenti rapidi

```bash
export KUBECONFIG=/Users/francescoolivieri/Desktop/macchinetta/local.yaml
NS=macchinetta
kubectl -n $NS get deploy,pods,svc,ingress,pvc
kubectl -n $NS describe pod -l component=dashboard
kubectl -n $NS logs deploy/macchinetta-dashboard --tail=50
```