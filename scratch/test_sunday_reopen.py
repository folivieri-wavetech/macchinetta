import datetime

TF_MAP = {"HOUR": 60, "HOUR_4": 240, "DAY": 1440}

print("=== VERIFICA COMPORTAMENTO CANDELAE DOMENICA SERA -> LUNEDI MATTINA ===")

# Domenica sera ore 22:00, 22:59, 23:00, 23:59
# Lunedì notte ore 00:00, 00:59, 01:00

test_times = [
    (datetime.datetime(2026, 9, 13, 22, 0), "Domenica 22:00 (Riapertura IG)"),
    (datetime.datetime(2026, 9, 13, 22, 30), "Domenica 22:30"),
    (datetime.datetime(2026, 9, 13, 22, 59), "Domenica 22:59"),
    (datetime.datetime(2026, 9, 13, 23, 0), "Domenica 23:00"),
    (datetime.datetime(2026, 9, 13, 23, 30), "Domenica 23:30"),
    (datetime.datetime(2026, 9, 13, 23, 59), "Domenica 23:59"),
    (datetime.datetime(2026, 9, 14, 0, 0), "Lunedi 00:00"),
    (datetime.datetime(2026, 9, 14, 0, 30), "Lunedi 00:30"),
    (datetime.datetime(2026, 9, 14, 0, 59), "Lunedi 00:59"),
    (datetime.datetime(2026, 9, 14, 1, 0), "Lunedi 01:00 (Boundary H4/D1)")
]

for dt, desc in test_times:
    min_tot = dt.hour * 60 + dt.minute
    base_dt = dt.replace(hour=0, minute=0, second=0, microsecond=0)
    print(f"\n--- {desc} ---")
    for tf in ["HOUR", "HOUR_4", "DAY"]:
        min_tf = TF_MAP[tf]
        offset = 60 if min_tf in (60, 240, 1440) else 0
        boundary_min = ((min_tot - offset) // min_tf) * min_tf + offset
        curr_dt = base_dt + datetime.timedelta(minutes=boundary_min)
        curr_snap = curr_dt.strftime("%Y/%m/%d %H:%M:00")
        print(f"  {tf:7s} -> boundary_min={boundary_min:4d} | snap_iniziale={curr_snap}")
