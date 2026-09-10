import sys
import os
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True)
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', line_buffering=True)

# Add paths
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

sys.argv = ["Motore_Trend.py", "DANY_DEMO"]
from macchinetta_trend.core_engine import CoreEngine, Candle
from Motore_Trend import CONFIG_STRUMENTI, pips_to_price, format_price_ig

def run_comprehensive_pip_audit():
    print("================================================================================")
    print("🔍 AUDIT CHIRURGICO: VERIFICA CALCOLO DEI PIP SU TUTTI I 10 STRUMENTI E SU TUTTI I TF")
    print("================================================================================\n")

    # Verifica definizioni e moltiplicatori
    errori = 0
    tabelle = []

    for nome, cfg in CONFIG_STRUMENTI.items():
        mult = cfg["moltiplicatore"]
        dec = cfg["decimali"]
        
        # 1 pip reale in delta prezzo
        p1 = pips_to_price(nome, 1)
        # 5 pip reali in delta prezzo
        p5 = pips_to_price(nome, 5)
        # 20 pip reali in delta prezzo
        p20 = pips_to_price(nome, 20)

        # Controlli di sicurezza specifici per classe di strumento
        if "JPY" in nome:
            # Forex JPY (es. 207.869) -> 1 pip = 0.010, 5 pip = 0.050, 20 pip = 0.200
            assert mult == 0.01, f"{nome}: mult deve essere 0.01, trovato {mult}"
            assert dec == 3, f"{nome}: dec deve essere 3, trovato {dec}"
            assert abs(p1 - 0.01) < 1e-9, f"{nome}: 1 pip errato: {p1}"
            assert abs(p5 - 0.05) < 1e-9, f"{nome}: 5 pip errato: {p5}"
            assert abs(p20 - 0.20) < 1e-9, f"{nome}: 20 pip errato: {p20}"
        elif "Gold" in nome or "US 500" in nome:
            # Gold / Indici -> 1 punto/pip = 1.0, 5 punti = 5.0, 20 punti = 20.0
            assert mult == 1.0, f"{nome}: mult deve essere 1.0, trovato {mult}"
            assert dec == 2, f"{nome}: dec deve essere 2, trovato {dec}"
            assert abs(p1 - 1.0) < 1e-9, f"{nome}: 1 pip errato: {p1}"
            assert abs(p5 - 5.0) < 1e-9, f"{nome}: 5 pip errato: {p5}"
            assert abs(p20 - 20.0) < 1e-9, f"{nome}: 20 pip errato: {p20}"
        else:
            # Forex Standard a 5 decimali -> 1 pip = 0.00010, 5 pip = 0.00050, 20 pip = 0.00200
            assert mult == 0.0001, f"{nome}: mult deve essere 0.0001, trovato {mult}"
            assert dec == 5, f"{nome}: dec deve essere 5, trovato {dec}"
            assert abs(p1 - 0.0001) < 1e-9, f"{nome}: 1 pip errato: {p1}"
            assert abs(p5 - 0.0005) < 1e-9, f"{nome}: 5 pip errato: {p5}"
            assert abs(p20 - 0.0020) < 1e-9, f"{nome}: 20 pip errato: {p20}"

        tabelle.append({
            "nome": nome,
            "dec": dec,
            "mult": mult,
            "p1": f"{p1:.{dec}f}",
            "p5": f"{p5:.{dec}f}",
            "p20": f"{p20:.{dec}f}",
        })

    print(f"{'STRUMENTO':<14} | {'DEC':<3} | {'MOLTIPLICATORE':<14} | {'1 PIP':<10} | {'5 PIP':<10} | {'20 PIP (PARACADUTE)':<20}")
    print("-" * 85)
    for r in tabelle:
        print(f"{r['nome']:<14} | {r['dec']:<3} | {r['mult']:<14} | {r['p1']:<10} | {r['p5']:<10} | {r['p20']:<20}")
    print("-" * 85)
    print("✅ Tutte le definizioni di 1 pip, 5 pip e 20 pip sono MATEMATICAMENTE ESATTE per ogni strumento!\n")

    # =========================================================================
    # TEST COMPORTAMENTALE DELL'ENGINE SU CIASCUN STRUMENTO E TIMEFRAME
    # =========================================================================
    print("🧪 TEST SIMULATO DEL COMPORTAMENTO LIVE SU TUTTI I TIME FRAME:")
    
    test_cases = [
        ("EUR/USD", 1.08500, "H1", "HOUR", 30),
        ("EUR/USD", 1.08500, "H4", "HOUR_4", 40),
        ("EUR/USD", 1.08500, "D1", "DAY", 50),
        ("GBP/JPY", 207.800, "H1", "HOUR", 30),
        ("GBP/JPY", 207.800, "H4", "HOUR_4", 40),
        ("USD/JPY", 145.500, "H1", "HOUR", 30),
        ("Spot Gold", 2500.00, "H1", "HOUR", 30),
        ("US 500 Cash", 5500.00, "H1", "HOUR", 30),
        ("US 500 Cash", 5500.00, "H4", "HOUR_4", 40),
    ]

    for nome, base_px, tf_code, tf_val, exp_tp_pips in test_cases:
        cfg_i = CONFIG_STRUMENTI[nome]
        mult = cfg_i["moltiplicatore"]
        dec = cfg_i["decimali"]
        
        engine_cfg = {
            "size_i": 1,
            "size_max": 5,
            "scala": 1,
            "timeframe": tf_val,
            "tk_periods": 21,
            "kj_periods": 55,
            "min_body": 5,
            "pip_value": mult,
            "max_kj_distance": 30.0,
            "auto_restart": False
        }
        engine = CoreEngine(engine_cfg)
        engine.start(base_px, "LONG")
        
        # Imposta TK e KJ
        engine.current_tk = base_px
        engine.current_kj = base_px
        
        # 1. Test Paracadute 20 pip:
        # Prezzo a KJ - 19.9 pip NON deve scattare
        safe_price = base_px - (19.9 * mult)
        ev_safe = engine.check_live_stops(safe_price)
        assert not any(e.get("type") == "reversal" for e in ev_safe), f"{nome} {tf_code}: Paracadute scattato a 19.9 pip invece che a 20!"

        # Prezzo a KJ - 20.0 pip DEVE scattare
        trigger_price = base_px - (20.0 * mult)
        ev_trig = engine.check_live_stops(trigger_price)
        assert any(e.get("type") == "reversal" and "live_stop_kj" in e.get("reason", "") for e in ev_trig), f"{nome} {tf_code}: Paracadute non scattato a esatti 20 pip!"
        
        # Reset engine per il test Candela Segnale
        engine.reset()
        engine.start(base_px, "LONG")
        engine.current_tk = base_px
        engine.current_kj = base_px
        
        # 2. Test Candela Segnale: candela chiude sotto KJ di 3 pip (senza toccare 20 pip di paracadute)
        # Minimo della candela = base_px - 4 pip
        c_low = base_px - (4.0 * mult)
        c_close = base_px - (3.0 * mult)
        c_seg = Candle(base_px, base_px + (1.0 * mult), c_low, c_close)
        
        ev_close = engine.on_candle_close(c_seg, c_close)
        # NON deve chiudere la Core
        assert engine.is_running == True, f"{nome}: Core chiusa erroneamente alla chiusura della candela!"
        assert engine.signal_candle_active == True, f"{nome}: Candela segnale non attivata!"
        
        # Il livello di stop atteso DEVE essere c_low - 5 pip
        exp_stop = c_low - (5.0 * mult)
        assert abs(engine.signal_stop_price - exp_stop) < 1e-9, f"{nome}: Livello stop Candela Segnale errato: atteso {exp_stop}, ottenuto {engine.signal_stop_price}"
        
        # Prezzo live tocca c_low - 4.9 pip -> NON scatta
        ev_live_safe = engine.check_live_stops(c_low - (4.9 * mult))
        assert not any(e.get("type") == "reversal" for e in ev_live_safe), f"{nome}: Stop Candela Segnale scattato prima di 5 pip!"

        # Prezzo live tocca c_low - 5.0 pip -> DEVE SCATTARE
        ev_live_trig = engine.check_live_stops(c_low - (5.0 * mult))
        assert any(e.get("type") == "reversal" and "break_min" in e.get("reason", "") for e in ev_live_trig), f"{nome}: Stop Candela Segnale non scattato a esatti 5 pip sotto minimo!"
        
        # 3. Test TP Incrementi: verifica che il target in pip corrisponda al TF
        engine.reset()
        engine.start(base_px, "LONG")
        engine.current_tk = base_px
        engine.current_kj = base_px
        # Apri un incremento
        engine.pm.open_increment(base_px, 1, "LONG")
        
        # Prezzo sale a TP - 0.1 pip -> non chiude
        tp_delta_safe = (exp_tp_pips - 0.1) * mult
        ev_tp_safe = engine.check_live_stops(base_px + tp_delta_safe)
        assert not any(e.get("type") == "tp_increment" for e in ev_tp_safe), f"{nome} {tf_code}: TP scattato prima del target!"
        
        # Prezzo sale a TP -> DEVE CHIUDERE
        tp_delta_trig = exp_tp_pips * mult
        ev_tp_trig = engine.check_live_stops(base_px + tp_delta_trig)
        assert any(e.get("type") == "tp_increment" for e in ev_tp_trig), f"{nome} {tf_code}: TP non scattato al target di {exp_tp_pips} pip!"

        print(f"  [OK] {nome:<12} su TF {tf_code:<3} -> Paracadute=20p, CandelaSegnale=5p, TP_Incr={exp_tp_pips}p VERIFICATI AL CENTESIMO DI PIP")

    print("\n================================================================================")
    print("🎯 CONCLUSIONE AUDIT: 100% DEI TEST SUPERATI CON SUCCESSO SENZA ERRORI!")
    print("================================================================================")

if __name__ == "__main__":
    run_comprehensive_pip_audit()
