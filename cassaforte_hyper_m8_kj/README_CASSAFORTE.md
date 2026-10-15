# CASSAFORTE HYPER M8 KJ (Kijun-sen 55 su Timeframe 8 Minuti)

Questo archivio contiene la versione del motore **Hyper su Timeframe a 8 Minuti (M8) con Kijun-sen 55 periodi**.

## Differenze rispetto alla versione M5 originale:
1. **Timeframe Candele:** 8 Minuti (`CANDLE_SECONDS = 480`).
2. **Kijun-sen 55:** Calcolata su 55 barre da 8 minuti (55 * 8m = 440 minuti, circa 7.33 ore).
3. **Notifiche Push NTFY:** Disattivate al 100% (nessun invio su ntfy.sh né da engine né da order manager per il TF 8M).
4. **File di Stato Indipendenti:** `hyper_gold_m8_state.json` e `hyper_us500_m8_state.json` (per preservare intatti gli stati M5).

## Parametri Strategia (identici al 5 minuti originale):
- **Core:** 6 contratti
- **Incrementi Bancomat:** 4 contratti (Spot Gold) / 3 contratti (US 500) con Take Profit a +5 pip
- **Incrementi Runner:** Take Profit esteso a +12 pip con Break-Even protetto a +1 pip dopo +6 pip
- **Paracadute KJ Intracandela:** Stop emergenza a KJ +/- 6 pip
- **Candela Segnale KJ:** Stop a rottura confermata +/- 3 pip
- **Sospensione Notturna e Weekend:** Orari e salvaguardie identici alla versione certificata.

## File archiviati in questa cartella:
- `hyper_gold_m8_engine.py`: Motore Hyper M8 per Spot Gold
- `hyper_us500_m8_engine.py`: Motore Hyper M8 per US 500 Cash
- `hyper_order_manager.py`: Gestore ordini Hyper con soppressione notifiche NTFY
- `hyper_tab.py`: Tab Streamlit per Dashboard aggiornato con supporto M8
