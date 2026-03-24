import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from google.oauth2 import service_account
from googleapiclient.discovery import build

SA_KEY = 'C:/Users/弁護士法人響/Downloads/ageless-impulse-488713-m6-0c52b81add54.json'
SPREADSHEET_ID = '1d6_Q3ws9yIEbCUZAMfaWqb2rZ_fjrJdLqruMWucg3pU'

creds = service_account.Credentials.from_service_account_file(SA_KEY, scopes=['https://www.googleapis.com/auth/spreadsheets'])
service = build('sheets', 'v4', credentials=creds)

def rgb(h):
    h = h.lstrip('#')
    return {'red': int(h[0:2],16)/255, 'green': int(h[2:4],16)/255, 'blue': int(h[4:6],16)/255}

# デモシート再作成
meta = service.spreadsheets().get(spreadsheetId=SPREADSHEET_ID).execute()
demo_gid = None
for s in meta['sheets']:
    if s['properties']['title'] == '🎨 背景カラーデモ':
        demo_gid = s['properties']['sheetId']
        break

pre_requests = []
if demo_gid:
    pre_requests.append({'deleteSheet': {'sheetId': demo_gid}})
pre_requests.append({'addSheet': {'properties': {'title': '🎨 背景カラーデモ', 'gridProperties': {'rowCount': 250, 'columnCount': 15}}}})

res = service.spreadsheets().batchUpdate(spreadsheetId=SPREADSHEET_ID, body={'requests': pre_requests}).execute()
demo_gid = res['replies'][-1]['addSheet']['properties']['sheetId']
print('デモシートGID:', demo_gid)

# ピンク系カラー大量展開
colors = [
    # --- 超薄・パウダー系 ---
    ('FFF5F7', '① パールホワイトピンク'),
    ('FFF0F5', '② ごく薄ラベンダーピンク'),
    ('FDEEF4', '③ ミルクピンク'),
    ('FCE8F0', '④ 薄桜'),
    ('FFE8F0', '⑤ ベビーピンク'),
    ('FFE4EC', '⑥ ソフトローズ'),
    # --- パステル系 ---
    ('FFD6E7', '⑦ パステルピンク ← 現在'),
    ('FFC8DD', '⑧ パウダーピンク'),
    ('FFBFD5', '⑨ 桜ピンク'),
    ('FFB7C5', '⑩ 花びらピンク'),
    ('FFAEC9', '⑪ 華やかピンク'),
    ('FFA8C5', '⑫ キャンディピンク'),
    # --- ピーチ・サーモン系 ---
    ('FFD5C8', '⑬ ピーチピンク'),
    ('FFCAB8', '⑭ サーモンピンク'),
    ('FFD0C2', '⑮ コーラルピンク'),
    ('FFE0D5', '⑯ ソフトコーラル'),
    # --- ローズ・マゼンタ系 ---
    ('FFD0E8', '⑰ ローズクォーツ'),
    ('F8D0E8', '⑱ アンティークローズ'),
    ('F5D0F0', '⑲ ラベンダーピンク'),
    ('EED5F5', '⑳ ライラックピンク'),
    # --- くすみ・ニュアンス系 ---
    ('F2D9E4', '㉑ ダスティローズ'),
    ('EDD5E0', '㉒ モーブピンク'),
    ('E8D5E8', '㉓ ミスティモーブ'),
    ('F0E0EA', '㉔ ブラッシュ'),
]

requests = []

# シートタイトル行
requests.append({'repeatCell': {
    'range': {'sheetId': demo_gid, 'startRowIndex': 0, 'endRowIndex': 1, 'startColumnIndex': 0, 'endColumnIndex': 13},
    'cell': {'userEnteredFormat': {
        'backgroundColor': rgb('880E4F'),
        'textFormat': {'foregroundColor': rgb('FFFFFF'), 'bold': True, 'fontSize': 13},
        'horizontalAlignment': 'CENTER', 'verticalAlignment': 'MIDDLE'
    }},
    'fields': 'userEnteredFormat.backgroundColor,userEnteredFormat.textFormat,userEnteredFormat.horizontalAlignment,userEnteredFormat.verticalAlignment'
}})
requests.append({'updateDimensionProperties': {
    'range': {'sheetId': demo_gid, 'dimension': 'ROWS', 'startIndex': 0, 'endIndex': 1},
    'properties': {'pixelSize': 45}, 'fields': 'pixelSize'
}})

