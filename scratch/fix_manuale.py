import re

with open('Motore.py', 'r', encoding='utf-8') as f:
    content = f.read()

# We want to remove "stato": "MANUALE" and "modalita_manuale": True from error handlers.
# We will do a regex substitution that targets aggiorna_memoria blocks containing "attivo": False and "MANUALE" (but NOT the one with comando_manuale).
# Actually, since there are only ~12 occurrences, we can do it explicitly.

# First, fix the two infinite loop bugs that I had proposed to fix in my un-applied edit:
# 1. TICKET1
content = re.sub(
    r'(print_log\(nome, "?? \[TICKET1\] Impossibile aprire. Riprovo al prossimo giro."\)\s+continue)',
    r'print_log(nome, "🛑 [TICKET1] Impossibile aprire dopo 4 tentativi. Arresto forzato per evitare loop infiniti.")\n                                aggiorna_memoria(nome, {"attivo": False, "errore_avvio": True, "msg_manuale": "⚠️ Rifiuto persistente di IG all\'apertura del TICKET1."}, log_wip=f"⚠️ [ERRORE CRITICO]: Fallita immissione TICKET1. Macchina sospesa.")\n                                invia_notifica(f"🚨 ERRORE CRITICO: {nome}", f"[{nome}] Fallita l\'apertura del Ticket1 (dopo 4 tentativi). La strategia è stata sospesa per sicurezza.", "warning")\n                                continue',
    content
)

# 2. MICRO
content = re.sub(
    r'(succ = invia_ordine_pendente\(nome, epic, valuta, "SELL", s_ass, round\(p_base_orig \+ tp4, dec\), "LIMIT", p_base_orig, round\(p_base_orig \+ \(2 \* tp4\), dec\), h, dec, etichetta="\[ORDINE MICRO\]"\)\n\s+else:\n\s+succ = invia_ordine_pendente\(nome, epic, valuta, "BUY", s_ass, round\(p_base_orig - tp4, dec\), "LIMIT", p_base_orig, round\(p_base_orig - \(2 \* tp4\), dec\), h, dec, etichetta="\[ORDINE MICRO\]"\)\n\s+)(if not succ:\n\s+print_log\(nome, "?? Impossibile ripristinare Ordine MICRO. Riprovo al prossimo giro."\))',
    r'\1if not succ:\n                                        print_log(nome, "🛑 [ORDINE MICRO] Impossibile ripristinare. Arresto forzato per evitare loop infiniti.")\n                                        aggiorna_memoria(nome, {"attivo": False, "errore_ripristino": True, "msg_manuale": "⚠️ Rifiuto persistente di IG al ripristino dell\'Ordine MICRO. Sospeso."}, log_wip=f"⚠️ Emergenza: IG rifiuta ripristino MICRO.")\n                                        invia_notifica(f"🚨 ERRORE CRITICO: {nome}", f"[{nome}] Fallito ripristino Ordine Micro (dopo 4 tentativi). Sospeso.", "warning")\n                                        continue',
    content
)

# 3. Replace all instances of "stato": "MANUALE" and "modalita_manuale": True, EXCEPT the manual command one.
# To be safe, we just use regex to remove those keys from any aggiorna_memoria that isn't the manual command one.

lines = content.split('\n')
new_lines = []
in_manual_command = False

for i, line in enumerate(lines):
    if "comando_manuale" in line and "Tasto MANUALE premuto" in lines[i-1] if i>0 else False:
        in_manual_command = True
    
    if in_manual_command:
        if "continue" in line:
            in_manual_command = False
        new_lines.append(line)
    else:
        # Check if the line sets MANUALE for an error
        # Some are single line, some are multiline.
        
        # Single line replacements:
        if '"stato": "MANUALE"' in line and '"modalita_manuale": True' in line:
            # We are removing "stato": "MANUALE", "modalita_manuale": True, from the dictionary
            line = re.sub(r'"stato": "MANUALE",\s*', '', line)
            line = re.sub(r'"modalita_manuale": True,\s*', '', line)
            
            # also replace "Passaggio a MANUALE" in log_wip / msg_manuale with "Sospensione Motore"
            line = line.replace("Passaggio a MANUALE", "Sospensione Motore")
            line = line.replace("Macchina in MANUALE", "Macchina Sospesa")
            line = line.replace("Passaggio in Manuale", "Sospensione Motore")
        
        # Multiline replacements:
        if '"stato": "MANUALE",' in line and not in_manual_command:
            continue
        if '"modalita_manuale": True,' in line and not in_manual_command:
            continue
            
        new_lines.append(line)

final_content = "\n".join(new_lines)
final_content = final_content.replace("Passaggio a MANUALE.", "Motore Sospeso.")
final_content = final_content.replace("Passaggio a MANUALE", "Motore Sospeso")

with open('Motore_fixed.py', 'w', encoding='utf-8') as f:
    f.write(final_content)

print("Done. Saved to Motore_fixed.py")
