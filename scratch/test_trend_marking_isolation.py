import os
import sys
import json
import tempfile
import unittest

# Assicuriamoci che la root del progetto sia nel path
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

# Simula argomento conto per permettere l'import sicuro dei moduli Motore e Motore_Trend
sys.argv = ["test_script", "DANY_DEMO"]
os.chdir(ROOT_DIR)

from trend_deals_manager import (
    carica_deal_trend,
    salva_deal_trend,
    registra_deal_trend,
    rimuovi_deal_trend,
    get_tutti_deal_trend_account,
    is_deal_trend
)
from Motore import filtra_posizioni_range
os.chdir(ROOT_DIR)
from Motore_Trend import filtra_posizioni_trend

class TestTrendMarkingIsolation(unittest.TestCase):
    def setUp(self):
        # Usiamo una cartella temporanea per simulare la cartella del conto
        self.test_dir = tempfile.mkdtemp()
        self.old_cwd = os.getcwd()
        os.chdir(self.test_dir)
        self.epic = "CS.D.USDJPY.TODAY.IP"

    def tearDown(self):
        os.chdir(self.old_cwd)

    def test_complete_isolation_between_range_and_trend(self):
        # 1. Nessun deal registrato inizialmente
        self.assertEqual(len(get_tutti_deal_trend_account()), 0)

        # 2. Registriamo un deal aperto da Trend
        trend_deal_id = "DEAL_TREND_001"
        registra_deal_trend(None, self.epic, trend_deal_id, label="Test USDJPY Trend Entry")

        self.assertTrue(is_deal_trend(None, trend_deal_id))
        self.assertFalse(is_deal_trend(None, "DEAL_RANGE_001"))

        # 3. Creiamo un mix di posizioni simulate su IG:
        # - Una posizione Trend (DEAL_TREND_001)
        # - Una posizione Range (DEAL_RANGE_001)
        # - Una posizione Range su un altro epic (DEAL_RANGE_EURUSD)
        posizioni_simulate_ig = [
            {
                "market": {"epic": self.epic},
                "position": {"dealId": trend_deal_id, "direction": "BUY", "size": 0.5, "level": 150.0}
            },
            {
                "market": {"epic": self.epic},
                "position": {"dealId": "DEAL_RANGE_001", "direction": "SELL", "size": 0.5, "level": 150.5}
            },
            {
                "market": {"epic": "CS.D.EURUSD.TODAY.IP"},
                "position": {"dealId": "DEAL_RANGE_EURUSD", "direction": "BUY", "size": 1.0, "level": 1.08}
            }
        ]

        # 4. Verifica filtro TREND: deve vedere SOLO ED ESCLUSIVAMENTE la posizione Trend sull'epic USDJPY
        pos_visibili_trend = filtra_posizioni_trend(posizioni_simulate_ig, self.epic)
        self.assertEqual(len(pos_visibili_trend), 1)
        self.assertEqual(pos_visibili_trend[0]["position"]["dealId"], trend_deal_id)

        # 5. Verifica filtro RANGE: deve vedere SOLO la posizione Range su USDJPY e NESSUNA di Trend!
        pos_visibili_range = filtra_posizioni_range(posizioni_simulate_ig, self.epic)
        self.assertEqual(len(pos_visibili_range), 1)
        self.assertEqual(pos_visibili_range[0]["position"]["dealId"], "DEAL_RANGE_001")

        # Range su EURUSD non deve essere toccato dal filtro USDJPY
        pos_range_eur = filtra_posizioni_range(posizioni_simulate_ig, "CS.D.EURUSD.TODAY.IP")
        self.assertEqual(len(pos_range_eur), 1)
        self.assertEqual(pos_range_eur[0]["position"]["dealId"], "DEAL_RANGE_EURUSD")

        # 6. Chiusura posizione Trend: rimozione chirurgica
        rimuovi_deal_trend(None, self.epic, trend_deal_id, label="Test USDJPY Trend Exit")
        self.assertFalse(is_deal_trend(None, trend_deal_id))

        # Simuliamo che su IG il deal chiuso non esista più nella lista posizioni aperte
        posizioni_ig_dopo_chiusura = [
            p for p in posizioni_simulate_ig if p["position"]["dealId"] != trend_deal_id
        ]

        # Ora se Trend filtra, non trova più posizioni Trend (è flat per Trend)
        pos_visibili_trend_dopo_chiusura = filtra_posizioni_trend(posizioni_ig_dopo_chiusura, self.epic)
        self.assertEqual(len(pos_visibili_trend_dopo_chiusura), 0)

        # Range continua a vedere la sua posizione Range intatta
        pos_visibili_range_dopo = filtra_posizioni_range(posizioni_ig_dopo_chiusura, self.epic)
        self.assertEqual(len(pos_visibili_range_dopo), 1)
        self.assertEqual(pos_visibili_range_dopo[0]["position"]["dealId"], "DEAL_RANGE_001")

    def test_sync_with_ig_removes_externally_closed_deals(self):
        from trend_deals_manager import sincronizza_deal_trend_con_ig

        # Registriamo due deal Trend su due epic diversi
        registra_deal_trend(None, "EPIC_1", "DEAL_1", label="Deal 1")
        registra_deal_trend(None, "EPIC_2", "DEAL_2", label="Deal 2")

        self.assertEqual(len(get_tutti_deal_trend_account()), 2)

        # Simuliamo che su IG sia rimasto aperto solo DEAL_2 (DEAL_1 è stato chiuso per SL o a mano)
        deal_ids_live = {"DEAL_2"}
        sincronizza_deal_trend_con_ig(None, deal_ids_live)

        tutti = get_tutti_deal_trend_account()
        self.assertEqual(len(tutti), 1)
        self.assertIn("DEAL_2", tutti)
        self.assertNotIn("DEAL_1", tutti)

if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
