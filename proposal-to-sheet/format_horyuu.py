import os
from google.oauth2 import service_account
from googleapiclient.discovery import build
from pathlib import Path

# GitHub Actions: 環境変数、ローカル: SAファイル
_CLIENT_EMAIL = os.environ.get('GOOGLE_CLIENT_EMAIL')
_PRIVATE_KEY  = os.environ.get('GOOGLE_PRIVATE_KEY')

if _CLIENT_EMAIL and _PRIVATE_KEY:
    creds = service_account.Credentials.from_service_account_info(
        {'type': 'service_account', 'client_email': _CLIENT_EMAIL,
         'private_key': _PRIVATE_KEY.replace('\\n', '\n'),
         'token_uri': 'https://oauth2.googleapis.com/token'},
        scopes=['https://www.googleapis.com/auth/spreadsheets'])
else:
    SA_PATH = Path(__file__).parent.parent / 'csv-to-sheet' / 'sa_credentials.json'
    creds = service_account.Credentials.from_service_account_file(
        str(SA_PATH), scopes=['https://www.googleapis.com/auth/spreadsheets'])

service = build('sheets', 'v4', credentials=creds)

SS_ID = '13cK3BhIxFot0cZilbDHa4dzZoH_tocmNYWEk-pTnkJo'
SID = 0

# 列定義 (0始まり)
# A-B: 響単, C-F: spacer, G-H: イージス, I-L: spacer
# M-N: サンク, O-R: spacer, S-T: 穂
SECTIONS = [
    {'label': 0, 'val': 1, 'sp_start': 2,  'sp_end': 6},   # 響単
    {'label': 6, 'val': 7, 'sp_start': 8,  'sp_end': 12},  # イージス
    {'label': 12,'val': 13,'sp_start': 14, 'sp_end': 18},  # サンク
    {'label': 18,'val': 19,'sp_start': None,'sp_end': None},# 穂（最後）
]
TOTAL_COLS = 20  # A-T

def rgb(r, g, b): return {'red': r/255, 'green': g/255, 'blue': b/255}

def rng(r1, c1, r2, c2):
    return {'sheetId': SID, 'startRowIndex': r1, 'endRowIndex': r2,
            'startColumnIndex': c1, 'endColumnIndex': c2}

def cell(r1, c1, r2, c2, f):
    return {'repeatCell': {'range': rng(r1, c1, r2, c2),
            'cell': {'userEnteredFormat': f}, 'fields': 'userEnteredFormat'}}

def merge(r1, c1, r2, c2):
    return {'mergeCells': {'range': rng(r1, c1, r2, c2), 'mergeType': 'MERGE_ALL'}}

def row_h(r, px):
    return {'updateDimensionProperties': {
        'range': {'sheetId': SID, 'dimension': 'ROWS', 'startIndex': r, 'endIndex': r+1},
        'properties': {'pixelSize': px}, 'fields': 'pixelSize'}}

def col_w(c, px):
    return {'updateDimensionProperties': {
        'range': {'sheetId': SID, 'dimension': 'COLUMNS', 'startIndex': c, 'endIndex': c+1},
        'properties': {'pixelSize': px}, 'fields': 'pixelSize'}}

def border(r1, c1, r2, c2, left=None, bottom=None, top=None, right=None):
    b = {'range': rng(r1, c1, r2, c2)}
    if left:   b['left']   = left
    if right:  b['right']  = right
    if top:    b['top']    = top
    if bottom: b['bottom'] = bottom
    return {'updateBorders': b}

def fmt(bg=None, fg=None, size=10, bold=False, align='LEFT',
        italic=False, valign='MIDDLE', wrap='OVERFLOW_CELL'):
    f = {'verticalAlignment': valign, 'horizontalAlignment': align,
         'wrapStrategy': wrap,
         'textFormat': {'bold': bold, 'fontSize': size, 'italic': italic}}
    if bg: f['backgroundColor'] = bg
    if fg: f['textFormat']['foregroundColor'] = fg
    return f

THICK  = lambda c: {'style': 'SOLID_THICK',  'color': c}
THIN   = lambda c: {'style': 'SOLID',        'color': c}
MEDIUM = lambda c: {'style': 'SOLID_MEDIUM', 'color': c}