row = 2
for hex_code, label in colors:
    block_end = row + 8

    # ブロック全体に背景色
    requests.append({'repeatCell': {
        'range': {'sheetId': demo_gid, 'startRowIndex': row, 'endRowIndex': block_end, 'startColumnIndex': 0, 'endColumnIndex': 13},
        'cell': {'userEnteredFormat': {'backgroundColor': rgb(hex_code)}},
        'fields': 'userEnteredFormat.backgroundColor'
    }})

    # ラベル行
    requests.append({'repeatCell': {
        'range': {'sheetId': demo_gid, 'startRowIndex': row, 'endRowIndex': row+1, 'startColumnIndex': 0, 'endColumnIndex': 13},
        'cell': {'userEnteredFormat': {
            'backgroundColor': rgb(hex_code),
            'textFormat': {'foregroundColor': rgb('880E4F'), 'bold': True, 'fontSize': 10},
            'horizontalAlignment': 'CENTER', 'verticalAlignment': 'MIDDLE'
        }},
        'fields': 'userEnteredFormat.backgroundColor,userEnteredFormat.textFormat,userEnteredFormat.horizontalAlignment,userEnteredFormat.verticalAlignment'
    }})
    requests.append({'updateDimensionProperties': {
        'range': {'sheetId': demo_gid, 'dimension': 'ROWS', 'startIndex': row, 'endIndex': row+1},
        'properties': {'pixelSize': 24}, 'fields': 'pixelSize'
    }})

    # テーブルサンプル5行
    sample_rows = [
        ('C2185B', 'FFFFFF', True),   # ヘッダー
        ('FFFFFF', '1A1A2E', False),  # 通常行1
        ('FDE8EF', '1A1A2E', False),  # 通常行2
        ('FFCC80', '5D4037', True),   # 上位強調
        ('D1C4E9', '4A148C', False),  # 下位強調
    ]
    for i, (bg, fg, bold) in enumerate(sample_rows):
        r = row + 1 + i
        requests.append({'repeatCell': {
            'range': {'sheetId': demo_gid, 'startRowIndex': r, 'endRowIndex': r+1, 'startColumnIndex': 1, 'endColumnIndex': 10},
            'cell': {'userEnteredFormat': {
                'backgroundColor': rgb(bg),
                'textFormat': {'foregroundColor': rgb(fg), 'bold': bold, 'fontSize': 10},
                'horizontalAlignment': 'CENTER', 'verticalAlignment': 'MIDDLE'
            }},
            'fields': 'userEnteredFormat.backgroundColor,userEnteredFormat.textFormat,userEnteredFormat.horizontalAlignment,userEnteredFormat.verticalAlignment'
        }})
        requests.append({'updateDimensionProperties': {
            'range': {'sheetId': demo_gid, 'dimension': 'ROWS', 'startIndex': r, 'endIndex': r+1},
            'properties': {'pixelSize': 22}, 'fields': 'pixelSize'
        }})

    # テーブル外枠
    requests.append({'updateBorders': {
        'range': {'sheetId': demo_gid, 'startRowIndex': row+1, 'endRowIndex': row+6, 'startColumnIndex': 1, 'endColumnIndex': 10},
        'top':    {'style': 'SOLID_MEDIUM', 'color': rgb('AD1457')},
        'bottom': {'style': 'SOLID_MEDIUM', 'color': rgb('AD1457')},
        'left':   {'style': 'SOLID_MEDIUM', 'color': rgb('AD1457')},
        'right':  {'style': 'SOLID_MEDIUM', 'color': rgb('AD1457')},
        'innerHorizontal': {'style': 'SOLID', 'color': rgb('F8BBD0')},
        'innerVertical':   {'style': 'SOLID', 'color': rgb('F8BBD0')},
    }})

    row = block_end

# 列幅
requests.append({'updateDimensionProperties': {
    'range': {'sheetId': demo_gid, 'dimension': 'COLUMNS', 'startIndex': 0, 'endIndex': 1},
    'properties': {'pixelSize': 15}, 'fields': 'pixelSize'
}})
for col in range(1, 10):
    requests.append({'updateDimensionProperties': {
        'range': {'sheetId': demo_gid, 'dimension': 'COLUMNS', 'startIndex': col, 'endIndex': col+1},
        'properties': {'pixelSize': 90}, 'fields': 'pixelSize'
    }})

result = service.spreadsheets().batchUpdate(spreadsheetId=SPREADSHEET_ID, body={'requests': requests}).execute()
print('完了! カラー数:', len(colors), '/ リクエスト数:', len(requests))
