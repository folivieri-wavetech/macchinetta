import os
import sys
import ssl
import time
import requests

# Disabilita controllo revoca Windows su Lightstreamer Demo
try:
    ssl._create_default_https_context = ssl._create_unverified_context
except Exception:
    pass

user, pwd, api_key = None, None, None
for p in ["FIORDOK_DEMO/.env", "DANY_DEMO/.env", ".env"]:
    if os.path.exists(p):
        with open(p, "r") as f:
            for l in f:
                l = l.strip()
                if l.startswith("IG_USERNAME="): user = l.split("=", 1)[1]
                elif l.startswith("IG_PASSWORD="): pwd = l.split("=", 1)[1]
                elif l.startswith("IG_API_KEY="): api_key = l.split("=", 1)[1]
        if user and pwd and api_key:
            print(f"Credenziali trovate in {p}: {user}")
            break

url_session = "https://demo-api.ig.com/gateway/deal/session"
h_session = {
    "X-IG-API-KEY": api_key,
    "Version": "2",
    "Accept": "application/json; charset=UTF-8",
    "Content-Type": "application/json; charset=UTF-8"
}
payload = {"identifier": user, "password": pwd}
r = requests.post(url_session, headers=h_session, json=payload, timeout=10)
print(f"Session status: {r.status_code}")
if r.status_code == 200:
    cst = r.headers.get("CST")
    xst = r.headers.get("X-SECURITY-TOKEN")
    d_resp = r.json()
    endpoint = d_resp.get("lightstreamerEndpoint")
    account_id = d_resp.get("currentAccountId")
    print(f"Endpoint: {endpoint}, Account: {account_id}")

    from lightstreamer_client import LightstreamerClient, LightstreamerSubscription
    ls = LightstreamerClient(account_id, f"CST-{cst}|XST-{xst}", endpoint)
    ls.connect()
    print("LS connected!")

    ticks = []
    def on_tick(item):
        vals = item.get("values", {})
        print("TICK:", vals)
        ticks.append(vals)

    sub = LightstreamerSubscription(mode="DISTINCT", items=["CHART:CS.D.CFEGOLD.CBE.IP:TICK"], fields=["BID", "OFR", "UTM"])
    sub.addlistener(on_tick)
    ls.subscribe(sub)
    print("Subscribed! Waiting 5s for ticks...")
    time.sleep(5)
    print(f"Ricevuti {len(ticks)} ticks.")
    ls.disconnect()
