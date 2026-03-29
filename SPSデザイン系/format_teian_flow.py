from google.oauth2 import service_account
from googleapiclient.discovery import build

SA_KEY = 'C:/Users/弁護士法人響/Downloads/ageless-impulse-488713-m6-0c52b81add54.json'
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
creds = service_account.Credentials.from_service_account_file(SA_KEY, scopes=SCOPES)
service = build('sheets', 'v4', credentials=creds)

SS_ID = '1uwuYAu-4320uPrACJFf6VwzRl_M6k-RtOl9oKCREF38'
SID   = 1260667735

def rgb(r, g, b):
    return {'red': r/255, 'green': g/255, 'blue': b/255}

# ── カラーパレット ──────────────────────────────
HDR_FLOW   = rgb( 27,  58, 107)   # #1B3A6B ダークネイビー（フローヘッダ）
HDR_TOOL   = rgb(180,  70,   0)   # #B44600 ダークオレンジ（ツールヘッダ）
SEC_HDR    = rgb( 40,  85, 145)   # #285591 セクションヘッダ
SUBSEC_HDR = rgb( 65, 110, 180)   # #416EB4 サブセクションヘッダ
STEP_A     = rgb(232, 242, 252)   # #E8F2FC 薄いブルーA
STEP_B     = rgb(210, 228, 246)   # #D2E4F6 薄いブルーB
COND_BG    = rgb(255, 248, 225)   # #FFF8E1 条件分岐（黄み）
NOTE_BG    = rgb(238, 244, 250)   # #EEF4FA ノート行（薄グレブル）
TOOL_BG    = rgb(255, 245, 235)   # #FFF5EB 薄オレンジ（ツール列）
GAP_BG     = rgb(248, 250, 252)   # #F8FAFC 空白行（極薄）
WHITE      = rgb(255, 255, 255)
DARK       = rgb( 25,  25,  45)   # ほぼ黒（本文）
ARROW_FG   = rgb( 65, 110, 180)   # #416EB4 矢印色
TOOL_FG    = rgb( 80,  50,  20)   # ダークブラウン（ツールテキスト）

requests = []

# ── 1. シートプロパティ：グリッド非表示 / ヘッダ固定 ───────────────
requests.append({
    'updateSheetProperties': {
        'properties': {
            'sheetId': SID,
            'gridProperties': {'frozenRowCount': 3, 'hideGridlines': True}
        },
        'fields': 'gridProperties.frozenRowCount,gridProperties.hideGridlines'
    }
})

# ── 2. 列幅 ────────────────────────────────────────────
col_widths = [
    (0,  1, 400),  # A  : フロー本文（広め）
    (1,  4,  12),  # B-D: 結合ヘッダの一部なので極薄
    (4,  8,  14),  # E-H: フロー列とツール列の間隔
    (8,  9, 360),  # I  : ツール本文（広め）
    (9, 12, 160),  # J-L: 追加ツール情報
    (12, 26,  50), # M- : 使わない列
]
for sc, ec, w in col_widths:
    requests.append({
        'updateDimensionProperties': {
            'range': {'sheetId': SID, 'dimension': 'COLUMNS', 'startIndex': sc, 'endIndex': ec},
            'properties': {'pixelSize': w},
            'fields': 'pixelSize'
        }
    })

# ── ヘルパー：範囲に書式を一括設定 ──────────────────────────────
def fmt(sr, er, sc, ec, bg, bold=False, fg=None, fs=None, ha=None, va='MIDDLE', wrap='WRAP'):
    if fg is None:
        fg = DARK
    tf = {'bold': bold, 'foregroundColor': fg}
    if fs:
        tf['fontSize'] = fs
    cell_fmt = {
        'backgroundColor': bg,
        'textFormat': tf,
        'verticalAlignment': va,
        'wrapStrategy': wrap,
        'padding': {'top': 4, 'right': 10, 'bottom': 4, 'left': 10},
    }
    if ha:
        cell_fmt['horizontalAlignment'] = ha
    fields = (
        'userEnteredFormat.backgroundColor,'
        'userEnteredFormat.textFormat.bold,'
        'userEnteredFormat.textFormat.foregroundColor,'
        'userEnteredFormat.textFormat.fontSize,'
        'userEnteredFormat.verticalAlignment,'
        'userEnteredFormat.wrapStrategy,'
        'userEnteredFormat.padding'
    )
    if ha:
        fields += ',userEnteredFormat.horizontalAlignment'
    return {
        'repeatCell': {
            'range': {'sheetId': SID, 'startRowIndex': sr, 'endRowIndex': er,
                      'startColumnIndex': sc, 'endColumnIndex': ec},
            'cell': {'userEnteredFormat': cell_fmt},
            'fields': fields
        }
    }

