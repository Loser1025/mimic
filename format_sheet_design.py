import gspread
from google.oauth2.service_account import Credentials

scopes = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
creds = Credentials.from_service_account_file('csv-to-sheet/sa_credentials.json', scopes=scopes)
gc = gspread.authorize(creds)

sh = gc.open_by_key('13cK3BhIxFot0cZilbDHa4dzZoH_tocmNYWEk-pTnkJo')
ws = sh.worksheet('保留')

def rgb(hex_color):
    h = hex_color.lstrip('#')
    return {
        'red':   int(h[0:2], 16) / 255,
        'green': int(h[2:4], 16) / 255,
        'blue':  int(h[4:6], 16) / 255,
    }

def fmt(bg=None, fg=None, bold=False, size=None, align=None, wrap=None):
    f = {}
    if bg:
        f['backgroundColor'] = rgb(bg)
    tf = {}
    if fg:
        tf['foregroundColor'] = rgb(fg)
    if bold:
        tf['bold'] = True
    if size:
        tf['fontSize'] = size
    if tf:
        f['textFormat'] = tf
    if align:
        f['horizontalAlignment'] = align
    if wrap:
        f['wrapStrategy'] = wrap
    return f

# ── セクションカラー定義 ──────────────────────────────────────
# 響単独    : Blue
# イージス  : Orange
# サンク    : Green
# 穂        : Purple
# つちクレ  : Rose/Pink

SECTION = {
    'hibiki':  {'header': '#1565C0', 'mid': '#BBDEFB', 'light': '#E3F2FD', 'text': '#0D47A1', 'range': 'A', 'end': 'F'},
    'aegis':   {'header': '#E65100', 'mid': '#FFE0B2', 'light': '#FFF3E0', 'text': '#BF360C', 'range': 'G', 'end': 'L'},
    'sank':    {'header': '#2E7D32', 'mid': '#C8E6C9', 'light': '#E8F5E9', 'text': '#1B5E20', 'range': 'M', 'end': 'R'},
    'ho':      {'header': '#6A1B9A', 'mid': '#E1BEE7', 'light': '#F3E5F5', 'text': '#4A148C', 'range': 'S', 'end': 'T'},
    'tsuchi':  {'header': '#AD1457', 'mid': '#F8BBD0', 'light': '#FCE4D6', 'text': '#880E4F', 'range': 'U', 'end': 'V'},
}

def sr(s, row):
    return f"{SECTION[s]['range']}{row}:{SECTION[s]['end']}{row}"

batch = []

# ── 全体リセット（白ベース） ───────────────────────────────────
batch.append({'range': 'A1:V28', 'format': fmt(bg='#FFFFFF', fg='#212121')})

# ── Row 1: 日付行 ─────────────────────────────────────────────
batch.append({'range': 'A1:V1', 'format': fmt(bg='#ECEFF1', fg='#546E7A', bold=True)})

# ── Row 2: タイトル行 ─────────────────────────────────────────
batch.append({'range': 'A2:T2', 'format': fmt(bg='#1A237E', fg='#FFFFFF', bold=True, size=11)})
# V2: ユニット保留ライフ（絵文字つき）
batch.append({'range': 'V2', 'format': fmt(bg='#E8EAF6', fg='#1A237E', size=9, wrap='WRAP')})

# ── Row 4: ALLセクションヘッダー ──────────────────────────────
batch.append({'range': 'A4:V4', 'format': fmt(bg='#263238', fg='#FFFFFF', bold=True)})

# ── Rows 5-7: ALL統計 ─────────────────────────────────────────
batch.append({'range': 'A5:A7', 'format': fmt(bg='#DEEBF7', fg='#1F3864', bold=True)})
batch.append({'range': 'B5:B7', 'format': fmt(bg='#DEEBF7', fg='#1F3864', bold=True)})

# ── Row 8: 空行（区切り） ─────────────────────────────────────
batch.append({'range': 'A8:V8', 'format': fmt(bg='#F5F5F5')})

# ── Row 9: 各拠点ヘッダー ─────────────────────────────────────
for s in SECTION:
    batch.append({'range': sr(s, 9), 'format': fmt(bg=SECTION[s]['header'], fg='#FFFFFF', bold=True, align='CENTER')})

# ── Rows 10-12: 各拠点 面談数/保留数/保留率 ───────────────────
for s in SECTION:
    start = SECTION[s]['range']
    end   = SECTION[s]['end']
    batch.append({'range': f"{start}10:{end}12", 'format': fmt(bg=SECTION[s]['light'], fg=SECTION[s]['text'], bold=True)})

# ── Row 13: 弁護士別件数 ──────────────────────────────────────
for s in SECTION:
    batch.append({'range': sr(s, 13), 'format': fmt(bg=SECTION[s]['mid'], fg=SECTION[s]['text'], bold=True)})

# ── Row 14: #N/A エラーセル ───────────────────────────────────
for s in ['aegis', 'sank', 'ho', 'tsuchi']:
    batch.append({'range': sr(s, 14), 'format': fmt(bg='#FFEBEE', fg='#C62828')})

# ── Rows 15-24: 空白エリア ────────────────────────────────────
batch.append({'range': 'A15:V24', 'format': fmt(bg='#FAFAFA')})

# ── Row 25: 保留・不受任一覧ヘッダー ─────────────────────────
for s in SECTION:
    batch.append({'range': sr(s, 25), 'format': fmt(bg='#F57F17', fg='#FFFFFF', bold=True)})

# ── Rows 26-27: 案件エントリー ────────────────────────────────
batch.append({'range': 'A26:V26', 'format': fmt(bg='#FFFDE7', fg='#4E342E')})
batch.append({'range': 'A27:V27', 'format': fmt(bg='#FFFDE7', fg='#4E342E')})

# ── 一括適用 ──────────────────────────────────────────────────
ws.batch_format(batch)
print(f'Applied {len(batch)} format rules. Done.')
