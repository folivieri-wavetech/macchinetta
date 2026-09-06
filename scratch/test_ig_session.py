import os
import requests
import json
from dotenv import dotenv_values

cfg = dotenv_values("FIORDOK_DEMO/.env")
session = requests.Session()
resp = session.post("https://demo-api.ig.com/gateway/deal/session", 
                    json={"identifier": cfg.get("IG_USERNAME"), "password": cfg.get("IG_PASSWORD")}, 
                    headers={"X-IG-API-KEY": cfg.get("IG_API_KEY"), "Version": "2", "Content-Type": "application/json", "Accept": "application/json; charset=UTF-8"})

cst = resp.headers.get("CST")
xst = resp.headers.get("X-SECURITY-TOKEN")
headers = {"X-IG-API-KEY": cfg.get("IG_API_KEY"), "CST": cst, "X-SECURITY-TOKEN": xst, "Version": "3", "Accept": "application/json; charset=UTF-8"}

# Proviamo con diversi account o verifichiamo i prezzi live e i file locali
print("SESSION OK:", bool(cst))
