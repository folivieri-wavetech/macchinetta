import json

# 1. 30S State
d30 = {
    "balance": 9936.60,
    "trading_enabled": True,
    "position": {
        "direction": "LONG",
        "open_price": 4266.67,
        "contracts": 5,
        "open_time": "00:33:00",
        "ts_active": False,
        "ts_price": None,
        "peak_price": 4266.67
    },
    "increments": [
        {"id": 1789598370292, "direction": "LONG", "open_price": 4275.79, "contracts": 3, "tp_price": 4277.79, "open_time": "00:39:30"},
        {"id": 1789598400080, "direction": "LONG", "open_price": 4275.55, "contracts": 3, "tp_price": 4277.55, "open_time": "00:40:00"},
        {"id": 1789598430906, "direction": "LONG", "open_price": 4275.29, "contracts": 3, "tp_price": 4277.29, "open_time": "00:40:30"},
        {"id": 1789598460324, "direction": "LONG", "open_price": 4274.93, "contracts": 3, "tp_price": 4276.93, "open_time": "00:41:00"},
        {"id": 1789598490424, "direction": "LONG", "open_price": 4274.13, "contracts": 3, "tp_price": 4276.13, "open_time": "00:41:30"}
    ],
    "inc_tp_pips": 2.0,
    "trades": [
        {"time": "00:33:00", "action": "OPEN CORE LONG", "open_price": 4266.67, "close_price": None, "contracts": 5, "pnl": 0.0, "balance": 9936.60, "reason": "S&R Supporto: Prezzo > KJ55"},
        {"time": "00:39:30", "action": "➕ OPEN INC LONG (+3 Contr., Tot: 8)", "open_price": 4275.79, "close_price": None, "contracts": 3, "pnl": 0.0, "balance": 9936.60, "reason": "Barra 30s su Supporto KJ | TP: 4277.79 (+2 pip)"},
        {"time": "00:40:00", "action": "➕ OPEN INC LONG (+3 Contr., Tot: 11)", "open_price": 4275.55, "close_price": None, "contracts": 3, "pnl": 0.0, "balance": 9936.60, "reason": "Barra 30s su Supporto KJ | TP: 4277.55 (+2 pip)"},
        {"time": "00:40:30", "action": "➕ OPEN INC LONG (+3 Contr., Tot: 14)", "open_price": 4275.29, "close_price": None, "contracts": 3, "pnl": 0.0, "balance": 9936.60, "reason": "Barra 30s su Supporto KJ | TP: 4277.29 (+2 pip)"},
        {"time": "00:41:00", "action": "➕ OPEN INC LONG (+3 Contr., Tot: 17)", "open_price": 4274.93, "close_price": None, "contracts": 3, "pnl": 0.0, "balance": 9936.60, "reason": "Barra 30s su Supporto KJ | TP: 4276.93 (+2 pip)"},
        {"time": "00:41:30", "action": "➕ OPEN INC LONG (+3 Contr., Tot: 20)", "open_price": 4274.13, "close_price": None, "contracts": 3, "pnl": 0.0, "balance": 9936.60, "reason": "Barra 30s su Supporto KJ | TP: 4276.13 (+2 pip)"}
    ],
    "candles": [],
    "last_ts_cycle": None
}

with open("hyper_gold_state.json", "w", encoding="utf-8") as f:
    json.dump(d30, f, indent=2, ensure_ascii=False)

# 2. M5 State
d_m5 = {
    "balance": 10000.0,
    "trading_enabled": True,
    "position": {
        "direction": "SHORT",
        "open_price": 4259.81,
        "contracts": 5,
        "open_time": "00:20:00",
        "ts_active": False,
        "ts_price": None,
        "peak_price": 4259.81
    },
    "increments": [
        {"id": 1789597501633, "direction": "SHORT", "open_price": 4261.61, "contracts": 3, "tp_price": 4257.61, "open_time": "00:25:01"},
        {"id": 1789597800105, "direction": "SHORT", "open_price": 4261.94, "contracts": 3, "tp_price": 4257.94, "open_time": "00:30:00"},
        {"id": 1789598100230, "direction": "SHORT", "open_price": 4270.15, "contracts": 3, "tp_price": 4266.15, "open_time": "00:35:00"},
        {"id": 1789598400042, "direction": "SHORT", "open_price": 4275.55, "contracts": 3, "tp_price": 4271.55, "open_time": "00:40:00"}
    ],
    "inc_tp_pips": 5.0,
    "trades": [
        {"time": "00:20:00", "action": "OPEN CORE SHORT", "open_price": 4259.81, "close_price": None, "contracts": 5, "pnl": 0.0, "balance": 10000.0, "reason": "Prezzo < TK144 (4301.57) e Close < KJ (4301.57) | TS Trigger: +10p, Lock: +6p, Step: 2p"},
        {"time": "00:25:01", "action": "➕ OPEN INC SHORT (+3 Contr., Tot: 8)", "open_price": 4261.61, "close_price": None, "contracts": 3, "pnl": 0.0, "balance": 10000.0, "reason": "Barra M5 verde su Resistenza KJ | TP: 4257.61 (+5 pip)"},
        {"time": "00:30:00", "action": "➕ OPEN INC SHORT (+3 Contr., Tot: 11)", "open_price": 4261.94, "close_price": None, "contracts": 3, "pnl": 0.0, "balance": 10000.0, "reason": "Barra M5 verde su Resistenza KJ | TP: 4257.94 (+5 pip)"},
        {"time": "00:35:00", "action": "➕ OPEN INC SHORT (+3 Contr., Tot: 14)", "open_price": 4270.15, "close_price": None, "contracts": 3, "pnl": 0.0, "balance": 10000.0, "reason": "Barra M5 verde su Resistenza KJ | TP: 4266.15 (+5 pip)"},
        {"time": "00:40:00", "action": "➕ OPEN INC SHORT (+3 Contr., Tot: 17)", "open_price": 4275.55, "close_price": None, "contracts": 3, "pnl": 0.0, "balance": 10000.0, "reason": "Barra M5 verde su Resistenza KJ | TP: 4271.55 (+5 pip)"}
    ],
    "candles": [],
    "last_ts_cycle": None
}

with open("hyper_gold_m1_state.json", "w", encoding="utf-8") as f:
    json.dump(d_m5, f, indent=2, ensure_ascii=False)

print("Both state files restored cleanly with 100% precision!")
