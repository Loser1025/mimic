import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import gspread, statistics
from google.oauth2.service_account import Credentials

SCOPES = ['https://www.googleapis.com/auth/spreadsheets','https://www.googleapis.com/auth/drive']
creds = Credentials.from_service_account_file(
    r'C:\Users\Loser\Desktop\-\tamalabo\automation-visitor-shindan\ageless-impulse-488713-m6-03014b3cddad.json',
    scopes=SCOPES
)
gc  = gspread.authorize(creds)
sh  = gc.open_by_key('1ODTZoW_6M9WbI0jwIc9vt_Y8crQ1sLHE57kZe4MGG2w')
ws5  = sh.worksheet('2026.5 のコピー')
ws6  = sh.worksheet('2026.6　※石井作成中')
wsSE = sh.worksheet('2026.6 （SE)')
d5  = ws5.get_all_values()
d6  = ws6.get_all_values()
dSE = wsSE.get_all_values()

FIXED='固定休日'; KIBOU='希望休日'; PAID='有給休暇'
REST={FIXED,KIBOU}
DOW=['月','火','水','木','金','土','日']
WEEKS=[range(0,7),range(7,14),range(14,21),range(21,28)]

def is_work(s):      return s.strip()!='' and s not in {FIXED,KIBOU,PAID}
def is_work_se(s):   return '-' in s.strip().replace('\n','')

# ── SE日別稼働数（重複除去） ───────────────────────────────
JUN_SE = 13
se_unique = {}
for ri, row in enumerate(dSE[3:], 3):
    name = row[3].strip() if len(row)>3 else ''
    if not name: continue
    june = (list(row[JUN_SE:JUN_SE+30]) + ['']*30)[:30]
    wd   = sum(1 for s in june if is_work_se(s))
    if wd < 3: continue
    prev = sum(1 for s in se_unique[name] if is_work_se(s)) if name in se_unique else -1
    if wd > prev:
        se_unique[name] = june

se_cnt = [sum(1 for sh in se_unique.values() if is_work_se(sh[d])) for d in range(30)]
print(f'SE（重複除去）: {len(se_unique)}名')

# ── 5月末trailing（CONS） ─────────────────────────────────
hrow5 = next(i for i,r in enumerate(d5) if any('5/1' in str(c) for c in r))
may_trail = {}
for row in d5[hrow5+1:]:
    if len(row)>5 and row[1].strip()=='CONS' and row[5].strip():
        s31 = (list(row[6:37]) + ['']*31)[:31]
        t = 0
        for s in reversed(s31):
            if is_work(s): t += 1
            else: break
        may_trail[row[5].strip()] = t

# ── 6月CONSメンバー読み込み ───────────────────────────────
hrow6 = next(i for i,r in enumerate(d6) if any('6/1' in str(c) for c in r))
members = []
for ri, row in enumerate(d6):
    if ri <= hrow6: continue
    if len(row)>5 and row[1].strip()=='CONS' and row[5].strip() and row[5].strip()!='氏名':
        raw = (list(row[6:36]) + ['']*30)[:30]
        wv  = [s for s in raw if is_work(s)]
        members.append({
            'ri':       ri,
            'name':     row[5].strip(),
            'shifts':   raw,
            'fc':       sum(1 for s in raw if s==FIXED),
            'dft':      max(set(wv), key=wv.count) if wv else '9:00-18:00',
            'trailing': may_trail.get(row[5].strip(), 0)
        })

N = len(members)
total_fc = sum(m['fc'] for m in members)
print(f'CONS: {N}名  総固定休日数: {total_fc}')

# ── 各日の「動かせない休み」人数 ─────────────────────────
nf_off = [0]*30
for m in members:
    for d, s in enumerate(m['shifts']):
        if s in {KIBOU,PAID} or (not is_work(s) and s != FIXED):
            nf_off[d] += 1

# CONSの稼働可能残数（固定休割り当てで減らしていく）
cons_remain = [N - nf_off[d] for d in range(30)]

LOW = 70     # combined SE+CONS の最低保証ライン
LOW_W = 35   # ライン割れペナルティ重み（連勤より低く・週休より低く）

