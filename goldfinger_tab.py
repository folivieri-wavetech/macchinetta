import os
import time
import json
import datetime
import streamlit as st
from dotenv import dotenv_values

try:
    from zoneinfo import ZoneInfo
    TZ_ITALIA = ZoneInfo("Europe/Rome")
except Exception:
    TZ_ITALIA = datetime.timezone(datetime.timedelta(hours=2))

def now_it():
    return datetime.datetime.now(TZ_ITALIA)

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))

def get_goldfinger_paths(conto):
    base = os.path.join(ROOT_DIR, conto)
    if not os.path.exists(base):
        base = os.path.join("/data", conto)
    return {
        "config": os.path.join(base, "config_goldfinger.json"),
        "stato": os.path.join(base, "stato_goldfinger.json"),
        "log": os.path.join(base, "goldfinger.log"),
        "stato_sistema": os.path.join(base, "stato_sistema.json"),
        "posizioni": os.path.join(base, "posizioni_aperte.json")
    }

def leggi_json_sicuro(path):
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def calcola_livello_chirurgico_gold(conto, px_live=None):
    """
    Calcola il livello chirurgico di partenza Short analizzando la struttura H1:
    - Prende in considerazione ESCLUSIVAMENTE i minimi che si trovano SOTTO la quotazione live.
    - Seleziona il supporto più prossimo sotto il prezzo live (o minimo H1 sotto live).
    - Applica rigorosamente la regola dei -5 pip sotto il riferimento preso.
    - Se il prezzo batte nuovi minimi assoluti (nessun minimo sotto il live), calcola -5 pip dal prezzo live.
    - Zero chiamate IG (solo file locali).
    """
    candidates = [
        os.path.join(ROOT_DIR, conto, "candele_Spot_Gold_HOUR.json"),
        os.path.join("/data", conto, "candele_Spot_Gold_HOUR.json"),
        os.path.join(ROOT_DIR, "candele_Spot_Gold_HOUR.json"),
        os.path.join("/data", "candele_Spot_Gold_HOUR.json"),
        os.path.join(ROOT_DIR, "FIORDOK_DEMO", "candele_Spot_Gold_HOUR.json"),
        os.path.join("/data", "FIORDOK_DEMO", "candele_Spot_Gold_HOUR.json"),
        os.path.join(ROOT_DIR, "DANY_DEMO", "candele_Spot_Gold_HOUR.json"),
        os.path.join("/data", "DANY_DEMO", "candele_Spot_Gold_HOUR.json"),
    ]
    candele = []
    for p in candidates:
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    d = json.load(f)
                    if isinstance(d, list) and len(d) >= 21:
                        candele = d
                        break
            except Exception:
                pass
                
    if not candele or len(candele) < 21:
        return None, None, None, None, None, None, None
        
    px = float(px_live) if px_live else None

    # Finestra 55 ore
    candele_55 = candele[-55:] if len(candele) >= 55 else candele
    lows_55 = [float(c.get('lowPrice', {}).get('bid') or c.get('lowPrice', {}).get('ask') or c.get('low')) for c in candele_55 if (c.get('lowPrice') or c.get('low'))]
    l55_all = min(lows_55) if lows_55 else 0.0

    # Finestra 21 ore
    candele_21 = candele[-21:]
    lows_21 = [float(c.get('lowPrice', {}).get('bid') or c.get('lowPrice', {}).get('ask') or c.get('low')) for c in candele_21 if (c.get('lowPrice') or c.get('low'))]
    l21_all = min(lows_21) if lows_21 else 0.0

    # Finestra 9 ore
    candele_9 = candele[-9:]
    lows_9 = [float(c.get('lowPrice', {}).get('bid') or c.get('lowPrice', {}).get('ask') or c.get('low')) for c in candele_9 if (c.get('lowPrice') or c.get('low'))]
    l9_all = min(lows_9) if lows_9 else l21_all

    # FILTRO CHIRURGICO: Considera SOLO i minimi rigorosamente SOTTO la quotazione live
    if px is not None:
        lows_55_sotto = [low for low in lows_55 if low < px]
        lows_21_sotto = [low for low in lows_21 if low < px]
        lows_9_sotto = [low for low in lows_9 if low < px]
    else:
        lows_55_sotto = lows_55
        lows_21_sotto = lows_21
        lows_9_sotto = lows_9

    l55 = min(lows_55_sotto) if lows_55_sotto else None
    l21 = min(lows_21_sotto) if lows_21_sotto else None
    l9 = min(lows_9_sotto) if lows_9_sotto else None

    # Supporto Immediato sotto il prezzo live (il più alto dei minimi sotto px)
    sup_immediato = max(lows_55_sotto) if lows_55_sotto else None

    # Pavimento strutturale sotto il live
    if l21 is not None and l55 is not None:
        if (l21 - l55) <= 12.0:
            min_strutturale = l55
        else:
            min_strutturale = l21
    elif l21 is not None:
        min_strutturale = l21
    elif l55 is not None:
        min_strutturale = l55
    else:
        min_strutturale = None

    # Riferimento Primario:
    # Se esiste un supporto passato sotto il live, usiamo il supporto più prossimo.
    # Altrimenti (nuovo minimo assoluto delle 55h), usiamo direttamente il prezzo live.
    if sup_immediato is not None:
        riferimento = sup_immediato
        rif_tipo = "Supporto H1 sotto Live"
    elif px is not None:
        riferimento = px
        rif_tipo = "Nuovo Minimo Assoluto (Prezzo Live)"
    else:
        riferimento = l21_all
        rif_tipo = "Minimo Storico"

    # Regola Operativa Immodificabile: Sempre 5 pip SOTTO il riferimento preso
    suggerito = round(riferimento - 5.0, 2)

    return (
        suggerito,
        round(riferimento, 2),
        round(min_strutturale, 2) if min_strutturale is not None else None,
        rif_tipo,
        round(l55, 2) if l55 is not None else None,
        round(l21, 2) if l21 is not None else None,
        round(l9, 2) if l9 is not None else None
    )

