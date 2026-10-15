import os
import re

src_dir = r"c:\Users\Fiordok\Desktop\Macchinetta_IG\cassaforte_hyper_m5_kj"
dst_dir = r"c:\Users\Fiordok\Desktop\Macchinetta_IG\cassaforte_hyper_m8_kj"
os.makedirs(dst_dir, exist_ok=True)

# 1. hyper_order_manager.py
with open(os.path.join(src_dir, "hyper_order_manager.py"), "r", encoding="utf-8") as f:
    content_om = f.read()

# Nel manager, disabilitiamo completamente le notifiche NTFY su 8M
content_om = content_om.replace(
    '    def send_notification(self, titolo: str, messaggio: str, tags: str = "rotating_light"):\n        """Invia notifica push su ntfy.sh usando il topic configurato per questo conto."""\n        topic = self._get_ntfy_topic()',
    '    def send_notification(self, titolo: str, messaggio: str, tags: str = "rotating_light"):\n        """Invia notifica push su ntfy.sh usando il topic configurato per questo conto."""\n        # NOTIFICHE NTFY TOTALMENTE DISABILITATE SU TF 8 MINUTI\n        return\n        topic = self._get_ntfy_topic()'
)

with open(os.path.join(dst_dir, "hyper_order_manager.py"), "w", encoding="utf-8") as f:
    f.write(content_om)
print("hyper_order_manager.py creato")

# Funzione per rimuovere pulitamente le chiamate order_mgr.send_notification(...)
def remove_send_notifications(text):
    lines = text.splitlines(keepends=True)
    out = []
    in_notification = False
    indent = ""
    for line in lines:
        if "order_mgr.send_notification(" in line:
            indent = line[:len(line) - len(line.lstrip())]
            if line.rstrip().endswith(")"):
                out.append(f"{indent}pass  # NTFY disattivato su TF 8 minuti\n")
            else:
                in_notification = True
                out.append(f"{indent}pass  # NTFY disattivato su TF 8 minuti\n")
            continue
        if in_notification:
            # Check if this line closes the parenthesis
            # Notice the arguments can span multiple lines ending with ')'
            if line.strip().endswith(")") or line.strip() == ")":
                in_notification = False
            continue
        out.append(line)
    return "".join(out)

# 2. hyper_gold_m8_engine.py
with open(os.path.join(src_dir, "hyper_gold_m5_engine.py"), "r", encoding="utf-8") as f:
    content_gold = f.read()

content_gold = remove_send_notifications(content_gold)
content_gold = content_gold.replace("CANDLE_SECONDS = 300    # 5 Minuti (M5) per barra", "CANDLE_SECONDS = 480    # 8 Minuti (M8) per barra")
content_gold = content_gold.replace('STATE_FILE = "hyper_gold_m5_state.json"', 'STATE_FILE = "hyper_gold_m8_state.json"')
content_gold = content_gold.replace("HyperGoldM5Engine", "HyperGoldM8Engine")
content_gold = content_gold.replace("aggregate_candles_to_5m", "aggregate_candles_to_8m")
content_gold = content_gold.replace('aggregate_candles_to_10m = aggregate_candles_to_5m', 'aggregate_candles_to_10m = aggregate_candles_to_8m')
content_gold = content_gold.replace('tf="5M"', 'tf="8M"')
content_gold = content_gold.replace('"tf": "5M"', '"tf": "8M"')
content_gold = content_gold.replace("Core 5M", "Core 8M")
content_gold = content_gold.replace("5M", "8M")
content_gold = content_gold.replace("5 Minuti", "8 Minuti")
content_gold = content_gold.replace("5 minuti", "8 minuti")

with open(os.path.join(dst_dir, "hyper_gold_m8_engine.py"), "w", encoding="utf-8") as f:
    f.write(content_gold)
print("hyper_gold_m8_engine.py creato")

# 3. hyper_us500_m8_engine.py
with open(os.path.join(src_dir, "hyper_us500_m5_engine.py"), "r", encoding="utf-8") as f:
    content_us = f.read()

content_us = remove_send_notifications(content_us)
content_us = content_us.replace("CANDLE_SECONDS = 300    # 5 Minuti (M5) per barra", "CANDLE_SECONDS = 480    # 8 Minuti (M8) per barra")
content_us = content_us.replace('STATE_FILE = "hyper_us500_m5_state.json"', 'STATE_FILE = "hyper_us500_m8_state.json"')
content_us = content_us.replace("HyperUS500M5Engine", "HyperUS500M8Engine")
content_us = content_us.replace("aggregate_candles_to_5m", "aggregate_candles_to_8m")
content_us = content_us.replace('aggregate_candles_to_10m = aggregate_candles_to_5m', 'aggregate_candles_to_10m = aggregate_candles_to_8m')
content_us = content_us.replace('tf="5M"', 'tf="8M"')
content_us = content_us.replace('"tf": "5M"', '"tf": "8M"')
content_us = content_us.replace("Core 5M", "Core 8M")
content_us = content_us.replace("5M", "8M")
content_us = content_us.replace("5 Minuti", "8 Minuti")
content_us = content_us.replace("5 minuti", "8 minuti")

with open(os.path.join(dst_dir, "hyper_us500_m8_engine.py"), "w", encoding="utf-8") as f:
    f.write(content_us)
print("hyper_us500_m8_engine.py creato")

# 4. hyper_tab.py
with open(os.path.join(src_dir, "hyper_tab.py"), "r", encoding="utf-8") as f:
    content_tab = f.read()

content_tab = content_tab.replace('("10M", "5M")', '("10M", "5M", "8M")')
content_tab = content_tab.replace('HyperGoldM5Engine', 'HyperGoldM8Engine')
content_tab = content_tab.replace('hyper_gold_m5_engine', 'hyper_gold_m8_engine')
content_tab = content_tab.replace('HyperUS500M5Engine', 'HyperUS500M8Engine')
content_tab = content_tab.replace('hyper_us500_m5_engine', 'hyper_us500_m8_engine')
content_tab = content_tab.replace('hyper_gold_m5_state.json', 'hyper_gold_m8_state.json')
content_tab = content_tab.replace('hyper_us500_m5_state.json', 'hyper_us500_m8_state.json')
content_tab = content_tab.replace('5M', '8M')

with open(os.path.join(dst_dir, "hyper_tab.py"), "w", encoding="utf-8") as f:
    f.write(content_tab)
print("hyper_tab.py creato")
