import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import gspread
from google.oauth2.service_account import Credentials

SCOPES = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
creds = Credentials.from_service_account_file(
    r'C:\Users\Loser\Desktop\-\tamalabo\automation-visitor-shindan\ageless-impulse-488713-m6-03014b3cddad.json',
    scopes=SCOPES
)
gc = gspread.authorize(creds)
sh = gc.open_by_key('1ODTZoW_6M9WbI0jwIc9vt_Y8crQ1sLHE57kZe4MGG2w')
ws = sh.worksheet('2026.6　※石井作成中')
data = ws.get_all_values()

FIXED = '固定休日'; KIBOU = '希望休日'; PAID = '有給休暇'
REST = {FIXED, KIBOU}

def is_work(s):
    return s.strip() != '' and s not in {FIXED, KIBOU, PAID}

# 6/1 = 月曜  →  day i の曜日 = i%7  (0=月…6=日)
DOW_NAME = ['月','火','水','木','金','土','日']
def get_dow(d): return d % 7

def target_workers(d):
    dow = get_dow(d)
    if dow <= 1:  return 32   # 月・火（多め）
    elif dow <= 4: return 30  # 水〜金
    else:          return 25  # 土・日

# ── CONSメンバー読み込み ──────────────────────────────
members = []
for ri, row in enumerate(data):
    if ri < 44: continue
    if len(row) <= 5: continue
    aff  = row[1].strip()
    name = row[5].strip()
    if not name or name == '氏名': continue
    if aff != 'CONS': continue
    raw = (list(row[6:36]) + ['']*30)[:30]
    wv  = [s for s in raw if is_work(s)]
    members.append({
        'ri':  ri,
        'name': name,
        'shifts': raw,
        'fc':  sum(1 for s in raw if s == FIXED),
        'dft': max(set(wv), key=wv.count) if wv else '9:00-18:00'
    })

N = len(members)
total_fixed = sum(m['fc'] for m in members)
print(f'CONSメンバー: {N}名  総固定休日数: {total_fixed}')

# ── 日別 固定以外の休み人数 ───────────────────────────
nf_off = [0]*30
for m in members:
    for d, s in enumerate(m['shifts']):
        if s in {KIBOU, PAID} or (not is_work(s) and s != FIXED):
            nf_off[d] += 1

# ── 日別 目標固定休日数 ──────────────────────────────
tgt_f = [max(0.0, N - target_workers(d) - nf_off[d]) for d in range(30)]
ttf = sum(tgt_f)
if ttf > 0:
    tgt_f = [x * total_fixed / ttf for x in tgt_f]   # スケール合わせ

print(f'\n日別 目標固定休日数（scaled）:')
for d in range(30):
    print(f'  6/{d+1:2d}({DOW_NAME[get_dow(d)]}) 目標稼働={target_workers(d)}  '
          f'nf_off={nf_off[d]}  tgt_fixed={tgt_f[d]:.1f}')

# ── スコア関数 ────────────────────────────────────────
WEEKS = [range(0,7), range(7,14), range(14,21), range(21,28)]

def ind_score(shifts):
    """個人制約のペナルティ"""
    s = 0; cur = 0
    for v in shifts:
        if is_work(v):
            cur += 1
            if   cur > 6: s += 1000   # 7連勤以上 NG
            elif cur == 6: s += 10    # 6連勤 注意
            elif cur == 5: s += 2     # 5連勤 軽微
        else:
            cur = 0
    for w in WEEKS:
        r = sum(1 for i in w if i < 30 and shifts[i] in REST)
        if r < 2: s += (2 - r) * 100  # 週2休不足
    return s

GW = 6.0   # グローバル重み（大きいほど人員配置優先）

# ── 最適化 ───────────────────────────────────────────
assigned = [0] * 30   # 各日に割り当て済み固定休日数

for m in members:
    if m['fc'] == 0:
        m['new'] = list(m['shifts'])
        continue

    # 動かせる日（希望休・有給・空欄以外）
    mv = [i for i in range(30)
          if m['shifts'][i] not in {KIBOU, PAID} and m['shifts'][i].strip() != '']

    # ベース：全可動日を勤務にリセット
    cur = list(m['shifts'])
    for i in mv: cur[i] = m['dft']

    for _ in range(m['fc']):
        best_i, best_s = None, float('inf')
        for i in mv:
            if cur[i] == FIXED: continue
            test = list(cur); test[i] = FIXED
            # 個人スコア + グローバル（目標余裕が多い日ほど有利）
            need = tgt_f[i] - assigned[i]
            s = ind_score(test) - need * GW
            if s < best_s:
                best_s = s; best_i = i

        if best_i is None:
            # フォールバック：需要が最も多い日に置く
            cands = [i for i in mv if cur[i] != FIXED]
            if cands:
                best_i = max(cands, key=lambda i: tgt_f[i] - assigned[i])

        if best_i is not None:
            cur[best_i] = FIXED
            assigned[best_i] += 1

    m['new'] = cur

# ── 結果集計 ─────────────────────────────────────────
print('\n' + '='*55)
print('【最適化後 日別配置人数】')
print(f'{"日付":^10} {"曜":^3} {"目標":>5} {"実人数":>6} {"差":>5}')
print('-'*40)

ok_days = 0
for d in range(30):
    act  = sum(1 for m in members if is_work(m['new'][d]))
    tgt  = target_workers(d)
    diff = act - tgt
    flag = '  ⚠️' if abs(diff) > 3 else ''
    if abs(diff) <= 3: ok_days += 1
    print(f'6/{d+1:2d}({DOW_NAME[get_dow(d)]}) {tgt:5d} {act:6d} {diff:+5d}{flag}')

print(f'\n目標±3以内の日: {ok_days}/30日')

# ── 個人チェック ─────────────────────────────────────
print('\n' + '='*55)
print('【個人別 制約チェック（新シフト）】')
issues_found = False
for m in members:
    iss = []
    cur2 = 0; st = None
    for i, v in enumerate(m['new']):
        if is_work(v):
            if cur2 == 0: st = i
            cur2 += 1
        else:
            if cur2 >= 7: iss.append(f'{cur2}連勤(6/{st+1}〜6/{i})')
            cur2 = 0
    if cur2 >= 7: iss.append(f'{cur2}連勤(6/{st+1}〜6/30)')

    for wi, w in enumerate(WEEKS, 1):
        r = sum(1 for i in w if i < 30 and m['new'][i] in REST)
        if r < 2: iss.append(f'W{wi}休み{r}日')

    if iss:
        issues_found = True
        print(f'  ⚠️  {m["name"]}: {", ".join(iss)}')

if not issues_found:
    print('  ✅ 全員クリア！')

# 固定休日が0で問題が残るメンバー
print('\n【固定休日ゼロで変更不可のメンバー】')
for m in members:
    if m['fc'] == 0:
        print(f'  ⚪ {m["name"]}: 固定休日0個（元のまま）')

# ── スプレッドシートへ書き込み ────────────────────────
print('\n' + '='*55)
batch = []
for m in members:
    if m['new'] != m['shifts']:
        batch.append({
            'range':  f'G{m["ri"]+1}:AJ{m["ri"]+1}',
            'values': [m['new']]
        })

print(f'更新対象: {len(batch)}名')
if batch:
    ws.batch_update(batch, value_input_option='RAW')
    print('✅ スプレッドシートへの書き込み完了！')
else:
    print('変更なし')
