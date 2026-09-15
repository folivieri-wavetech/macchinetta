import sys, os
from test_increment_tp_tk import test_user_scenario_long, test_scenario_short

if __name__ == "__main__":
    test_user_scenario_long()
    test_scenario_short()
    print("TUTTI I TEST TAKE PROFIT INCREMENTI SU TENKAN (TK +- 50 pip) SUPERATI CON SUCCESSO!")
