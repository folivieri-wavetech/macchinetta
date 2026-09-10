import requests
import json
from dotenv import dotenv_values

cfg = dotenv_values("DANY_DEMO/.env")
ak = cfg.get("IG_API_KEY")
un = cfg.get("IG_USERNAME")
pw = cfg.get("IG_PASSWORD")

h = {"X-IG-API-KEY": ak, "Version": "2", "Content-Type": "application/json"}
p = {"identifier": un, "password": pw}
r = requests.post("https://demo-api.ig.com/gateway/deal/session", headers=h, json=p, timeout=10)
print("DANY LOGIN STATUS:", r.status_code)
print("RESPONSE:", r.text[:300])
