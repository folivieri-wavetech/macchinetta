# 🖥️ Guida: Setup Mini PC (Intel N100) per Trading & Bot H24 / 7-7 (Headless)

Questa guida riassume l'architettura e la procedura per far girare software di trading/bot (.exe Windows) 24/7 senza tenere il PC principale acceso e senza usare server cloud/datacenter.

---

## 🎯 Perché il Mini PC Intel N100?
1. **Consumi irrisori**: 6W - 12W (costo bolletta elettrica: ~1,50 € / 2,00 € al mese).
2. **IP Residenziale Domestico**: Nessun blocco IP da parte di bookmaker / exchange / broker che filtrano i datacenter cloud (AWS, OVH, Hetzner).
3. **Windows 11 Nativo**: Compatibilità totale con qualsiasi applicativo `.exe` con interfaccia grafica.
4. **Dimensioni tascabili**: 10x10 cm, posizionabile vicino al modem senza monitor né tastiera.

---

## 🛠️ Procedura di Setup

### 1. Configurazione Iniziale (Una Tantum - 5 minuti)
1. **Primo Avvio**: Collegare temporaneamente il Mini PC a un monitor o TV via HDMI, con mouse e tastiera USB.
2. **Primo setup Windows**: Completare la procedura guidata di Windows 11.
3. **Abilitazione Controllo Remoto**:
   - **Opzione A (AnyDesk / RustDesk)**: Installare il programma, abilitare *Accesso non presidiato* con password fissa e annotare l'ID numerico.
   - **Opzione B (Desktop Remoto RDP Windows Pro)**: *Impostazioni -> Sistema -> Desktop Remoto -> ON*.
4. **Disconnessione**: Spegnere, scollegare HDMI, mouse e tastiera. Posizionare il Mini PC vicino al modem/router con cavo di rete Ethernet e alimentazione.

---

### 2. Gestione e Installazione Software (.EXE) dal PC Principale
1. Aprire AnyDesk / Desktop Remoto dal proprio PC principale e connettersi all'ID/IP del Mini PC.
2. Trasferire il file `.exe` con un semplice **Copia & Incolla** o trascinandolo nella finestra remota.
3. Installare e avviare il software di trading.
4. Chiudere la finestra di controllo remoto: il Mini PC continua a lavorare H24 in background.

---

## ⚙️ Ottimizzazioni Consigliate per il Funzionamento H24

1. **Auto-Power ON (Ripristino dopo Blackout)**:
   - Entrare nel BIOS del Mini PC all'avvio (tasto `Canc` o `F7`/`F11`).
   - Abilitare la voce `Restore on AC Power Loss` o `State After G3` su **Power ON**.
2. **Avvio Automatico del Bot**:
   - Creare un collegamento del programma in `shell:startup` (Esecuzione automatica) o configurarlo nell'*Utilità di Pianificazione* (Task Scheduler) di Windows con trigger all'accesso utente.
3. **HDMI Dummy Plug (Opzionale)**:
   - Adattatore HDMI fittizio da 4-5 € per forzare Windows a mantenere attiva la risoluzione Full HD 1080p anche in assenza di un monitor fisico.
4. **Mini-UPS (Opzionale)**:
   - Piccolo gruppo di continuità da 25-30 € per proteggere modem e Mini PC da micro-interruzioni di corrente.
