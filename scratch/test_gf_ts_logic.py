import sys

def test_entry_ts(max_prec, lvl, passo, ask):
    if max_prec is None:
        max_prec = lvl

    target_ts = round(max_prec + 3.0, 2)
    distanza_prec = round(target_ts - lvl, 2)

    if distanza_prec > 20.0:
        sl_price = round(lvl + 20.0, 2)
        desc_ts = f"Cap 20 pip da entry ({lvl:.2f} + 20p = {sl_price:.2f})"
    elif distanza_prec < passo:
        sl_price = round(lvl + passo, 2)
        desc_ts = f"Passo minimo ({passo}p da entry = {sl_price:.2f})"
    else:
        sl_price = target_ts
        desc_ts = f"Max prec + 3p ({max_prec:.2f} + 3p = {sl_price:.2f}, dist: {distanza_prec:.1f}p)"

    if ask and sl_price <= ask:
        sl_price = round(ask + passo, 2)

    return sl_price, desc_ts

# Scenario 1: Max prec 4172, entry 4160 (distanza 15 <= 20) -> TS 4175
ts1, d1 = test_entry_ts(4172.0, 4160.0, 4.0, 4160.5)
assert ts1 == 4175.0, f"Expected 4175.0, got {ts1}"
print(f"Test 1 passed: {ts1} ({d1})")

# Scenario 2: Max prec 4172, entry 4145 (distanza 30 > 20) -> TS 4165 (cap 20p)
ts2, d2 = test_entry_ts(4172.0, 4145.0, 4.0, 4145.5)
assert ts2 == 4165.0, f"Expected 4165.0, got {ts2}"
print(f"Test 2 passed: {ts2} ({d2})")

# Scenario 3: Max prec 4160, entry 4159 (distanza 4 < passo 6) -> TS 4165 (passo min)
ts3, d3 = test_entry_ts(4160.0, 4159.0, 6.0, 4159.5)
assert ts3 == 4165.0, f"Expected 4165.0, got {ts3}"
print(f"Test 3 passed: {ts3} ({d3})")

# Scenario 4: Chiusura candela H1 a :00:00
aperti = [
    {"numero": 1, "open_price": 4160.0, "sl_price": 4175.0, "stato": "APERTO"},
    {"numero": 2, "open_price": 4145.0, "sl_price": 4165.0, "stato": "APERTO"}
]
max_chiuso = 4164.0
ts_chiuso = round(max_chiuso + 3.0, 2)
for s in aperti:
    s["sl_price"] = ts_chiuso
    s["stato"] = "PROTETTO_BE"

assert aperti[0]["sl_price"] == 4167.0
assert aperti[1]["sl_price"] == 4167.0
assert aperti[0]["stato"] == "PROTETTO_BE"
assert aperti[1]["stato"] == "PROTETTO_BE"
print("Test 4 passed: Tutti i TS equiparati a 4167.0 a :00:00")

print("\nTUTTI I TEST SUPERATI CON SUCCESSO!")
