import sys, os, json

sys.path.append(".")
import Dashboard

print("Starting test_radar...")
for conto_selezionato in ["FIORDOK_DEMO", "BONGIOLO_DEMO", "DANY_DEMO"]:
    print(f"\n--- Testing account: {conto_selezionato} ---")
    radar_data = {}
    ts_aggiornamento = None
    prezzi_live = {}
    accs = Dashboard.get_accounts()
    if conto_selezionato and conto_selezionato not in accs:
        accs = [conto_selezionato] + accs
        
    for c_dir in accs:
        r_file = os.path.join(c_dir, "radar_trend.json")
        if os.path.exists(r_file):
            try:
                with open(r_file, "r", encoding="utf-8") as f_rf:
                    rf_d = json.load(f_rf)
                    d_r = rf_d.get("radar_trend", {})
                    ts_r = rf_d.get("radar_trend_ts")
                    if d_r:
                        radar_data.update(d_r)
            except Exception as e:
                print("Err r_file:", e)
        st_file = os.path.join(c_dir, Dashboard.STATO_SISTEMA)
        if os.path.exists(st_file):
            try:
                with open(st_file, "r", encoding="utf-8") as f_st:
                    st_d = json.load(f_st)
                    pl = st_d.get("prezzi_live", {})
                    if pl:
                        prezzi_live.update(pl)
            except Exception as e:
                print("Err st_file:", e)

    tutti_strumenti = ["AUD/NZD", "CAD/JPY", "EUR/USD", "GBP/JPY", "GBP/USD", "USD/CAD", "USD/CHF", "USD/JPY", "Spot Gold", "US 500 Cash"]
    tf_map_code = {"M5": "MINUTE_5", "H1": "HOUR", "H4": "HOUR_4", "D1": "DAY"}
    
    for idx, s_nome in enumerate(tutti_strumenti):
        cfg_s = Dashboard.CONFIG_STRUMENTI.get(s_nome, {})
        dec = cfg_s.get("decimali", 2)
        mult = cfg_s.get("moltiplicatore", 0.0001)
        px = prezzi_live.get(s_nome)
        info_r = radar_data.get(s_nome, {})
        tf_dict = info_r.get("timeframes", {})
        trades_tf = {}
        check_dirs = [conto_selezionato] + [d for d in accs if d != conto_selezionato] if conto_selezionato else accs
        for c_dir in check_dirs:
            if not c_dir: continue
            mem_c = Dashboard.carica_memoria(c_dir)
            mem_s = mem_c.get(s_nome, {})
            if mem_s.get("attivo", False) and mem_s.get("stato") in ("LONG", "SHORT"):
                tf_a = mem_s.get("timeframe", "HOUR")
                tf_lbl = "M5" if "MINUTE_5" in tf_a else ("H1" if "HOUR" in tf_a and "HOUR_4" not in tf_a else ("H4" if "HOUR_4" in tf_a else "D1"))
                if tf_lbl not in trades_tf:
                    pos_c = mem_s.get("posizioni_core", [])
                    pos_i = mem_s.get("posizioni_incr", [])
                    tot_pnl_pts = 0.0
                    has_pos = False
                    if px and isinstance(px, (int, float)):
                        for pc in pos_c:
                            e_px = pc.get("entry")
                            sz = pc.get("size", 1)
                            d_pos = pc.get("direction", mem_s.get("stato"))
                            if e_px and isinstance(e_px, (int, float)) and e_px > 0:
                                has_pos = True
                                diff = (px - e_px) if d_pos == "LONG" else (e_px - px)
                                tot_pnl_pts += (diff / mult) * sz
                        for pi in pos_i:
                            e_px = pi.get("entry")
                            sz = pi.get("size", 1)
                            d_pos = pi.get("direction", mem_s.get("stato"))
                            if e_px and isinstance(e_px, (int, float)) and e_px > 0:
                                has_pos = True
                                diff = (px - e_px) if d_pos == "LONG" else (e_px - px)
                                tot_pnl_pts += (diff / mult) * sz
                    is_profit = (tot_pnl_pts >= 0) if has_pos else True
                    trades_tf[tf_lbl] = {
                        "stato": mem_s.get("stato"),
                        "conto": c_dir.replace("_DEMO", "").replace("_REALE", ""),
                        "is_profit": is_profit,
                        "pnl_pts": tot_pnl_pts
                    }
        # format radar cell
        for lbl_key in ["M5", "H1", "H4", "D1"]:
            t_data = tf_dict.get(lbl_key, {})
            kj_v = t_data.get("kj")
            dist_p = t_data.get("dist_pips")
            dir_p = t_data.get("dir", "-")
            vicino = t_data.get("vicino", False)
            if kj_v is None and px and isinstance(px, (int, float)):
                tf_code = tf_map_code.get(lbl_key, "HOUR")
                candele_c = Dashboard.carica_candele_locali_dash(conto_selezionato or "FIORDOK_DEMO", s_nome, tf_code, px_live=px)
                kj_c = Dashboard.calcola_kj55_da_candele_dash(candele_c, 55)
                if kj_c is not None:
                    kj_v = kj_c
                    diff_pts = px - kj_v
                    dist_p = round(abs(diff_pts) / mult)
            is_current_tf_trade = (lbl_key in trades_tf)
            if is_current_tf_trade:
                t_info = trades_tf[lbl_key]
                st_val = t_info["stato"]
                ct_val = t_info["conto"]
                is_profit = t_info.get("is_profit", True)
                pnl_pts = t_info.get("pnl_pts", 0.0)
                col_dir_tr = "#4ade80" if is_profit else "#f87171"
                icon_dir = "🟢" if is_profit else "🔴"
                pnl_sign = f"+{pnl_pts:.0f}" if pnl_pts > 0 else f"{pnl_pts:.0f}"
                title_tip = f"Conto: {ct_val} ({st_val}) | PnL: {pnl_sign} pt"
                kj_line = f"<span style='font-size:0.60rem; color:#FFFF00; font-weight:500;'>KJ: {kj_v:.{dec}f}</span>" if (kj_v is not None) else "<span style='font-size:0.60rem; color:#64748b;'>-</span>"
            elif kj_v is not None and dist_p is not None:
                kj_formatted = f"{kj_v:.{dec}f}"
                dist_int = int(round(dist_p))
    print(f"Radar test SUCCESS for {conto_selezionato}")
print("ALL TESTS COMPLETED SUCCESSFULLY!")
