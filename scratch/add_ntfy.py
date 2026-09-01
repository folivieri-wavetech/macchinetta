import re

with open('Motore_Trend.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Add invia_notifica function definition right after print_log
notifica_func = """
def invia_notifica(titolo, messaggio, tags="rotating_light"):
    topic = config.get("NTFY_TOPIC")
    if topic:
        try:
            orario = now_it().strftime("%H:%M:%S")
            messaggio_con_orario = f"[{orario}] {messaggio}"
            headers = {
                "Title": f"[{NOME_CONTO}] {titolo}".encode('utf-8'),
                "Tags": tags
            }
            requests.post(f"https://ntfy.sh/{topic}", data=messaggio_con_orario.encode('utf-8'), headers=headers, timeout=5)
        except Exception as e:
            print_log("SISTEMA", f"⚠️ Errore invio notifica Push: {e}")
"""

content = content.replace('def print_log(strumento, messaggio):', notifica_func + '\ndef print_log(strumento, messaggio):')

# 2. Add ntfy for Quota Esaurita
content = content.replace(
    'print_log(nome, "🛑 QUOTA IG ESAURITA! Arresto automatico del Trend per evitare chiamate a vuoto.")',
    'print_log(nome, "🛑 QUOTA IG ESAURITA! Arresto automatico del Trend per evitare chiamate a vuoto.")\n            invia_notifica(f"🛑 QUOTA IG ESAURITA: {nome}", f"[{nome}] Raggiunto limite dati storici IG. Arresto Trend in corso.", "no_entry")'
)

# 3. Add ntfy for Engine Start
content = content.replace(
    'print_log(nome, f"🚀 Motore Partito in {direzione}. Core piazzata a {pos.entry_price}.")',
    'print_log(nome, f"🚀 Motore Partito in {direzione}. Core piazzata a {pos.entry_price}.")\n                invia_notifica(f"🚀 AVVIO TREND: {nome}", f"[{nome}] Motore Partito in {direzione}. Core piazzata a {pos.entry_price}.", "rocket")'
)

# 4. Add ntfy for Increment
content = content.replace(
    'print_log(nome, msg)',
    'print_log(nome, msg)\n                    invia_notifica(f"➕ INCREMENTO TREND: {nome}", f"[{nome}] {msg}", "heavy_plus_sign")',
    1  # Only the first occurrence which is the increment
)

# 5. Add ntfy for Closure
content = content.replace(
    'msg = f"➖ Chiuso {tipo} ({sz}) PnL: {ev.get(\'pnl\', 0):.2f}"',
    'msg = f"➖ Chiuso {tipo} ({sz}) PnL: {ev.get(\'pnl\', 0):.2f}"\n                    invia_notifica(f"➖ CHIUSURA TREND: {nome}", f"[{nome}] {msg}", "heavy_minus_sign")'
)

# 6. Add ntfy for Reversal
content = content.replace(
    'print_log(nome, f"🛑 REVERSAL! Chiusura globale per incrocio KJ.")',
    'print_log(nome, f"🛑 REVERSAL! Chiusura globale per incrocio KJ.")\n                invia_notifica(f"🛑 REVERSAL TREND: {nome}", f"[{nome}] Incrocio KJ! Chiusura globale e stop motore (o inversione se attiva).", "warning")'
)

with open('Motore_Trend_ntfy.py', 'w', encoding='utf-8') as f:
    f.write(content)
print("Done")
