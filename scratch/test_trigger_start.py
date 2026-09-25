"""
Test di verifica logica Trigger Virtuale a Chiusura Candela (Trend)
Include test per il filtro distanza Kijun su H1 (5 < dist_kj < 25 pip).
"""
import unittest

def valuta_condizione_trigger(trig_dir, closed_close, trig_px, kj_val, tf="HOUR", mult=0.0001):
    if closed_close <= 0 or trig_px <= 0:
        return False
        
    dist_kj_pip = abs(closed_close - kj_val) / mult if (kj_val is not None and mult) else 0.0
    dist_h1_ok = True
    if tf == "HOUR" and kj_val is not None:
        if dist_kj_pip <= 5.0 or dist_kj_pip >= 25.0:
            dist_h1_ok = False

    if trig_dir == "SHORT":
        kj_ok = (kj_val is None or closed_close <= kj_val)
        return (closed_close <= trig_px and kj_ok and dist_h1_ok)
    elif trig_dir == "LONG":
        kj_ok = (kj_val is None or closed_close >= kj_val)
        return (closed_close >= trig_px and kj_ok and dist_h1_ok)
    return False

class TestTriggerTrend(unittest.TestCase):
    def test_short_trigger_attesa(self):
        # CADJPY SHORT: Kijun 108.20, Trigger 108.00, mult 0.01 (pip = 0.01)
        kj = 108.20
        trig = 108.00
        mult = 0.01
        
        # 1. Candela chiude a 108.05 (non ha rotto il trigger 108.00)
        self.assertFalse(valuta_condizione_trigger("SHORT", 108.05, trig, kj, mult=mult))
        
        # 2. Candela chiude a 108.00 esatto (dist = 20 pip da 108.20 -> ok 5-25 pip)
        self.assertTrue(valuta_condizione_trigger("SHORT", 108.00, trig, kj, mult=mult))
        
        # 3. Candela chiude a 108.05 ma con trigger a 108.10:
        # dist da KJ = (108.20 - 108.05) = 15 pip -> ok
        self.assertTrue(valuta_condizione_trigger("SHORT", 108.05, 108.10, kj, mult=mult))

    def test_filtro_distanza_h1_troppo_vicina(self):
        # Se la candela chiude sotto trigger ma ha distanza <= 5 pip da Kijun -> BLOCCO
        # Kijun 1.3200, Trigger 1.3198, Close 1.3197 (distanza = 3 pip <= 5 pip)
        kj = 1.3200
        trig = 1.3198
        close = 1.3197
        self.assertFalse(valuta_condizione_trigger("SHORT", close, trig, kj, tf="HOUR", mult=0.0001))
        
        # Se chiude a 1.3194 (distanza = 6 pip > 5 pip e < 25 pip) -> PASSA
        self.assertTrue(valuta_condizione_trigger("SHORT", 1.3194, trig, kj, tf="HOUR", mult=0.0001))

    def test_filtro_distanza_h1_troppo_lontana(self):
        # Se la candela chiude con distanza >= 25 pip da Kijun -> BLOCCO
        # Kijun 1.3200, Trigger 1.3180, Close 1.3170 (distanza = 30 pip >= 25 pip)
        kj = 1.3200
        trig = 1.3180
        close = 1.3170
        self.assertFalse(valuta_condizione_trigger("SHORT", close, trig, kj, tf="HOUR", mult=0.0001))
        
        # Se chiude a 1.3178 (distanza = 22 pip, compresa tra 5 e 25) -> PASSA
        self.assertTrue(valuta_condizione_trigger("SHORT", 1.3178, trig, kj, tf="HOUR", mult=0.0001))

    def test_filtro_h1_long(self):
        # LONG: Kijun 1.3200, Trigger 1.3210
        kj = 1.3200
        trig = 1.3210
        
        # Close 1.3204 (distanza 4 pip <= 5 pip) -> BLOCCO
        self.assertFalse(valuta_condizione_trigger("LONG", 1.3204, trig, kj, tf="HOUR", mult=0.0001))
        
        # Close 1.3212 (distanza 12 pip, compresa tra 5 e 25) -> PASSA
        self.assertTrue(valuta_condizione_trigger("LONG", 1.3212, trig, kj, tf="HOUR", mult=0.0001))
        
        # Close 1.3228 (distanza 28 pip >= 25 pip) -> BLOCCO
        self.assertFalse(valuta_condizione_trigger("LONG", 1.3228, trig, kj, tf="HOUR", mult=0.0001))

    def test_non_applicato_su_altri_timeframe(self):
        # Su H4 o D1 il filtro 5-25 pip H1 non si applica
        kj = 1.3200
        trig = 1.3210
        close = 1.3240 # dist = 40 pip
        self.assertTrue(valuta_condizione_trigger("LONG", close, trig, kj, tf="HOUR_4", mult=0.0001))

if __name__ == "__main__":
    unittest.main()