def border_box(sr, er, sc, ec, outer_color, inner_color=None, outer_w=2):
    if inner_color is None:
        inner_color = rgb(210, 220, 235)
    outer = {'style': 'SOLID', 'width': outer_w, 'color': outer_color}
    inner = {'style': 'SOLID', 'width': 1,       'color': inner_color}
    return {
        'updateBorders': {
            'range': {'sheetId': SID, 'startRowIndex': sr, 'endRowIndex': er,
                      'startColumnIndex': sc, 'endColumnIndex': ec},
            'top': outer, 'bottom': outer, 'left': outer, 'right': outer,
            'innerHorizontal': inner, 'innerVertical': {'style': 'NONE'},
        }
    }

# ── 3. ベースリセット（全体白地、フォント10pt）─────────────────
requests.append(fmt(0, 120, 0, 26, WHITE, fg=DARK, fs=10, wrap='WRAP'))

# ── 4. ヘッダ行（rows 0-2）──────────────────────────────
requests.append(fmt(0, 3, 0, 8,  HDR_FLOW, bold=True, fg=WHITE, fs=13, ha='CENTER'))
requests.append(fmt(0, 3, 8, 14, HDR_TOOL, bold=True, fg=WHITE, fs=13, ha='CENTER'))

# ── 5. セクションヘッダ ─────────────────────────────────
#  ①直繋ぎ (index 3)
requests.append(fmt(3, 4, 0, 8,  SEC_HDR, bold=True, fg=WHITE, fs=11, ha='LEFT'))
requests.append(fmt(3, 4, 8, 14, TOOL_BG, bold=True, fg=TOOL_FG, fs=9))
#  ②既存面談 (index 24)
requests.append(fmt(24, 25, 0, 8,  SEC_HDR, bold=True, fg=WHITE, fs=11, ha='LEFT'))
requests.append(fmt(24, 25, 8, 14, TOOL_BG, bold=True, fg=TOOL_FG, fs=9))
#  ▼受任時 (index 50)
requests.append(fmt(50, 51, 0, 14, SUBSEC_HDR, bold=True, fg=WHITE, fs=11, ha='LEFT'))
#  ▼検討・リリース時 (index 69)
requests.append(fmt(69, 70, 0, 14, SUBSEC_HDR, bold=True, fg=WHITE, fs=11, ha='LEFT'))

# ── 6. ①直繋ぎ フローステップ (rows 4-21) ──────────────────
ARROW_ROWS_1 = {6, 8, 10, 12, 14, 16, 18, 20}
step_idx = 0
for i in range(4, 22):
    if i in ARROW_ROWS_1:
        requests.append(fmt(i, i+1, 0, 8,  WHITE,   fg=ARROW_FG, fs=14, ha='CENTER', wrap='OVERFLOW_CELL'))
    elif i == 21:  # 最終ノート
        requests.append(fmt(i, i+1, 0, 8,  NOTE_BG, fg=DARK, fs=9))
    else:
        bg = STEP_A if step_idx % 2 == 0 else STEP_B
        requests.append(fmt(i, i+1, 0, 8,  bg, fg=DARK, fs=10))
        step_idx += 1
    requests.append(fmt(i, i+1, 8, 14, TOOL_BG, fg=TOOL_FG, fs=9))

# ── 7. ②既存面談 フローステップ (rows 25-28) ───────────────
for i in range(25, 29):
    if i == 26:
        requests.append(fmt(i, i+1, 0, 8,  WHITE,  fg=ARROW_FG, fs=14, ha='CENTER', wrap='OVERFLOW_CELL'))
    else:
        bg = STEP_A if i % 2 == 0 else STEP_B
        requests.append(fmt(i, i+1, 0, 8,  bg,     fg=DARK, fs=10))
    requests.append(fmt(i, i+1, 8, 14, TOOL_BG, fg=TOOL_FG, fs=9))

# ── 8. 空白行（22-23, 28-49）───────────────────────────
requests.append(fmt(22, 24, 0, 26, GAP_BG, fg=DARK))
requests.append(fmt(28, 50, 0, 26, GAP_BG, fg=DARK))

# ── 9. ▼受任時 フローステップ (rows 51-76) ──────────────────
ARROW_ROWS_2 = {52, 54, 57, 59, 71, 73}
COND_ROWS    = {60, 64}
NOTE_ROWS    = {56, 62, 66}
step_idx2 = 0
for i in range(51, 77):
    if i in ARROW_ROWS_2:
        requests.append(fmt(i, i+1, 0, 8,  WHITE,   fg=ARROW_FG, fs=14, ha='CENTER', wrap='OVERFLOW_CELL'))
    elif i in COND_ROWS:
        requests.append(fmt(i, i+1, 0, 8,  COND_BG, bold=True, fg=rgb(120, 70, 0), fs=10))
    elif i in NOTE_ROWS:
        requests.append(fmt(i, i+1, 0, 8,  NOTE_BG, fg=DARK, fs=9))
    elif i == 69:   # subsec header — 上で設定済み
        pass
    else:
        bg = STEP_A if step_idx2 % 2 == 0 else STEP_B
        requests.append(fmt(i, i+1, 0, 8,  bg,      fg=DARK, fs=10))
        step_idx2 += 1
    requests.append(fmt(i, i+1, 8, 14, TOOL_BG, fg=TOOL_FG, fs=9))

