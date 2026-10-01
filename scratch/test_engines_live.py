import time
from hyper_gold_m5_engine import HyperGoldM5Engine
from hyper_us500_m5_engine import HyperUS500M5Engine

print("Starting engines...")
g = HyperGoldM5Engine.get_instance("FIORDOK_DEMO")
u = HyperUS500M5Engine.get_instance("FIORDOK_DEMO")

for i in range(8):
    time.sleep(1)
    print(f"[{i+1}s] Gold conn: {g.ls_connected} (ticks: {g.total_ticks}, mid: {g.live_mid}) | US500 conn: {u.ls_connected} (ticks: {u.total_ticks}, mid: {u.live_mid})")