# カラーパレット
WHITE   = rgb(255, 255, 255)
DARK    = rgb(30,  30,  30)
NAVY    = rgb(15,  23,  42)
NAVY_L  = rgb(30,  41,  59)
INDIGO  = rgb(55,  48,  163)
INDIGO_L= rgb(238, 242, 255)
INDIGO_B= rgb(165, 180, 252)
SEP     = rgb(226, 232, 240)
GRAY_BG = rgb(248, 250, 252)

# 各セクションカラー: [header, light_bg, border, text, list_stripe]
COLORS = [
    # 響単 (ブルー)
    {'h': rgb(29, 78, 216),  'l': rgb(239, 246, 255), 'b': rgb(147, 197, 253),
     't': rgb(30, 64, 175),  's': rgb(219, 234, 254)},
    # イージス (ティール)
    {'h': rgb(15, 118, 110), 'l': rgb(240, 253, 250), 'b': rgb(94, 234, 212),
     't': rgb(19, 78, 74),   's': rgb(204, 251, 241)},
    # サンク (アンバー)
    {'h': rgb(180, 83, 9),   'l': rgb(255, 251, 235), 'b': rgb(253, 211, 77),
     't': rgb(146, 64, 14),  's': rgb(254, 243, 199)},
    # 穂 (ローズ)
    {'h': rgb(157, 23, 77),  'l': rgb(255, 241, 242), 'b': rgb(251, 164, 186),
     't': rgb(136, 19, 55),  's': rgb(255, 228, 230)},
]

reqs = []

# 列幅
col_widths = {0: 220, 1: 68}  # 各セクションのlabel/val列
for s in SECTIONS:
    reqs.append(col_w(s['label'], 220))
    reqs.append(col_w(s['val'],   68))
    if s['sp_start'] is not None:
        for c in range(s['sp_start'], s['sp_end']):
            reqs.append(col_w(c, 14))

# 行高
for r, h in {0: 22, 1: 42, 2: 6, 3: 34, 4: 28, 5: 28, 6: 28,
             7: 6, 8: 34, 9: 28, 10: 28, 11: 28, 12: 8,
             13: 28, 14: 28, 15: 6, 16: 6, 17: 32}.items():
    reqs.append(row_h(r, h))
for r in range(18, 40):
    reqs.append(row_h(r, 26))

# ベースクリア
reqs.append(cell(0, 0, 50, TOTAL_COLS, fmt(bg=WHITE, fg=DARK, size=10)))

# ── Row 0: 日付 ───────────────────────────────────────
reqs.append(cell(0, 0, 1, TOTAL_COLS,
    fmt(bg=GRAY_BG, fg=rgb(100, 116, 139), size=9, italic=True)))

# ── Row 1: タイトル ───────────────────────────────────
reqs.append(merge(1, 0, 2, TOTAL_COLS))
reqs.append(cell(1, 0, 2, TOTAL_COLS,
    fmt(bg=NAVY, fg=WHITE, size=13, bold=True, align='CENTER')))

# ── Row 2: ネイビーバー ───────────────────────────────
reqs.append(cell(2, 0, 3, TOTAL_COLS, fmt(bg=NAVY_L)))

# ── Row 3: ALL ヘッダー ───────────────────────────────
reqs.append(merge(3, 0, 4, TOTAL_COLS))
reqs.append(cell(3, 0, 4, TOTAL_COLS,
    fmt(bg=INDIGO, fg=WHITE, size=11, bold=True, align='CENTER')))

# ── Rows 4-6: ALL stats ───────────────────────────────
reqs.append(cell(4, 0, 7, 1,
    fmt(bg=INDIGO_L, fg=rgb(30, 64, 175), size=10, bold=True)))
reqs.append(cell(4, 1, 7, 2,
    fmt(bg=INDIGO_L, fg=rgb(30, 64, 175), size=10, bold=True, align='RIGHT')))
reqs.append(cell(4, 2, 7, TOTAL_COLS, fmt(bg=INDIGO_L)))
reqs.append(border(4, 0, 7, 2, left=THICK(INDIGO), bottom=THIN(INDIGO_B)))

