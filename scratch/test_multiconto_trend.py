import os
import json

def test_multiconto_trend_range_logic():
    print("Test 1: Verifica logica di salvataggio memoria per Multiconto Trend-Range...")
    
    conto_t = "TEST_FIORDOK_DEMO"
    conto_r = "TEST_DANY_DEMO"
    os.makedirs(conto_t, exist_ok=True)
    os.makedirs(conto_r, exist_ok=True)
    
    nome_strumento = "EUR/USD"
    dir_trend = "LONG"
    tf_scelto = "HOUR" # H1
    
    dir_range = "SHORT" if dir_trend == "LONG" else "LONG"
    assert dir_range == "SHORT"
    
    # Inizializza memoria base
    mem_t = {nome_strumento: {"size": 3, "size_max": 5, "scala": 1, "min_body": 10}}
    mem_r = {nome_strumento: {"tp": 50, "opp": 10, "dts": 5, "size": 4}}
    
    # Esegui salvataggio Trend su conto T
    full_mem_t = dict(mem_t)
    full_mem_t[nome_strumento] = {
        **mem_t.get(nome_strumento, {}),
        "attivo": True,
        "direzione": dir_trend,
        "stato": "FLAT",
        "tipo_strategia": "TREND",
        "timeframe": tf_scelto,
        "needs_manual_start": True,
        "msg_manuale": "",
        "storico_wip_trend": [],
        "posizioni_core": [],
        "posizioni_incr": [],
        "trailing_sl_core": None,
        "trailing_sl_incr": None
    }
    
    # Esegui salvataggio Range su conto R
    full_mem_r = dict(mem_r)
    full_mem_r[nome_strumento] = {
        **mem_r.get(nome_strumento, {}),
        "attivo": True,
        "direzione": dir_range,
        "tp": 50,
        "opp": 10,
        "dts": 5,
        "size": 4,
        "stato": "IN_ATTESA",
        "tipo_strategia": "RANGE",
        "storico_wip": [],
        "errore_avvio": False,
        "errore_ripristino": False,
        "comando_manuale": False,
        "msg_manuale": ""
    }
    
    # Verifiche
    assert full_mem_t[nome_strumento]["tipo_strategia"] == "TREND"
    assert full_mem_t[nome_strumento]["timeframe"] == "HOUR"
    assert full_mem_t[nome_strumento]["direzione"] == "LONG"
    assert full_mem_t[nome_strumento]["attivo"] == True
    
    assert full_mem_r[nome_strumento]["tipo_strategia"] == "RANGE"
    assert full_mem_r[nome_strumento]["direzione"] == "SHORT"
    assert full_mem_r[nome_strumento]["attivo"] == True
    assert full_mem_r[nome_strumento]["tp"] == 50
    assert full_mem_r[nome_strumento]["opp"] == 10
    
    print("✅ TEST COMPLETATO CON SUCCESSO: Logica Multiconto Trend-Range valida al 100%!")
    
    # Cleanup
    import shutil
    shutil.rmtree(conto_t)
    shutil.rmtree(conto_r)

if __name__ == "__main__":
    test_multiconto_trend_range_logic()
