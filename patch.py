import re

with open('Simulatore_Avanzato.py', 'r', encoding='utf-8') as f:
    lines = f.read().split('\n')

for i, line in enumerate(lines):
    # 1. Percentuale Sottotrading
    if 'riga_totale = f"Totale Sottotrading [{tot_subtrading:+.0f} €] - Profit: {tot_profit} - Loss: {tot_loss}"' in line:
        lines[i] = '        tot_trades = tot_profit + tot_loss\n        perc_pos = (tot_profit / tot_trades * 100) if tot_trades > 0 else 0\n        riga_totale = f"Totale Sottotrading [{tot_subtrading:+.0f} €] - Profit: {tot_profit} - Loss: {tot_loss} [{perc_pos:.0f}%]"'
        
    # 2. Rimuovere blocco zombie (linea ~307)
    if 'elif tipo == "SAT1_SL_HIT":' in line:
        if 'Si torna a FASE 1' in lines[i+1]:
            for j in range(10):
                lines[i+j] = ''
                
    # 3. Aggiungere Ticket2 registra_stat
    if 'pnl, _ = self.chiudi_posizione(pid, lvl, "Loss OCO")' in line and 'TICKET2' in lines[i-1]:
        lines[i] = line + '\n                                self.registra_stat("Ticket2", pnl)'
        
    # 4. Aggiungere fase3_pnl += pnl_tot
    if 'pnl_tot = pnl_sat1 + pnl_sat2 + pnl_og + pnl_ol' in line:
        lines[i] = line + '\n                        self.fase3_pnl += pnl_tot'
        
    # 5. Fix .2f to dynamic dec
    if 'self.mult = float(mult)' in line:
        lines[i] = line + '\n        self.dec = 2 if molt_strum == 1.0 else (3 if molt_strum == 0.01 else 5)'

in_class = False
in_func = False
for i, line in enumerate(lines):
    if 'class SimulatoreMatematico' in line:
        in_class = True
    if 'def esegui_hedge_sincrono' in line:
        in_class = False
        in_func = True
        lines[i] = line + '\n    dec = 2 if molt_strum == 1.0 else (3 if molt_strum == 0.01 else 5)'
    
    if in_class and '.2f}' in line:
        lines[i] = line.replace('.2f}', '.{self.dec}f}')
    
    if in_func and '.2f}' in line:
        lines[i] = line.replace('.2f}', '.{dec}f}')

with open('Simulatore_Avanzato.py', 'w', encoding='utf-8') as f:
    f.write('\n'.join(lines))