# ── 10. フォーム記入欄（77行目以降）────────────────────────
requests.append(fmt(77, 116, 0,  8, GAP_BG, fg=DARK))
requests.append(fmt(77, 116, 8, 14, TOOL_BG, fg=TOOL_FG, fs=9))

# ── 11. 行の高さ ─────────────────────────────────────
def row_h(si, ei, h):
    return {
        'updateDimensionProperties': {
            'range': {'sheetId': SID, 'dimension': 'ROWS', 'startIndex': si, 'endIndex': ei},
            'properties': {'pixelSize': h},
            'fields': 'pixelSize'
        }
    }

requests.append(row_h(0,   120, 34))   # ベース全体 34px
requests.append(row_h(0,   3,   56))   # ヘッダ 56px
requests.append(row_h(3,   4,   42))   # ①直繋ぎ
requests.append(row_h(24,  25,  42))   # ②既存面談
requests.append(row_h(50,  51,  42))   # ▼受任時
requests.append(row_h(69,  70,  42))   # ▼検討・リリース時
# 矢印行は小さく
for ri in list(ARROW_ROWS_1) + list(ARROW_ROWS_2):
    requests.append(row_h(ri, ri+1, 22))

# ── 12. ボーダー ─────────────────────────────────────
# ①直繋ぎ フロー列
requests.append(border_box(3, 22, 0, 8,
    outer_color=rgb(40, 85, 145),
    inner_color=rgb(195, 215, 238)))
# ①直繋ぎ ツール列
requests.append(border_box(3, 22, 8, 14,
    outer_color=rgb(180, 70, 0),
    inner_color=rgb(230, 200, 175)))
# ②既存面談
requests.append(border_box(24, 29, 0, 8,
    outer_color=rgb(40, 85, 145),
    inner_color=rgb(195, 215, 238)))
requests.append(border_box(24, 29, 8, 14,
    outer_color=rgb(180, 70, 0),
    inner_color=rgb(230, 200, 175)))
# ▼受任時（50-76 フロー列）
requests.append(border_box(50, 69, 0, 8,
    outer_color=rgb(65, 110, 180),
    inner_color=rgb(200, 218, 240)))
requests.append(border_box(50, 69, 8, 14,
    outer_color=rgb(180, 70, 0),
    inner_color=rgb(230, 200, 175)))
# ▼検討・リリース時（69-77）
requests.append(border_box(69, 77, 0, 8,
    outer_color=rgb(65, 110, 180),
    inner_color=rgb(200, 218, 240)))
requests.append(border_box(69, 77, 8, 14,
    outer_color=rgb(180, 70, 0),
    inner_color=rgb(230, 200, 175)))
# ツールフォーム列（77-115）
requests.append(border_box(77, 116, 8, 14,
    outer_color=rgb(180, 70, 0),
    inner_color=rgb(230, 200, 175)))

# ── 13. セクションヘッダ結合セル追加 ─────────────────────────
new_merges = [
    # ①直繋ぎ → A4:H4 (cols 0-7)
    {'sheetId': SID, 'startRowIndex': 3,  'endRowIndex': 4,  'startColumnIndex': 0, 'endColumnIndex': 8},
    # ②既存面談 → A25:H25
    {'sheetId': SID, 'startRowIndex': 24, 'endRowIndex': 25, 'startColumnIndex': 0, 'endColumnIndex': 8},
    # ▼受任時 → 全幅
    {'sheetId': SID, 'startRowIndex': 50, 'endRowIndex': 51, 'startColumnIndex': 0, 'endColumnIndex': 14},
    # ▼検討・リリース時 → 全幅
    {'sheetId': SID, 'startRowIndex': 69, 'endRowIndex': 70, 'startColumnIndex': 0, 'endColumnIndex': 14},
]
for m in new_merges:
    requests.append({'mergeCells': {'range': m, 'mergeType': 'MERGE_ALL'}})

# ── 実行 ───────────────────────────────────────────────
result = service.spreadsheets().batchUpdate(
    spreadsheetId=SS_ID,
    body={'requests': requests}
).execute()
print(f'完了！ {len(result.get("replies", []))} リクエスト処理')
