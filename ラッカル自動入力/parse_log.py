import csv, re, sys

log = sys.stdin.read()

results = []
current_num = current_name = current_total = None

for line in log.splitlines():
    line = line.strip()
    m = re.match(r'\[(\d+)/164\] (.+?) → ¥([\d,]+)', line)
    if m:
        current_num = int(m.group(1))
        current_name = m.group(2)
        current_total = int(m.group(3).replace(',', ''))
        continue
    m2 = re.match(r'(.+?) (\d+)回中(\d+)回残 ¥([\d,]+)→¥([\d,]+)', line)
    if m2 and current_num is not None:
        results.append({
            '番号': current_num,
            '名前': current_name,
            '合計残高': current_total,
            '商品名': m2.group(1),
            '総回数': int(m2.group(2)),
            '残回数': int(m2.group(3)),
            '元金額': int(m2.group(4).replace(',', '')),
            '残金額': int(m2.group(5).replace(',', '')),
        })

out = r'C:\Users\弁護士法人響\Downloads\損害金計算結果.csv'
with open(out, 'w', encoding='utf-8-sig', newline='') as f:
    w = csv.DictWriter(f, fieldnames=['番号','名前','合計残高','商品名','総回数','残回数','元金額','残金額'])
    w.writeheader()
    w.writerows(results)

print(f"完了: {len(results)}行 → {out}")
