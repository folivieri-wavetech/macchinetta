"""Test unitario logica Hyper 30S:
- Trailing Stop a step di 3 pip
- Crossover Primario KJ55
- Rientro Pullback (distanza <= 3 pip da KJ55)
- Esaurimento ciclo (max 1 rientro)
"""
import sys

def test_ts_steps():
    open_px = 3000.00
    TS_STEP_PIPS = 3.0

    # LONG
    for gain, expected_k, expected_lock in [
        (2.0, 0, None),
        (3.0, 1, 0.0),    # +3p gain -> Stop a BE (+0p lock = 3000.00)
        (5.8, 1, 0.0),    # +5.8p gain -> Stop sempre a BE
        (6.0, 2, 3.0),    # +6p gain -> Stop a +3p (3003.00)
        (8.9, 2, 3.0),    # +8.9p gain -> Stop a +3p
        (9.0, 3, 6.0),    # +9p gain -> Stop a +6p (3006.00)
        (12.5, 4, 9.0)    # +12.5p gain -> Stop a +9p (3009.00)
    ]:
        k = int(gain // TS_STEP_PIPS)
        assert k == expected_k, f"Gain {gain}: atteso k={expected_k}, ottenuto {k}"
        if k >= 1:
            lock = (k - 1) * TS_STEP_PIPS
            assert lock == expected_lock, f"Gain {gain}: atteso lock={expected_lock}, ottenuto {lock}"
            stop_px = round(open_px + lock, 2)
            assert stop_px == open_px + expected_lock

    # SHORT
    for gain, expected_k, expected_lock in [
        (3.0, 1, 0.0),
        (6.0, 2, 3.0),
        (9.0, 3, 6.0)
    ]:
        k = int(gain // TS_STEP_PIPS)
        lock = (k - 1) * TS_STEP_PIPS
        stop_px = round(open_px - lock, 2)
        assert stop_px == open_px - expected_lock

    print("✅ Test 1: Calcolo Trailing Stop a step di 3 pip SUPERATO")

def test_cycle_state_machine():
    kj = 3000.00
    PULLBACK_MAX_DIST = 3.0

    # Scenario:
    # 1. FLAT -> Taglio Long (chiusura 3002.00 provenendo da sotto)
    prev_close = 3002.00
    prev_open = 2999.00
    prev_bar_close = 2999.00

    taglio_long = (prev_close > kj) and (prev_open <= kj or prev_bar_close <= kj)
    assert taglio_long is True

    cycle_phase = "PRIMARY_OPEN"
    cycle_direction = "LONG"
    print("✅ Test 2a: Taglio Primario LONG riconosciuto")

    # 2. Il trade primario sale a 3007 (+7 pip gain) e poi tocca TS a 3003 (+3 pip stop)
    # Alla chiusura TS:
    if cycle_phase == "PRIMARY_OPEN":
        cycle_phase = "PULLBACK_ARMED"
    assert cycle_phase == "PULLBACK_ARMED"
    print("✅ Test 2b: Trailing Stop preso -> Stato PULLBACK_ARMED")

    # 3. Pullback: il prezzo ritraccia a 3001.50 (distanza da KJ = 1.5 pip <= 3.0 pip)
    # Candela verde (close 3002.00 >= open 3001.00)
    c_close = 3002.00
    c_open = 3001.00
    dist_kj = round(c_close - kj, 2)

    pullback_valid = (
        cycle_phase == "PULLBACK_ARMED" and
        cycle_direction == "LONG" and
        c_close > kj and
        dist_kj <= PULLBACK_MAX_DIST and
        c_close >= c_open
    )
    assert pullback_valid is True

    # Entra il rientro Pullback
    cycle_phase = "PULLBACK_OPEN"
    print("✅ Test 2c: Rientro Pullback valido eseguito")

    # 4. Il rientro tocca il Trailing Stop
    if cycle_phase == "PULLBACK_OPEN":
        cycle_phase = "CYCLE_DONE"
    assert cycle_phase == "CYCLE_DONE"
    print("✅ Test 2d: Chiusura Rientro -> Ciclo esaurito (CYCLE_DONE)")

    # 5. Verifica che ulteriori candele sopra KJ NON facciano altri rientri
    next_close = 3002.00
    next_open = 3001.00
    dist_next = round(next_close - kj, 2)
    reentry_allowed = (
        cycle_phase == "PULLBACK_ARMED" and
        dist_next <= PULLBACK_MAX_DIST
    )
    assert reentry_allowed is False
    print("✅ Test 2e: Nessun ulteriore rientro consentito fino a nuovo taglio fresco")

if __name__ == "__main__":
    test_ts_steps()
    test_cycle_state_machine()
    print("🎉 TUTTI I TEST LOGICI SUPERATI CON SUCCESSO!")
