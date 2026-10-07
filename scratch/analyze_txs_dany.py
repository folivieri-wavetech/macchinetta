import sys, json

with open('/tmp/txs_dany.json') as f:
    txs = json.load(f)

print(f"Total transactions: {len(txs)}")

# Filtriamo le transazioni dal 2 ottobre 2026 15:59:00 UTC (17:59:00 italiane) in poi
for t in txs:
    d = t.get('dateUtc', '')
    if d >= '2026-10-02T15:59:00':
        inst = t.get('instrumentName', '')
        tt = t.get('transactionType', '')
        sz = t.get('size', '')
        op = t.get('openLevel', '')
        cl = t.get('closeLevel', '')
        pnl = t.get('profitAndLoss', '')
        op_d = t.get('openDateUtc', '')
        ref = t.get('reference', '')
        print(f"{d} (Open: {op_d}) | {inst} | {tt} {sz} | Op: {op} -> Cl: {cl} | PnL: {pnl} | Ref: {ref}")
