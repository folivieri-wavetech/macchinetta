import os

code = """
    # --- TAB OTTIMIZZAZIONE GLOBALE ---
    with tab_ottimizzazione:
        st.markdown("<h2 style='text-align: center; color: #FF4500;'>🧪 Ottimizzatore Multi-Condizione (Monte Carlo)</h2>", unsafe_allow_html=True)
        st.markdown("Genera automaticamente decine di configurazioni di mercato casuali e laterali, testando centinaia di combinazioni (TP/DTS) e stilando una Classifica Globale in base al rapporto Profitto/Rischio (RoMD).", unsafe_allow_html=True)
        
        st.markdown("---")
        
        ott_modo_dati = st.radio("Seleziona la base dati per l'ottimizzazione:", ["Generazione Batch (LATERALE + RANDOM)", "File Singolo Esistente"], key="ott_modo")
        
        profilo = st.selectbox("Seleziona Strumento/Profilo", ["Indici / Oro (Tick 1.0)", "Forex (Major - Es. EURUSD)", "Forex (JPY - Es. USDJPY)"], key="ott_profilo")
        
        if profilo == "Indici / Oro (Tick 1.0)":
            def_part, def_tick, def_tp_min, def_tp_max, def_tp_step, def_dts_min, def_dts_max, def_dts_step, fmt = 2400.0, 1.0, 40.0, 200.0, 10.0, 10.0, 30.0, 5.0, "%.1f"
            def_mult = 1.0
        elif "Major" in profilo:
            def_part, def_tick, def_tp_min, def_tp_max, def_tp_step, def_dts_min, def_dts_max, def_dts_step, fmt = 1.3500, 0.0005, 0.0040, 0.0200, 0.0010, 0.0010, 0.0030, 0.0005, "%.4f"
            def_mult = 10000.0
        else:
            def_part, def_tick, def_tp_min, def_tp_max, def_tp_step, def_dts_min, def_dts_max, def_dts_step, fmt = 160.00, 0.005, 0.40, 2.00, 0.10, 0.10, 0.30, 0.05, "%.3f"
            def_mult = 100.0
            
        from Simulatore_Avanzato import genera_base_dati, esegui_ottimizzazione_griglia
        import pandas as pd
        
        file_paths_ott = []
        
        st.markdown("### 1. Dati di Partenza")
        if ott_modo_dati == "File Singolo Esistente":
            cartella_sim = os.path.join(os.getcwd(), "Simulatore")
            selezionato = st.selectbox("Seleziona Strumento (Esistente)", [d for d in os.listdir(cartella_sim) if os.path.isdir(os.path.join(cartella_sim, d))] if os.path.exists(cartella_sim) else [], key="ott_strum")
            if selezionato:
                dir_path_ott = os.path.join(cartella_sim, selezionato)
                files_csv = [f for f in os.listdir(dir_path_ott) if f.endswith(".csv")]
                if files_csv:
                    file_sel = st.selectbox("Seleziona Dataset", files_csv, key="ott_file")
                    file_paths_ott.append(os.path.join(dir_path_ott, file_sel))
                else:
                    st.warning("Nessun dataset presente.")
        else:
            st.info("Questa modalità genererà al volo 5 file LATERALE e 5 file RANDOM per testare la robustezza dei parametri ed evitare overfitting sulla media.")
            c_g1, c_g2, c_g3 = st.columns(3)
            with c_g1: ott_partenza = st.number_input("Prezzo di Partenza", value=def_part, step=def_tick*10, format=fmt, key=f"ott_part_{profilo}")
            with c_g2: ott_tick_size = st.number_input("Tick Size", value=def_tick, step=def_tick, format=fmt, key=f"ott_tick_{profilo}")
            ott_tic_tot = st.number_input("Numero di Tick per file", value=10000, step=1000, key=f"ott_tic_tot_{profilo}")
            
        st.markdown("### 2. Configura la Griglia dei Parametri")
        c1, c2, c3 = st.columns(3)
        with c1:
            st.markdown("#### TP (Take Profit)")
            tp_min = st.number_input("TP Minimo", value=def_tp_min, step=def_tp_step, format=fmt, key=f"ott_tp_min_{profilo}")
            tp_max = st.number_input("TP Massimo", value=def_tp_max, step=def_tp_step, format=fmt, key=f"ott_tp_max_{profilo}")
            tp_step = st.number_input("TP Step", value=def_tp_step, step=def_tp_step, format=fmt, key=f"ott_tp_step_{profilo}")
        with c2:
            st.markdown("#### DTS (Distanza Sicurezza)")
            dts_min = st.number_input("DTS Minimo", value=def_dts_min, step=def_dts_step, format=fmt, key=f"ott_dts_min_{profilo}")
            dts_max = st.number_input("DTS Massimo", value=def_dts_max, step=def_dts_step, format=fmt, key=f"ott_dts_max_{profilo}")
            dts_step = st.number_input("DTS Step", value=def_dts_step, step=def_dts_step, format=fmt, key=f"ott_dts_step_{profilo}")
        with c3:
            st.markdown("#### Variabili Fisse")
            ott_size = st.number_input("Size Iniziale", value=10.0, step=1.0, key=f"ott_size_{profilo}")
            ott_val_punto = st.number_input("Valore Punto (EUR)", value=1.0, step=0.5, key=f"ott_val_{profilo}")
            
        st.markdown("#### Automazione")
        ott_target_sim = st.number_input("Target Simulazioni (File totali)", min_value=10, max_value=10000, value=50, step=10, key=f"ott_target_sim_{profilo}")
        
        if st.button("🚀 Avvia Ottimizzazione Globale", type="primary", use_container_width=True):
            import numpy as np
            tp_list = np.arange(tp_min, tp_max + tp_step, tp_step).tolist()
            dts_list = np.arange(dts_min, dts_max + dts_step, dts_step).tolist()
            tp_range = {"min": tp_min, "max": tp_max, "step": tp_step}
            dts_range = {"min": dts_min, "max": dts_max, "step": dts_step}
            storico_file = "ottimizzazione_storico_globale.csv"
            
            if ott_modo_dati == "Generazione Batch (LATERALE + RANDOM)":
                iterazioni = max(1, int(ott_target_sim / 10))
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                import time
                for it in range(iterazioni):
                    status_text.markdown(f"**Elaborazione in corso... Batch {it+1}/{iterazioni} ({(it+1)*10} file totali)**")
                    
                    file_paths_ott = []
                    for i in range(5):
                        p = genera_base_dati(f"BATCH_OTT_{int(time.time()*1000)}_{i}", "LATERALE", ott_partenza, ott_tick_size, ott_tic_tot, ott_size)
                        file_paths_ott.append(p)
                    for i in range(5):
                        p = genera_base_dati(f"BATCH_OTT_{int(time.time()*1000)}_{i}", "RANDOM", ott_partenza, ott_tick_size, ott_tic_tot, ott_size)
                        file_paths_ott.append(p)
                        
                    df_res = esegui_ottimizzazione_griglia(file_paths_ott, tp_range, dts_range, size=ott_size, mult=def_mult, valore_punto=ott_val_punto)
                    
                    if not df_res.empty:
                        if os.path.exists(storico_file):
                            df_storico = pd.read_csv(storico_file)
                            df_full = pd.concat([df_storico, df_res], ignore_index=True)
                        else:
                            df_full = df_res.copy()
                        df_full.to_csv(storico_file, index=False)
                        
                    for p in file_paths_ott:
                        if os.path.exists(p):
                            os.remove(p)
                            
                    progress_bar.progress((it + 1) / iterazioni)
                status_text.success(f"✅ Ottimizzazione Monte Carlo completata! ({iterazioni*10} file elaborati)")
                
            else:
                if not file_paths_ott:
                    st.error("Nessun dataset selezionato.")
                else:
                    with st.spinner("Ottimizzazione file singolo in corso..."):
                        df_res = esegui_ottimizzazione_griglia(file_paths_ott, tp_range, dts_range, size=ott_size, mult=def_mult, valore_punto=ott_val_punto)
                        if not df_res.empty:
                            if os.path.exists(storico_file):
                                df_storico = pd.read_csv(storico_file)
                                df_full = pd.concat([df_storico, df_res], ignore_index=True)
                            else:
                                df_full = df_res.copy()
                            df_full.to_csv(storico_file, index=False)
                            st.success("✅ Ottimizzazione file singolo completata!")
                            
            if os.path.exists(storico_file):
                df_full = pd.read_csv(storico_file)
                
                # Raggruppamento Globale e Medie
                df_global = df_full.groupby(["TP", "OPP", "DTS"]).mean().reset_index()
                n_files = 10 if ott_modo_dati == "Generazione Batch (LATERALE + RANDOM)" else 1
                df_global["N_Simulazioni"] = df_full.groupby(["TP", "OPP", "DTS"]).size().reset_index(drop=True) * n_files
                
                # Calcolo Score RoMD e Win
                df_global["Score RoMD"] = df_global["PNL Totale"] / df_global["Max Drawdown"].replace(0, 1)
                df_global["Score Win"] = df_global["PNL Totale"] * (df_global["Win Rate %"] / 100.0)
                
                # Ordinamento per Score RoMD
                df_global = df_global.sort_values(by="Score RoMD", ascending=False).reset_index(drop=True)
                
                # Formattazione per visualizzazione
                col_display = ["TP", "OPP", "DTS", "PNL Long", "PNL Short", "PNL Totale", "Max Drawdown", "Win Rate %", "Score RoMD", "Score Win", "N_Simulazioni"]
                df_display = df_global[col_display].copy()
                
                st.markdown("### 🏆 Classifica Globale Parametri Migliori (Ordinata per Score RoMD)")
                st.dataframe(df_display.style.background_gradient(subset=["Score RoMD", "PNL Totale"], cmap="RdYlGn").format({
                    "PNL Long": "{:.2f} €", "PNL Short": "{:.2f} €", "PNL Totale": "{:.2f} €", 
                    "Max Drawdown": "{:.2f} €", "Score RoMD": "{:.2f}", "Score Win": "{:.2f}"
                }), use_container_width=True)
                
                st.markdown("### 🗺️ Mappa di Calore Globale (Robustezza Score RoMD)")
                try:
                    import plotly.express as px
                    pivot_df = df_global.pivot_table(values="Score RoMD", index="DTS", columns="TP", aggfunc="mean")
                    fig = px.imshow(pivot_df, text_auto=".2f", color_continuous_scale="RdYlGn", aspect="auto", origin='lower')
                    fig.update_layout(title="Score RoMD Globale per Combinazione (TP vs DTS)", xaxis_title="Take Profit (TP)", yaxis_title="Distanza Sicurezza (DTS)")
                    st.plotly_chart(fig, use_container_width=True)
                except Exception as e:
                    st.warning(f"Impossibile renderizzare la Heatmap: {e}")
                    
            else:
                st.warning("Nessun risultato ottenuto (griglia vuota o nessun test eseguito).")
"""
with open('Dashboard.py', 'a', encoding='utf-8') as f:
    f.write(code)