def calcola_scaglioni_interi(pz_start, passo, size_unit, delta_tot):
    if delta_tot <= 0 or pz_start is None or pz_start <= 0:
        return []
    num_scaglioni = max(1, int(delta_tot) // int(size_unit))
    sizes = [int(size_unit)] * num_scaglioni
    residuo = int(delta_tot) - sum(sizes)
    if residuo > 0:
        sizes[-1] += int(residuo)
    scaglioni = []
    for i, sz in enumerate(sizes):
        pz_lvl = round(pz_start - (i * passo), 2)
        scaglioni.append({
            "numero": i + 1,
            "prezzo_target": pz_lvl,
            "size": int(sz),
            "stato": "IN_ATTESA",
            "deal_id": None,
            "open_price": None,
            "sl_price": None,
            "opened_at": None
        })
    return scaglioni

def scrivi_json_sicuro(path, dati):
    try:
        tmp = f"{path}.tmp.{os.getpid()}"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(dati, f, indent=4)
        os.replace(tmp, path)
        return True
    except Exception:
        return False

def recupera_prezzo_live_gold(conto, st_sys, stato, pos_live):
    """
    Recupera il prezzo Bid/Ask live per Spot Gold con fallback a cascata per garantire freschezza continua:
    1. Da stato_sistema.json del conto corrente
    2. Da posizioni_aperte.json se presente una posizione aperta su Gold (ha bid e offer IG in tempo reale)
    3. Dallo streaming Lightstreamer attivo negli altri conti condivisi (FIORDOK_DEMO, BONGIOLO_DEMO, DANY_DEMO)
    4. Da stato_goldfinger.json
    """
    # 1. Da stato_sistema del conto corrente
    px_ba = st_sys.get("prezzi_bid_ask", {}).get("Spot Gold", {})
    if px_ba.get("bid") and px_ba.get("ask"):
        return float(px_ba["bid"]), float(px_ba["ask"]), st_sys.get("ultimo_aggiornamento", "")

    # 2. Da posizioni_aperte del conto
    for p in pos_live:
        inst = str(p.get("instrument", "")).upper()
        epic = str(p.get("epic", "")).upper()
        if "GOLD" in inst or "GOLD" in epic or "CFEGOLD" in epic:
            b, a = p.get("bid"), p.get("offer")
            if b and a:
                return float(b), float(a), "Feed Posizioni IG"

    # 3. Dallo streaming condiviso degli altri conti (zero chiamate API)
    for c_other in ["FIORDOK_DEMO", "BONGIOLO_DEMO", "DANY_DEMO"]:
        c_paths = [
            os.path.join(ROOT_DIR, c_other, "stato_sistema.json"),
            os.path.join("/data", c_other, "stato_sistema.json")
        ]
        for cp in c_paths:
            if os.path.exists(cp):
                try:
                    with open(cp, "r", encoding="utf-8") as f:
                        d = json.load(f)
                        p_ba = d.get("prezzi_bid_ask", {}).get("Spot Gold", {})
                        if p_ba.get("bid") and p_ba.get("ask"):
                            return float(p_ba["bid"]), float(p_ba["ask"]), d.get("ultimo_aggiornamento", "")
                except Exception:
                    pass

    # 4. Da stato_goldfinger.json
    if stato.get("ultimo_prezzo_bid") and stato.get("ultimo_prezzo_ask"):
        return float(stato["ultimo_prezzo_bid"]), float(stato["ultimo_prezzo_ask"]), stato.get("ultimo_aggiornamento", "")

    return None, None, ""

@st.fragment(run_every=10)
def renderizza_tab_goldfinger(conto):
    paths = get_goldfinger_paths(conto)
    cfg = leggi_json_sicuro(paths["config"])
    stato = leggi_json_sicuro(paths["stato"])
    st_sys = leggi_json_sicuro(paths["stato_sistema"])
    pos_live = leggi_json_sicuro(paths["posizioni"])
    if not isinstance(pos_live, list):
        pos_live = []

    # 1. Calcolo Delta Live su Spot Gold
    tot_long = 0
    tot_short = 0
    for p in pos_live:
        inst = str(p.get("instrument", "")).upper()
        epic = str(p.get("epic", "")).upper()
        if "GOLD" in inst or "GOLD" in epic or "CFEGOLD" in epic:
            sz = int(float(p.get("size", 0)))
            d = p.get("direction", "").upper()
            if d in ("BUY", "LONG"):
                tot_long += sz
            elif d in ("SELL", "SHORT"):
                tot_short += sz

    delta_calcolato = max(0, tot_long - tot_short)

    # 2. Prezzo Live Gold con fallback e orario aggiornamento
    bid_live, ask_live, ora_agg = recupera_prezzo_live_gold(conto, st_sys, stato, pos_live)

    # Stato del modulo
    is_attivo = cfg.get("attivo", False)
    stato_operativo = stato.get("stato_operativo", "IDLE")

    st.markdown("""
        <div style='display: flex; align-items: center; justify-content: space-between; margin-top: -10px; margin-bottom: 12px;'>
            <div>
                <h1 style='color: #FFD700; margin: 0; font-size: 1.8rem; font-weight: 800;'>🏆 Goldfinger - Paracadute e Copertura Spot Gold</h1>
                <p style='color: #94a3b8; margin: 2px 0 0 0; font-size: 0.88rem;'>Modulo chirurgico di difesa a scaglioni (Passo 6 pip) con incasso su rimbalzo e riarmo seconda ondata • <i>Auto-refresh ogni 10s</i></p>
            </div>
        </div>
    """, unsafe_allow_html=True)

    # Metriche principali compatte
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        bid_str = f"{float(bid_live):.2f}" if bid_live else "--"
        ask_str = f"{float(ask_live):.2f}" if ask_live else "--"
        info_sub = f"IG Live • {ora_agg}" if ora_agg else "Prezzo Bid / Ask IG"
        st.markdown(
            f"<div style='background: #0f172a; border: 1px solid #1e293b; border-radius: 6px; padding: 8px 12px; min-height: 64px;'>"
            f"<div style='color: #94a3b8; font-size: 0.72rem; font-weight: 600; text-transform: uppercase;'>🟡 Spot Gold Live</div>"
            f"<div style='color: #f8fafc; font-size: 1.05rem; font-weight: 700; margin-top: 3px;'>{bid_str} / {ask_str}</div>"
            f"<div style='color: #64748b; font-size: 0.68rem; margin-top: 2px;'>{info_sub}</div>"
            f"</div>",
            unsafe_allow_html=True
        )
    with c2:
        if not is_attivo:
            st_text = "🔴 INATTIVO"
            st_desc = "Robot fermo"
            st_col = "#ef4444"
        elif stato_operativo == "ARMED_ROLLOVER":
            st_text = "🟡 ARMATO (Rollover)"
            st_desc = "Pausa serale 22:55-00:15"
            st_col = "#eab308"
        else:
            st_text = "🟢 ATTIVO H24"
            st_desc = "Guardia a mercato"
            st_col = "#22c55e"
        st.markdown(
            f"<div style='background: #0f172a; border: 1px solid #1e293b; border-radius: 6px; padding: 8px 12px; min-height: 64px;'>"
            f"<div style='color: #94a3b8; font-size: 0.72rem; font-weight: 600; text-transform: uppercase;'>🛡️ Stato Guardia</div>"
            f"<div style='color: {st_col}; font-size: 1.05rem; font-weight: 700; margin-top: 3px;'>{st_text}</div>"
            f"<div style='color: #64748b; font-size: 0.68rem; margin-top: 2px;'>{st_desc}</div>"
            f"</div>",
            unsafe_allow_html=True
        )
    with c3:
        st.markdown(
            f"<div style='background: #0f172a; border: 1px solid #1e293b; border-radius: 6px; padding: 8px 12px; min-height: 64px;'>"
            f"<div style='color: #94a3b8; font-size: 0.72rem; font-weight: 600; text-transform: uppercase;'>⚖️ Delta Scoperto IG</div>"
            f"<div style='color: #38bdf8; font-size: 1.05rem; font-weight: 700; margin-top: 3px;'>{delta_calcolato} mini</div>"
            f"<div style='color: #64748b; font-size: 0.68rem; margin-top: 2px;'>+{tot_long} L / -{tot_short} S</div>"
            f"</div>",
            unsafe_allow_html=True
        )
    with c4:
        pnl_inc = stato.get("totale_incassato", 0.0)
        pnl_col = "#94a3b8" if pnl_inc == 0 else ("#22c55e" if pnl_inc > 0 else "#ef4444")
        st.markdown(
            f"<div style='background: #0f172a; border: 1px solid #1e293b; border-radius: 6px; padding: 8px 12px; min-height: 64px;'>"
            f"<div style='color: #94a3b8; font-size: 0.72rem; font-weight: 600; text-transform: uppercase;'>💰 Cash Incassato</div>"
            f"<div style='color: {pnl_col}; font-size: 1.05rem; font-weight: 700; margin-top: 3px;'>{pnl_inc:+.2f} €</div>"
            f"<div style='color: #64748b; font-size: 0.68rem; margin-top: 2px;'>Dai rimbalzi (+7 pip)</div>"
            f"</div>",
            unsafe_allow_html=True
        )

    st.markdown("<hr style='margin: 10px 0; border-color: #334155;'>", unsafe_allow_html=True)

    col_ctrl, col_ladder = st.columns([5, 7])

    with col_ctrl:
        st.markdown("<h4 style='color: #38bdf8; margin-bottom: 8px;'>⚙️ Parametri di Ingresso</h4>", unsafe_allow_html=True)
        
        saved_pz1 = float(cfg.get("livello_1_prezzo") or 0.0)
        
        # Calcolo Livello Chirurgico Consigliato (Minimi H1 sotto il live con offset -5 pip, sempre ricalcolato anche a guardia già partita)
        sugg_lvl, rif_val, min_stru_val, rif_tipo, l55_val, l21_val, l9_val = calcola_livello_chirurgico_gold(conto, px_live=bid_live)
        
        if sugg_lvl is not None:
            min55_str = f"{l55_val:.2f}" if l55_val is not None else "--"
            min21_str = f"{l21_val:.2f}" if l21_val is not None else "--"
            min9_str = f"{l9_val:.2f}" if l9_val is not None else "--"
            
            # Badge di confronto se il robot è già attivo a mercato
            confronto_armato_html = ""
            if is_attivo and saved_pz1 > 0:
                diff_pts = sugg_lvl - saved_pz1
                diff_sign = f"+{diff_pts:.2f}" if diff_pts >= 0 else f"{diff_pts:.2f}"
                confronto_armato_html = f"<span style='color: #94a3b8; font-size: 0.74rem; font-weight: 500; margin-left: 10px;'>(In esecuzione @ <b style='color: #facc15;'>{saved_pz1:.2f}</b> • Delta: {diff_sign} pip)</span>"
            
            st.markdown(f"""
                <div style='background: rgba(14, 165, 233, 0.08); border: 1px solid rgba(56, 189, 248, 0.3); border-radius: 8px; padding: 10px 14px; margin-bottom: 12px;'>
                    <div style='display: flex; justify-content: space-between; align-items: center;'>
                        <span style='color: #38bdf8; font-weight: 700; font-size: 0.84rem;'>🎯 LIVELLO CHIRURGICO CONSIGLIATO (-5 pip):</span>
                        <div>
                            <span style='color: #FFD700; font-weight: 800; font-size: 1.15rem;'>{sugg_lvl:.2f}</span>
                            {confronto_armato_html}
                        </div>
                    </div>
                    <div style='color: #94a3b8; font-size: 0.74rem; margin-top: 4px;'>
                        Riferimento: <b>{rif_tipo} ({rif_val:.2f}) - 5 pip</b> | Minimi sotto live: <b>Min21: {min21_str}</b> | <b>Min55: {min55_str}</b> | <b>Min9: {min9_str}</b>
                    </div>
                </div>
            """, unsafe_allow_html=True)

        # Prezzo Livello 1 (Obbligatorio)
        def_pz1 = float(bid_live) if bid_live else 0.0
        
        ss_key = f"gf_pz1_{conto}"
        val_default = st.session_state.get(ss_key)
        if val_default is None:
            # Il valore salvato o suggerito è valido SOLO se rigorosamente sotto la quotazione live
            if saved_pz1 > 0 and (not bid_live or float(saved_pz1) < float(bid_live)):
                val_default = float(saved_pz1)
            elif sugg_lvl is not None and (not bid_live or float(sugg_lvl) < float(bid_live)):
                val_default = float(sugg_lvl)
            elif def_pz1 > 0:
                val_default = float(round(def_pz1 - 5.0, 2))
            else:
                val_default = 0.0

        col_inp, col_btn_sugg = st.columns([7, 5], vertical_alignment="bottom")
        with col_inp:
            pz_l1 = st.number_input(
                "🎯 Prezzo Livello 1 (Partenza)",
                min_value=0.0,
                max_value=10000.0,
                value=float(val_default),
                step=1.0,
                format="%.2f",
                key=f"input_{ss_key}",
                help="Prezzo a cui scatterà il primo scaglione SHORT a mercato."
            )
        with col_btn_sugg:
            if sugg_lvl is not None:
                if st.button(f"🎯 Usa {sugg_lvl:.2f}", key=f"btn_sugg_{conto}", use_container_width=True, help="Applica il prezzo chirurgico consigliato al Livello 1"):
                    st.session_state[ss_key] = float(sugg_lvl)
                    st.rerun()

        cp, cs = st.columns(2)
        with cp:
            passo = st.number_input("Passo Scaglioni (pip)", min_value=1.0, max_value=50.0, value=float(cfg.get("passo_pip", 6.0)), step=1.0)
        with cs:
            size_u = st.number_input("Size Tranche (Interi)", min_value=1, max_value=20, value=int(cfg.get("size_scaglione", 3)), step=1)

        delta_input = st.number_input("Delta Contratti da Coprire", min_value=1, max_value=100, value=int(delta_calcolato if delta_calcolato > 0 else 15), step=1)

        st.markdown("<div style='margin-top: 15px;'></div>", unsafe_allow_html=True)

        if not is_attivo:
            if st.button("🚀 AVVIA GOLDFINGER", type="primary", use_container_width=True):
                # Blocco anti-errore
                if pz_l1 <= 0:
                    st.error("🛑 ERRORE DI SICUREZZA: Devi inserire un prezzo valido per il Livello 1 prima di avviare!")
                elif bid_live and pz_l1 >= float(bid_live):
                    st.error(f"🛑 ERRORE DI SICUREZZA: Il prezzo Livello 1 ({pz_l1:.2f}) deve essere RIGOROSAMENTE INFERIORE al prezzo live ({float(bid_live):.2f}) per una copertura Short a scendere!")
                elif bid_live and (float(bid_live) - pz_l1) > 200:
                    st.error(f"🛑 ERRORE: Il prezzo Livello 1 ({pz_l1:.2f}) è troppo distante dal prezzo attuale ({float(bid_live):.2f}). Verifica il valore!")
                else:
                    new_cfg = {
                        "attivo": True,
                        "livello_1_prezzo": float(pz_l1),
                        "passo_pip": float(passo),
                        "size_scaglione": int(size_u),
                        "delta_totale": int(delta_input),
                        "avviato_il": now_it().strftime("%Y-%m-%d %H:%M:%S")
                    }
                    scrivi_json_sicuro(paths["config"], new_cfg)
                    st.success(f"✅ GOLDFINGER AVVIATO: Guardia armata dal livello {pz_l1:.2f} in giù.")
                    time.sleep(0.5)
                    st.rerun()
        else:
            st.markdown(
                "<div style='background: rgba(234, 179, 8, 0.1); border: 1px solid rgba(234, 179, 8, 0.35); border-radius: 6px; padding: 6px 10px; margin-bottom: 8px; color: #facc15; font-size: 0.80rem; font-weight: 600; text-align: center; letter-spacing: 0.3px;'>"
                "⚠️ GOLDFINGER È ATTIVO E OPERATIVO A MERCATO"
                "</div>",
                unsafe_allow_html=True
            )

            # Hot-Update a Chirurgico (se nessuna posizione è già aperta a mercato)
            scaglioni_att = stato.get("scaglioni", [])
            aperti_att = [s for s in scaglioni_att if s.get("stato") in ("APERTO", "PROTETTO_BE")]

            if len(aperti_att) == 0 and sugg_lvl is not None and abs(float(sugg_lvl) - float(saved_pz1)) > 0.01:
                if st.button(f"🎯 Aggiorna a Chirurgico ({sugg_lvl:.2f})", key=f"btn_aggiorna_chir_{conto}", type="primary", use_container_width=True):
                    if bid_live and float(sugg_lvl) >= float(bid_live):
                        st.error(f"🛑 ERRORE DI SICUREZZA: Il livello chirurgico ({sugg_lvl:.2f}) non è inferiore al prezzo live ({float(bid_live):.2f})!")
                    else:
                        new_cfg = cfg.copy()
                        new_cfg["livello_1_prezzo"] = float(sugg_lvl)
                        new_cfg["aggiornato_il"] = now_it().strftime("%Y-%m-%d %H:%M:%S")
                        scrivi_json_sicuro(paths["config"], new_cfg)

                        new_stato = stato.copy()
                        new_stato["livello_1_prezzo"] = float(sugg_lvl)
                        new_stato["scaglioni"] = calcola_scaglioni_interi(
                            float(sugg_lvl),
                            float(cfg.get("passo_pip", passo)),
                            int(cfg.get("size_scaglione", size_u)),
                            int(cfg.get("delta_totale", delta_input))
                        )
                        scrivi_json_sicuro(paths["stato"], new_stato)
                        st.session_state[ss_key] = float(sugg_lvl)
                        st.success(f"✅ Guardia aggiornata a Chirurgico: Livello 1 spostato a {sugg_lvl:.2f} con scaglioni ricalcolati!")
                        time.sleep(0.5)
                        st.rerun()
            elif len(aperti_att) > 0:
                st.caption(f"🔒 Guardia a mercato: {len(aperti_att)} scaglioni aperti. Fermare con STOP per riarmare da zero.")

            if st.button("🛑 STOP GOLDFINGER", type="secondary", use_container_width=True):
                new_cfg = cfg.copy()
                new_cfg["attivo"] = False
                new_cfg["fermato_il"] = now_it().strftime("%Y-%m-%d %H:%M:%S")
                scrivi_json_sicuro(paths["config"], new_cfg)
                st.info("🛑 GOLDFINGER ARRESTATO. Le posizioni aperte rimangono intatte sotto gestione manuale.")
                time.sleep(0.5)
                st.rerun()

    with col_ladder:
        st.markdown("<h4 style='color: #FFD700; margin-bottom: 8px;'>📋 Scaletta Scaglioni e Monitoraggio</h4>", unsafe_allow_html=True)
        
        scaglioni = stato.get("scaglioni", [])
        if not scaglioni and pz_l1 > 0:
            # Calcolo preview scala
            num_sc = max(1, int(delta_input) // int(size_u))
            sizes = [int(size_u)] * num_sc
            res = int(delta_input) - sum(sizes)
            if res > 0: sizes[-1] += res
            preview_sc = []
            for i, sz in enumerate(sizes):
                preview_sc.append({
                    "numero": i + 1,
                    "prezzo_target": round(pz_l1 - (i * passo), 2),
                    "size": sz,
                    "stato": "IN_ATTESA"
                })
            scaglioni = preview_sc

        if scaglioni:
            tab_rows = ""
            for s in scaglioni:
                st_code = s.get("stato", "IN_ATTESA")
                if st_code == "IN_ATTESA":
                    st_badge = "<span style='color: #94a3b8; font-weight: bold;'>⏳ In Attesa</span>"
                elif st_code == "APERTO":
                    st_badge = f"<span style='color: #38bdf8; font-weight: bold;'>🟢 APERTO @ {s.get('open_price', 0):.2f}</span>"
                elif st_code == "PROTETTO_BE":
                    st_badge = f"<span style='color: #22c55e; font-weight: bold;'>🛡️ BE+1 (SL: {s.get('sl_price', 0):.2f})</span>"
                elif st_code == "CHIUSO":
                    st_badge = "<span style='color: #FFD700; font-weight: bold;'>💰 Chiuso all'Incasso</span>"
                else:
                    st_badge = st_code
                
                pz_tgt = f"{s.get('prezzo_target', 0):.2f}"
                tab_rows += (
                    f"<tr style='border-bottom: 1px solid #334155; text-align: center;'>"
                    f"<td style='padding: 6px; font-weight: bold; text-align: center;'>Scaglione {s.get('numero')}</td>"
                    f"<td style='padding: 6px; color: #f8fafc; text-align: center;'>{pz_tgt}</td>"
                    f"<td style='padding: 6px; color: #38bdf8; font-weight: bold; text-align: center;'>-{s.get('size')} mini</td>"
                    f"<td style='padding: 6px; text-align: center;'>{st_badge}</td>"
                    f"</tr>"
                )

            html_table = (
                "<table style='width: 100%; border-collapse: collapse; font-size: 0.85rem; text-align: center;'>"
                "<thead>"
                "<tr style='border-bottom: 2px solid #64748b; color: #94a3b8; text-align: center;'>"
                "<th style='text-align: center; padding: 6px;'>Scaglione</th>"
                "<th style='text-align: center; padding: 6px;'>Trigger Prezzo</th>"
                "<th style='text-align: center; padding: 6px;'>Size Short</th>"
                "<th style='text-align: center; padding: 6px;'>Stato</th>"
                "</tr>"
                "</thead>"
                f"<tbody>{tab_rows}</tbody>"
                "</table>"
            )
            st.markdown(html_table, unsafe_allow_html=True)
            
            min_disc = stato.get("minimo_discesa")
            if min_disc is not None:
                sgancio = round(min_disc + 7.0, 2)
                st.markdown(
                    f"<div style='margin-top: 10px; padding: 8px 12px; background-color: #0f172a; border-left: 3px solid #38bdf8; border-radius: 4px; font-size: 0.82rem;'>"
                    f"📉 <b>Minimo Discesa Corrente:</b> <span style='color: #f8fafc;'>{min_disc:.2f}</span> &nbsp;|&nbsp; "
                    f"💥 <b>Soglia Chiusura Rimbalzo (+7 pip):</b> <span style='color: #FFD700; font-weight: bold;'>{sgancio:.2f}</span>"
                    f"</div>",
                    unsafe_allow_html=True
                )
        else:
            st.info("Imposta il Prezzo del Livello 1 a sinistra per visualizzare l'anteprima della scaletta.")

    # Storico Operazioni di Incasso
    st.markdown("<hr style='margin: 15px 0 10px 0; border-color: #334155;'>", unsafe_allow_html=True)
    with st.expander("📜 Registro Operazioni Chiuse da Goldfinger (Incassi e Stop)", expanded=False):
        storico = stato.get("storico_operazioni", [])
        if storico:
            r_html = ""
            for op in reversed(storico[-30:]):
                pnl = op.get("pnl", 0.0)
                pnl_c = "#22c55e" if pnl >= 0 else "#ef4444"
                r_html += (
                    f"<tr style='border-bottom: 1px solid #1e293b; text-align: center;'>"
                    f"<td style='padding: 5px; color: #94a3b8; text-align: center;'>{op.get('data')}</td>"
                    f"<td style='padding: 5px; text-align: center;'>Scaglione {op.get('scaglione')}</td>"
                    f"<td style='padding: 5px; text-align: center;'>{op.get('size')} mini</td>"
                    f"<td style='padding: 5px; text-align: center;'>{op.get('open'):.2f}</td>"
                    f"<td style='padding: 5px; text-align: center;'>{op.get('close'):.2f}</td>"
                    f"<td style='padding: 5px; color: {pnl_c}; font-weight: bold; text-align: center;'>{pnl:+.2f} €</td>"
                    f"<td style='padding: 5px; color: #94a3b8; text-align: center;'>{op.get('motivo')}</td>"
                    f"</tr>"
                )
            html_hist = (
                "<table style='width: 100%; border-collapse: collapse; font-size: 0.82rem; text-align: center;'>"
                "<thead>"
                "<tr style='border-bottom: 2px solid #475569; color: #94a3b8; text-align: center;'>"
                "<th style='text-align: center; padding: 5px;'>Data</th>"
                "<th style='text-align: center; padding: 5px;'>Scaglione</th>"
                "<th style='text-align: center; padding: 5px;'>Size</th>"
                "<th style='text-align: center; padding: 5px;'>Open</th>"
                "<th style='text-align: center; padding: 5px;'>Close</th>"
                "<th style='text-align: center; padding: 5px;'>PnL Netto</th>"
                "<th style='text-align: center; padding: 5px;'>Evento</th>"
                "</tr>"
                "</thead>"
                f"<tbody>{r_html}</tbody>"
                "</table>"
            )
            st.markdown(html_hist, unsafe_allow_html=True)
        else:
            st.caption("Nessuna operazione ancora chiusa in questa sessione.")