# ── Row 7: セパレーター ───────────────────────────────
reqs.append(cell(7, 0, 8, TOTAL_COLS, fmt(bg=INDIGO)))

# ── Row 8: 各セクション ヘッダー ─────────────────────
for i, (s, c) in enumerate(zip(SECTIONS, COLORS)):
    reqs.append(merge(8, s['label'], 9, s['val'] + 1))
    reqs.append(cell(8, s['label'], 9, s['val'] + 1,
        fmt(bg=c['h'], fg=WHITE, size=11, bold=True, align='CENTER')))
    if s['sp_start']:
        reqs.append(cell(8, s['sp_start'], 9, s['sp_end'], fmt(bg=SEP)))

# ── Rows 9-11: 各セクション stats ────────────────────
for s, c in zip(SECTIONS, COLORS):
    L, V = s['label'], s['val']
    reqs.append(cell(9, L, 12, L+1, fmt(bg=c['l'], fg=c['t'], size=10, bold=True)))
    reqs.append(cell(9, V, 12, V+1, fmt(bg=c['l'], fg=c['t'], size=10, bold=True, align='RIGHT')))
    reqs.append(border(9, L, 12, V+1, left=THICK(c['h']), bottom=THIN(c['b'])))
    if s['sp_start']:
        reqs.append(cell(9, s['sp_start'], 12, s['sp_end'], fmt(bg=WHITE)))

# ── Row 12: スペーサー ────────────────────────────────
reqs.append(cell(12, 0, 13, TOTAL_COLS, fmt(bg=WHITE)))

# ── Row 13: 担当拠点管轄 ─────────────────────────────
for s, c in zip(SECTIONS, COLORS):
    L, V = s['label'], s['val']
    reqs.append(merge(13, L, 14, V+1))
    reqs.append(cell(13, L, 14, V+1,
        fmt(bg=c['h'], fg=WHITE, size=10, bold=True, align='CENTER')))
    if s['sp_start']:
        reqs.append(cell(13, s['sp_start'], 14, s['sp_end'], fmt(bg=SEP)))

# ── Row 14: 担当値 ────────────────────────────────────
for s, c in zip(SECTIONS, COLORS):
    L, V = s['label'], s['val']
    reqs.append(cell(14, L, 15, V+1, fmt(bg=c['l'], fg=c['t'], size=9)))
    if s['sp_start']:
        reqs.append(cell(14, s['sp_start'], 15, s['sp_end'], fmt(bg=WHITE)))

# ── Rows 15-16: スペーサー ───────────────────────────
reqs.append(cell(15, 0, 17, TOTAL_COLS, fmt(bg=WHITE)))

# ── Row 17: 保留・不在一覧 ヘッダー ──────────────────
for s, c in zip(SECTIONS, COLORS):
    L, V = s['label'], s['val']
    reqs.append(merge(17, L, 18, V+1))
    reqs.append(cell(17, L, 18, V+1,
        fmt(bg=c['h'], fg=WHITE, size=11, bold=True, align='CENTER')))
    reqs.append(border(17, L, 18, V+1, top=MEDIUM(c['h']), left=THICK(c['h'])))
    if s['sp_start']:
        reqs.append(cell(17, s['sp_start'], 18, s['sp_end'], fmt(bg=SEP)))

# ── Rows 18+: リスト（交互色） ───────────────────────
for i in range(22):
    r = 18 + i
    for s, c in zip(SECTIONS, COLORS):
        L, V = s['label'], s['val']
        bg_c = WHITE if i % 2 == 0 else c['s']
        reqs.append(cell(r, L, r+1, V+1, fmt(bg=bg_c, fg=DARK, size=9, wrap='CLIP')))
        reqs.append(border(r, L, r+1, V+1, bottom=THIN(c['b'])))
        if s['sp_start']:
            reqs.append(cell(r, s['sp_start'], r+1, s['sp_end'], fmt(bg=WHITE)))

# ── 外枠 ─────────────────────────────────────────────
reqs.append(border(1, 0, 2, TOTAL_COLS, top=THICK(NAVY)))

service.spreadsheets().batchUpdate(
    spreadsheetId=SS_ID, body={'requests': reqs}).execute()
print("フォーマット適用完了！（響単・イージス・サンク・穂）")
