import json, pathlib, sys

p = pathlib.Path('/tmp/perf_results.json')
if not p.exists():
    sys.exit()

data = json.loads(p.read_text())
if not data:
    sys.exit()

name_w = max(len(r['name']) for r in data)
header = f"{'Test':<{name_w}}  {'Time':>8}  {'Baseline':>8}  {'Delta':>8}"
print(header)
print('-' * len(header))
for r in data:
    delta = r['delta_pct']
    sign = '+' if delta > 0 else ''
    flag = ' REGRESSION' if r['regression'] else ''
    print(f"{r['name']:<{name_w}}  {r['elapsed']:>7.3f}s  {r['baseline']:>7.3f}s  {sign}{delta:>6.1f}%{flag}")
