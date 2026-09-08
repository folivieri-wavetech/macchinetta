"""
Test di verifica del blocco Kijun per avvio manuale LONG/SHORT
"""
def check_manual_start_allowed(direzione, px_start, kj_val):
    if kj_val is not None and px_start is not None:
        if direzione == "SHORT" and px_start > kj_val:
            return False, f"🛑 Avvio SHORT BLOCCATO: Prezzo ({px_start}) > Kijun ({kj_val})."
        elif direzione == "LONG" and px_start < kj_val:
            return False, f"🛑 Avvio LONG BLOCCATO: Prezzo ({px_start}) < Kijun ({kj_val})."
    return True, "OK"

# Caso dell'utente: USDCHF Live=0.81000, KJ=0.80890
kj_user = 0.80890
live_user = 0.81000

# 1. Test SHORT con Live > KJ -> Deve essere BLOCCATO
ok_short, msg_s = check_manual_start_allowed("SHORT", live_user, kj_user)
assert not ok_short, "Lo SHORT doveva essere bloccato!"
print("Test 1 Superato:", msg_s)

# 2. Test LONG con Live > KJ -> Deve essere CONSENTITO
ok_long, msg_l = check_manual_start_allowed("LONG", live_user, kj_user)
assert ok_long, "Il LONG doveva essere consentito!"
print("Test 2 Superato: LONG consentito quando Live > KJ")

# 3. Caso speculare: Prezzo sceso sotto KJ (es. Live=0.80800, KJ=0.80890)
live_below = 0.80800

# Test LONG con Live < KJ -> Deve essere BLOCCATO
ok_long_below, msg_lb = check_manual_start_allowed("LONG", live_below, kj_user)
assert not ok_long_below, "Il LONG sotto KJ doveva essere bloccato!"
print("Test 3 Superato:", msg_lb)

# Test SHORT con Live < KJ -> Deve essere CONSENTITO
ok_short_below, msg_sb = check_manual_start_allowed("SHORT", live_below, kj_user)
assert ok_short_below, "Lo SHORT sotto KJ doveva essere consentito!"
print("Test 4 Superato: SHORT consentito quando Live < KJ")

print("\n TUTTI I TEST UNITARI HANNO AVUTO SUCCESSO! ")
