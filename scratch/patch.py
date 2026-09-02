import sys

with open(r'C:\Users\Fiordok\Desktop\Macchinetta_IG\Dashboard.py', 'r', encoding='utf-8') as f:
    text = f.read()

old_block = """                          elif stato == "FASE_3 + Ultima":
                              f3_dir, f3_base = dati.get("fase3_dir"), dati.get("fase3_current_base")
                              if f3_dir and f3_base is not None:
                                  spia = " 🟢" if (prezzo < f3_base + (dati.get("tp", 50)/4)*mult if f3_dir == "BUY" else prezzo > f3_base - (dati.get("tp", 50)/4)*mult) else " 🔴\""""

new_block = old_block + """
                          elif stato == "FASE_2_SATELLITI":
                              pos_live = st.session_state.get("live_pos_data", [])
                              c = CONFIG_STRUMENTI.get(nome, {})
                              if c and c.get("epic"):
                                  s_core = float(dati.get("size", 4))
                                  s_mezzo = max(1.0, s_core / 2)
                                  t_epic = c.get("epic")
                                  for p in pos_live:
                                      if p['market']['epic'] == t_epic and float(p['position']['size']) == s_mezzo:
                                          p_dir = p['position']['direction']
                                          p_level = float(p['position']['level'])
                                          spia = " 🟢" if (prezzo > p_level if p_dir == "BUY" else prezzo < p_level) else " 🔴"
                                          break"""

if old_block in text:
    text = text.replace(old_block, new_block)
    with open(r'C:\Users\Fiordok\Desktop\Macchinetta_IG\Dashboard.py', 'w', encoding='utf-8') as f:
        f.write(text)
    print("SUCCESS")
else:
    print("OLD BLOCK NOT FOUND")
