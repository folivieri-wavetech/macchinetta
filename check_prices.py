import json
import os
import requests
from dotenv import dotenv_values

os.chdir("FIORDOK_DEMO")
with open("stato_sistema.json", "r") as f:
    stato = json.load(f)
    prezzi_live = stato.get("prezzi_live", {})
    print(f"Prezzi Live in stato_sistema: {prezzi_live}")

config = dotenv_values("../.env")
with open("token_ig.json", "r") as f:
    token = json.load(f)

headers = {
    "X-IG-API-KEY": config.get("IG_API_KEY"),
    "CST": token.get("CST"),
    "X-SECURITY-TOKEN": token.get("X-SECURITY-TOKEN"),
    "Accept": "application/json",
    "Version": "3"
}

for epic in ["CS.D.CFEGOLD.CBE.IP", "IX.D.SPTRD.IBE.IP", "CS.D.EURGBP.MINI.IP"]:
    url = f"https://demo-api.ig.com/gateway/deal/prices/$epic?resolution=DAY&max=2&pageSize=0"
    url = url.replace("$epic", epic)
    r = requests.get(url, headers=headers)
    if r.status_code == 200:
        prices = r.json().get('prices', [])
        print(f"[{epic}] History DAY API: {prices[-1] if prices else 'NO DATA'}")
    else:
        print(f"[{epic}] Error API: {r.status_code} - {r.text}")
