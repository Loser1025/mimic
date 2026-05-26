import gspread
from google.oauth2.service_account import Credentials

scopes = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
creds = Credentials.from_service_account_file('csv-to-sheet/sa_credentials.json', scopes=scopes)
gc = gspread.authorize(creds)

sh = gc.open_by_key('13cK3BhIxFot0cZilbDHa4dzZoH_tocmNYWEk-pTnkJo')
ws = sh.worksheet('保留')
sid = ws.id

# ─────────────────────────────────────────────
# Step 1: 全書式を完全リセット（userEnteredFormat を空に）
# ─────────────────────────────────────────────
sh.batch_update({'requests': [{
    'repeatCell': {
        'range': {
            'sheetId': sid,
            'startRowIndex': 0, 'endRowIndex': 50,
            'startColumnIndex': 0, 'endColumnIndex': 22,
        },
        'cell': {'userEnteredFormat': {}},
        'fields': 'userEnteredFormat'
    }
}]})
print('Reset done.')

# ─────────────────────────────────────────────
# ヘルパー
# ─────────────────────────────────────────────
def rgb(h):
    h = h.lstrip('#')
    return {'red': int(h[0:2],16)/255, 'green': int(h[2:4],16)/255, 'blue': int(h[4:6],16)/255}

def cell_fmt(bg=None, fg=None, bold=False, size=None, h_align=None, wrap=None, italic=False):
    uf = {}
    if bg:
        uf['backgroundColor'] = rgb(bg)
    tf = {}
    if fg:       tf['foregroundColor'] = rgb(fg)
    if bold:     tf['bold'] = True
    if italic:   tf['italic'] = True
    if size:     tf['fontSize'] = size
    if tf:       uf['textFormat'] = tf
    if h_align:  uf['horizontalAlignment'] = h_align
    if wrap:     uf['wrapStrategy'] = wrap
    return uf

def make_req(r1, c1, r2, c2, **kw):
    """repeatCell リクエストを生成 (r1,c1,r2,c2 は 0-indexed, endは exclusive)"""
    return {
        'repeatCell': {
            'range': {'sheetId': sid,
                      'startRowIndex': r1, 'endRowIndex': r2,
                      'startColumnIndex': c1, 'endColumnIndex': c2},
            'cell': {'userEnteredFormat': cell_fmt(**kw)},
            'fields': 'userEnteredFormat'
        }
    }

# ─────────────────────────────────────────────
# カラーパレット
# ─────────────────────────────────────────────
# 各拠点: (ヘッダー濃色, データ薄色, テキスト色)
SEC = {
    #        header      data-bg     text
    'hibiki':  ('#1565C0', '#E3F2FD', '#0D47A1'),  # 響単独  : Blue
    'aegis':   ('#E65100', '#FFF3E0', '#BF360C'),  # イージス: Orange
    'sank':    ('#2E7D32', '#E8F5E9', '#1B5E20'),  # サンク  : Green
    'ho':      ('#6A1B9A', '#F3E5F5', '#4A148C'),  # 穂      : Purple
    'tsuchi':  ('#AD1457', '#FCE4D6', '#880E4F'),  # つちクレ: Rose
}

# 列範囲 (0-indexed, exclusive)
COL = {
    'hibiki': (0,  6),   # A-F
    'aegis':  (6,  12),  # G-L
    'sank':   (12, 18),  # M-R
    'ho':     (18, 20),  # S-T
    'tsuchi': (20, 22),  # U-V
}

# ─────────────────────────────────────────────
# Step 2: 書式リクエストを組み立て
# ─────────────────────────────────────────────
reqs = []

# Row 1: 日付 — 薄いグレー
reqs.append(make_req(0,0, 1,22, bg='#ECEFF1', fg='#546E7A', bold=True))

# Row 2: メインタイトル (A-T) — 濃いネイビー + 白太字
reqs.append(make_req(1,0, 2,20, bg='#1A237E', fg='#FFFFFF', bold=True, size=11))
# V2: ユニットライフ欄 — 薄いラベンダー、小さめ
reqs.append(make_req(1,21, 2,22, bg='#E8EAF6', fg='#283593', size=9, wrap='WRAP'))

# Row 3: 空行 — 区切り用にごく薄いグレー
reqs.append(make_req(2,0, 3,22, bg='#F5F5F5'))

# Row 4: ALLヘッダー — ダークスレート
reqs.append(make_req(3,0, 4,22, bg='#37474F', fg='#FFFFFF', bold=True))

# Rows 5-7: ALL統計ラベル+値 — ごく薄いブルー
reqs.append(make_req(4,0, 7,2, bg='#E8F4FD', fg='#1A237E', bold=True))
# N5: 大きなレポートテキスト欄 (N列=13) — 薄いグレー
reqs.append(make_req(4,13, 5,14, bg='#F5F5F5', fg='#424242', size=9, wrap='WRAP'))
# M6: 報告用ラベル
reqs.append(make_req(5,12, 6,13, bg='#ECEFF1', fg='#37474F', bold=True))

# Row 8: 空行区切り
reqs.append(make_req(7,0, 8,22, bg='#F5F5F5'))

# Row 9: 各拠点ヘッダー — セクション色 + 白太字
for key, (hdr, _, _) in SEC.items():
    c1, c2 = COL[key]
    reqs.append(make_req(8, c1, 9, c2, bg=hdr, fg='#FFFFFF', bold=True, h_align='CENTER'))

# Rows 10-12: 各拠点 面談数/保留数/保留率
for key, (_, data_bg, text) in SEC.items():
    c1, c2 = COL[key]
    reqs.append(make_req(9, c1, 12, c2, bg=data_bg, fg=text, bold=True))

# Row 13: 弁護士別件数ヘッダー — 中間トーン（data_bgより少し濃く）
MID = {
    'hibiki':  '#BBDEFB',
    'aegis':   '#FFE0B2',
    'sank':    '#C8E6C9',
    'ho':      '#E1BEE7',
    'tsuchi':  '#F8BBD0',
}
for key, mid in MID.items():
    c1, c2 = COL[key]
    _, _, text = SEC[key]
    reqs.append(make_req(12, c1, 13, c2, bg=mid, fg=text, bold=True))

# Row 14: #N/A エラー行 — 各拠点の薄い色 + エラーテキスト
# hibiki は空なのでdata_bgのみ、他は#N/Aセルあり
for key, (_, data_bg, _) in SEC.items():
    c1, c2 = COL[key]
    reqs.append(make_req(13, c1, 14, c2, bg=data_bg, fg='#B71C1C'))

# Rows 15-24: 空白エリア — 各拠点のごく薄い色 (data_bgをそのまま使用)
for key, (_, data_bg, _) in SEC.items():
    c1, c2 = COL[key]
    reqs.append(make_req(14, c1, 24, c2, bg=data_bg))

# Row 25: 保留・不受任一覧ヘッダー — 各拠点のヘッダー色 + 白太字
for key, (hdr, _, _) in SEC.items():
    c1, c2 = COL[key]
    reqs.append(make_req(24, c1, 25, c2, bg=hdr, fg='#FFFFFF', bold=True))

# Row 26以降: 案件エントリー — 各拠点の薄い色 + 濃いテキスト（余裕を持って50行まで）
for key, (_, data_bg, text) in SEC.items():
    c1, c2 = COL[key]
    reqs.append(make_req(25, c1, 50, c2, bg=data_bg, fg=text))

# ─────────────────────────────────────────────
# Step 3: 一括送信
# ─────────────────────────────────────────────
sh.batch_update({'requests': reqs})
print(f'Design applied: {len(reqs)} rules. Done.')
