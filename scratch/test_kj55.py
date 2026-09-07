import json
import requests
from dotenv import dotenv_values
config = dotenv_values(".env")

auth_payload = {
    "identifier": config.get("IG_USERNAME"),
    "password": config.get("IG_PASSWORD")
}
headers = {
    "X-IG-API-KEY": config.get("IG_API_KEY"),
    "Content-Type": "application/json",
    "Accept": "application/json; charset=UTF-8",
    "Version": "2"
}

r = requests.post("https://demo-api.ig.com/gateway/deal/session", json=auth_payload, headers=headers)
if r.status_code == 200:
    cst = r.headers.get("CST")
    xst = r.headers.get("X-SECURITY-TOKEN")
    
    h3 = {
        "X-IG-API-KEY": config.get("IG_API_KEY"),
        "CST": cst,
        "X-SECURITY-TOKEN": xst,
        "Accept": "application/json",
        "Version": "3"
    }
    
    url = "https://demo-api.ig.com/gateway/deal/prices/CS.D.CFEGOLD.CBE.IP?resolution=HOUR&max=55&pageSize=0"
    r_prices = requests.get(url, headers=h3)
    if r_prices.status_code == 200:
        prices = r_prices.json().get('prices', [])
        print(f"Got {len(prices)} candles")
        highs = [p['highPrice']['bid'] for p in prices if p['highPrice'] and p['highPrice']['bid']]
        lows = [p['lowPrice']['bid'] for p in prices if p['lowPrice'] and p['lowPrice']['bid']]
        if highs and lows:
            kj55 = (max(highs) + min(lows)) / 2
            print(f"KJ55: {kj55}, Max High: {max(highs)}, Min Low: {min(lows)}")
    else:
        print("Price Error", r_prices.status_code, r_prices.text)
else:
    print("Login Failed")
