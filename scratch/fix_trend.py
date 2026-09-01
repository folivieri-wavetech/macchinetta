import re

with open('Motore_Trend.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Replace the condition in esegui_motore_trend
old_cond = r"""        minuti_mancanti = min_tf - \(\(min_tot - offset\) % min_tf\)
        if minuti_mancanti == 0:
            minuti_mancanti = min_tf
            
        prossima = now \+ datetime\.timedelta\(minutes=minuti_mancanti\)
        prossima = prossima\.replace\(second=1, microsecond=0\)
        
        secondi_mancanti = \(prossima - now\)\.total_seconds\(\)
        
        # Consideriamo "sveglio" se mancano meno di 15 secondi alla chiusura \(o se abbiamo già un deal attivo che dobbiamo monitorare per incrementi\)
        if secondi_mancanti <= 15 or dati\.get\("stato"\) != "FLAT" or needs_start:
            has_active = True
            attivi\.append\(nome\)"""

new_cond = """        minuti_mancanti = min_tf - ((min_tot - offset) % min_tf)
        if minuti_mancanti == 0:
            minuti_mancanti = min_tf
            
        prossima = now + datetime.timedelta(minutes=minuti_mancanti)
        prossima = prossima.replace(second=1, microsecond=0)
        
        secondi_mancanti = (prossima - now).total_seconds()
        
        is_running = dati.get("stato") != "FLAT"
        is_candle_boundary = (min_tot - offset) % min_tf == 0
        
        # Ci svegliamo SOLO se:
        # 1. E' stato richiesto un avvio manuale (needs_start)
        # 2. Il motore sta girando, siamo nel minuto esatto di chiusura della candela, e siamo nei primi 30 secondi
        if needs_start or (is_running and is_candle_boundary and now.second < 30):
            has_active = True
            attivi.append(nome)"""

content = re.sub(old_cond, new_cond, content, count=1)

with open('Motore_Trend_fixed.py', 'w', encoding='utf-8') as f:
    f.write(content)
print("Done")
