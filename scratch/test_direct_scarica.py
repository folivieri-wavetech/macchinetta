import sys
sys.path.insert(0, '/data')
sys.path.insert(0, '/app')
sys.argv = ['Motore_Trend.py', 'FIORDOK_DEMO']

import Motore_Trend

c = Motore_Trend.scarica_candele_yahoo("Spot Gold", "HOUR", px_live=4427.5)
sub55 = c[-55:]
max_h = max(x["highPrice"]["bid"] for x in sub55)
min_l = min(x["lowPrice"]["bid"] for x in sub55)
print(f"Direct scarica_candele_yahoo -> Max: {max_h} | Min: {min_l} | KJ: {(max_h+min_l)/2}")