# ── スコア関数（5月跨ぎ連勤考慮） ───────────────────────
def score_fn(shifts, trailing, day_place=None):
    val = 0
    cur = trailing
    for i, v in enumerate(shifts):
        if is_work(v):
            cur += 1
            if   cur > 6: val += 1000
            elif cur == 6: val += 10
            elif cur >= 5: val += 2
        else:
            cur = 0
    for w in WEEKS:
        r = sum(1 for i in w if i<30 and shifts[i] in REST)
        if r < 2: val += (2 - r) * 100

    # combined staffing penalty
    if day_place is not None:
        combined_after = se_cnt[day_place] + cons_remain[day_place] - 1
        shortfall = max(0, LOW - combined_after)
        val += shortfall * LOW_W

    return val

# ── メンバー処理順: trailing大 → fc小 の順で（制約きつい人優先）
members_sorted = sorted(members, key=lambda m: (-m['trailing'], m['fc']))

# new シフトを辞書で管理
new_shifts_map = {}

for m in members_sorted:
    name = m['name']
    if m['fc'] == 0:
        new_shifts_map[name] = list(m['shifts'])
        continue

    mv = [i for i in range(30)
          if m['shifts'][i] not in {KIBOU,PAID} and m['shifts'][i].strip()!='']

    cur = list(m['shifts'])
    for i in mv: cur[i] = m['dft']   # 全可動日を勤務にリセット

    for _ in range(m['fc']):
        best_i, best_s = None, float('inf')
        for i in mv:
            if cur[i] == FIXED: continue
            test = list(cur); test[i] = FIXED
            s = score_fn(test, m['trailing'], day_place=i)
            if s < best_s: best_s=s; best_i=i

        if best_i is None:
            # フォールバック: combined余裕が最大の日
            cands = [i for i in mv if cur[i]!=FIXED]
            if cands:
                best_i = max(cands, key=lambda i: se_cnt[i]+cons_remain[i]-1)

        if best_i is not None:
            cur[best_i] = FIXED
            cons_remain[best_i] -= 1

    new_shifts_map[name] = cur

# ── 日別稼働人数集計 ──────────────────────────────────────
print()
print('='*60)
print(f'{"日付":^10} {"曜":^3} {"SE":>5} {"CONS":>5} {"合計":>6}  判定')
print('-'*60)

combined_list = []
for d in range(30):
    c = sum(1 for m in members if is_work(new_shifts_map[m['name']][d]))
    tot = se_cnt[d] + c
    combined_list.append(tot)
    flag = '🔴 少ない' if tot < LOW else ('🟡 やや少' if tot < LOW+5 else '')
    print(f'6/{d+1:2d}({DOW[d%7]}) {se_cnt[d]:5d} {c:5d} {tot:6d}  {flag}')

avg = statistics.mean(combined_list)
mn  = min(combined_list)
print(f'\n平均={avg:.1f}  最小={mn}  LOW閾値={LOW}')

# ── 個人別制約チェック ────────────────────────────────────
print()
print('='*60)
print('【個人別制約チェック（連勤・週休・5月跨ぎ）】')
any_issue = False
for m in members:
    ns   = new_shifts_map[m['name']]
    iss  = []
    cur2 = m['trailing']
    for i, v in enumerate(ns):
        if is_work(v): cur2 += 1
        else:
            if cur2 >= 7: iss.append(f'{cur2}連勤(〜6/{i})')
            cur2 = 0
    if cur2 >= 7: iss.append(f'{cur2}連勤(〜6/30)')
    for wi, w in enumerate(WEEKS, 1):
        r = sum(1 for i in w if i<30 and ns[i] in REST)
        if r < 2: iss.append(f'W{wi}休{r}日')
    if iss:
        any_issue = True
        print(f'  ⚠️  {m["name"]}（5末{m["trailing"]}日）: {", ".join(iss)}')
if not any_issue:
    print('  ✅ 全員クリア！')

# 固定休日0で変更不可メンバー
print()
zero_fc = [m['name'] for m in members if m['fc']==0]
if zero_fc:
    print(f'固定休日ゼロ（変更不可）: {", ".join(zero_fc)}')

# ── スプレッドシートへ書き込み ────────────────────────────
print()
batch = []
for m in members:
    ns = new_shifts_map[m['name']]
    if ns != m['shifts']:
        batch.append({'range': f'G{m["ri"]+1}:AJ{m["ri"]+1}', 'values': [ns]})

print(f'更新対象: {len(batch)}名')
if batch:
    ws6.batch_update(batch, value_input_option='RAW')
    print('✅ スプレッドシートへの書き込み完了！')
else:
    print('変更なし')
