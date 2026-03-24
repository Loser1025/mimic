import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from google.oauth2 import service_account
from googleapiclient.discovery import build

SA_KEY = 'C:/Users/弁護士法人響/Downloads/ageless-impulse-488713-m6-0c52b81add54.json'
SPREADSHEET_ID = '1d6_Q3ws9yIEbCUZAMfaWqb2rZ_fjrJdLqruMWucg3pU'
SHEET_GID = 1646467731

creds = service_account.Credentials.from_service_account_file(SA_KEY, scopes=['https://www.googleapis.com/auth/spreadsheets'])
service = build('sheets', 'v4', credentials=creds)

def rgb(h):
    h = h.lstrip('#')
    return {'red': int(h[0:2],16)/255, 'green': int(h[2:4],16)/255, 'blue': int(h[4:6],16)/255}

DARK    = rgb('1A1A2E')
WHITE   = rgb('FFFFFF')
BG      = 'FFAEC9'
COL_END = 10  # A〜J列（B列が空白スペーサー）
NONE    = {'style': 'NONE'}
ALL_FMT = 'userEnteredFormat.backgroundColor,userEnteredFormat.textFormat,userEnteredFormat.horizontalAlignment,userEnteredFormat.verticalAlignment'

requests = []

# 1. 全体リセット
requests.append({'repeatCell': {
    'range': {'sheetId': SHEET_GID, 'startRowIndex': 0, 'endRowIndex': 130, 'startColumnIndex': 0, 'endColumnIndex': 15},
    'cell': {'userEnteredFormat': {
        'backgroundColor': rgb('FFFFFF'),
        'textFormat': {'foregroundColor': DARK, 'bold': False, 'fontSize': 10}
    }},
    'fields': 'userEnteredFormat.backgroundColor,userEnteredFormat.textFormat'
}})

# 2. 背景エリア
for r0, r1 in [(1, 4), (35, 39), (61, 77), (122, 150)]:
    requests.append({'repeatCell': {
        'range': {'sheetId': SHEET_GID, 'startRowIndex': r0, 'endRowIndex': r1, 'startColumnIndex': 0, 'endColumnIndex': 15},
        'cell': {'userEnteredFormat': {'backgroundColor': rgb(BG)}},
        'fields': 'userEnteredFormat.backgroundColor'
    }})
    requests.append({'updateBorders': {
        'range': {'sheetId': SHEET_GID, 'startRowIndex': r0, 'endRowIndex': r1, 'startColumnIndex': 0, 'endColumnIndex': 15},
        'top': NONE, 'bottom': NONE, 'left': NONE, 'right': NONE,
        'innerHorizontal': NONE, 'innerVertical': NONE
    }})

# 3. タイトル行
requests.append({'repeatCell': {
    'range': {'sheetId': SHEET_GID, 'startRowIndex': 0, 'endRowIndex': 1, 'startColumnIndex': 0, 'endColumnIndex': 15},
    'cell': {'userEnteredFormat': {
        'backgroundColor': rgb('880E4F'),
        'textFormat': {'foregroundColor': WHITE, 'bold': True, 'fontSize': 16},
        'horizontalAlignment': 'CENTER', 'verticalAlignment': 'MIDDLE'
    }},
    'fields': ALL_FMT
}})
requests.append({'updateDimensionProperties': {
    'range': {'sheetId': SHEET_GID, 'dimension': 'ROWS', 'startIndex': 0, 'endIndex': 1},
    'properties': {'pixelSize': 55}, 'fields': 'pixelSize'
}})

# 4. 各チーム
teams = [
    {'header': 4,  'data_start': 5,  'data_end': 35},
    {'header': 39, 'data_start': 40, 'data_end': 61},
    {'header': 77, 'data_start': 78, 'data_end': 122},
]
gold_colors = ['FFCC80', 'FFD599', 'FFDFA8', 'FFE8B8', 'FFF0CC', 'FFF8E1']
lavender_colors = ['D1C4E9', 'D8CCF0', 'E0D5F2', 'E8DFF5', 'EFE9F7', 'F5F0FB']

for team in teams:
    h, ds, de = team['header'], team['data_start'], team['data_end']

    # ヘッダー行
    requests.append({'repeatCell': {
        'range': {'sheetId': SHEET_GID, 'startRowIndex': h, 'endRowIndex': h+1, 'startColumnIndex': 0, 'endColumnIndex': COL_END},
        'cell': {'userEnteredFormat': {
            'backgroundColor': rgb('C2185B'),
            'textFormat': {'foregroundColor': WHITE, 'bold': True, 'fontSize': 11},
            'horizontalAlignment': 'CENTER', 'verticalAlignment': 'MIDDLE'
        }},
        'fields': ALL_FMT
    }})
    requests.append({'updateDimensionProperties': {
        'range': {'sheetId': SHEET_GID, 'dimension': 'ROWS', 'startIndex': h, 'endIndex': h+1},
        'properties': {'pixelSize': 32}, 'fields': 'pixelSize'
    }})

    # 通常データ行（交互カラー）
    for i in range(ds, de):
        bg = 'FFFFFF' if (i - ds) % 2 == 0 else 'FDE8EF'
        requests.append({'repeatCell': {
            'range': {'sheetId': SHEET_GID, 'startRowIndex': i, 'endRowIndex': i+1, 'startColumnIndex': 0, 'endColumnIndex': COL_END},
            'cell': {'userEnteredFormat': {
                'backgroundColor': rgb(bg),
                'textFormat': {'foregroundColor': DARK, 'bold': False, 'fontSize': 10},
                'horizontalAlignment': 'CENTER', 'verticalAlignment': 'MIDDLE'
            }},
            'fields': ALL_FMT
        }})
        # A列のみ左揃え
        requests.append({'repeatCell': {
            'range': {'sheetId': SHEET_GID, 'startRowIndex': i, 'endRowIndex': i+1, 'startColumnIndex': 0, 'endColumnIndex': 1},
            'cell': {'userEnteredFormat': {'horizontalAlignment': 'LEFT'}},
            'fields': 'userEnteredFormat.horizontalAlignment'
        }})

    # 上位6名（黄金グラデーション）
    for i, row_idx in enumerate(range(ds, ds + 6)):
        requests.append({'repeatCell': {
            'range': {'sheetId': SHEET_GID, 'startRowIndex': row_idx, 'endRowIndex': row_idx+1, 'startColumnIndex': 0, 'endColumnIndex': COL_END},
            'cell': {'userEnteredFormat': {
                'backgroundColor': rgb(gold_colors[i]),
                'textFormat': {'foregroundColor': rgb('5D4037'), 'bold': True, 'fontSize': 10},
                'horizontalAlignment': 'CENTER', 'verticalAlignment': 'MIDDLE'
            }},
            'fields': ALL_FMT
        }})
        requests.append({'repeatCell': {
            'range': {'sheetId': SHEET_GID, 'startRowIndex': row_idx, 'endRowIndex': row_idx+1, 'startColumnIndex': 0, 'endColumnIndex': 1},
            'cell': {'userEnteredFormat': {'horizontalAlignment': 'LEFT'}},
            'fields': 'userEnteredFormat.horizontalAlignment'
        }})
        requests.append({'updateBorders': {
            'range': {'sheetId': SHEET_GID, 'startRowIndex': row_idx, 'endRowIndex': row_idx+1, 'startColumnIndex': 0, 'endColumnIndex': COL_END},
            'left':   {'style': 'SOLID_THICK', 'color': rgb('FF8F00')},
            'bottom': {'style': 'SOLID', 'color': rgb('FFD180')},
        }})

    # 下位6名（ラベンダーグラデーション）
    for i, row_idx in enumerate(range(de - 6, de)):
        shade = lavender_colors[5 - i]
        requests.append({'repeatCell': {
            'range': {'sheetId': SHEET_GID, 'startRowIndex': row_idx, 'endRowIndex': row_idx+1, 'startColumnIndex': 0, 'endColumnIndex': COL_END},
            'cell': {'userEnteredFormat': {
                'backgroundColor': rgb(shade),
                'textFormat': {'foregroundColor': rgb('4A148C'), 'bold': False, 'fontSize': 10},
                'horizontalAlignment': 'CENTER', 'verticalAlignment': 'MIDDLE'
            }},
            'fields': ALL_FMT
        }})
        requests.append({'repeatCell': {
            'range': {'sheetId': SHEET_GID, 'startRowIndex': row_idx, 'endRowIndex': row_idx+1, 'startColumnIndex': 0, 'endColumnIndex': 1},
            'cell': {'userEnteredFormat': {'horizontalAlignment': 'LEFT'}},
            'fields': 'userEnteredFormat.horizontalAlignment'
        }})
        requests.append({'updateBorders': {
            'range': {'sheetId': SHEET_GID, 'startRowIndex': row_idx, 'endRowIndex': row_idx+1, 'startColumnIndex': 0, 'endColumnIndex': COL_END},
            'left':   {'style': 'SOLID_THICK', 'color': rgb('7E57C2')},
            'bottom': {'style': 'SOLID', 'color': rgb('B39DDB')},
        }})

    # 表全体の外枠
    requests.append({'updateBorders': {
        'range': {'sheetId': SHEET_GID, 'startRowIndex': h, 'endRowIndex': de, 'startColumnIndex': 0, 'endColumnIndex': COL_END},
        'top':    {'style': 'SOLID_MEDIUM', 'color': rgb('AD1457')},
        'bottom': {'style': 'SOLID_MEDIUM', 'color': rgb('AD1457')},
        'left':   {'style': 'SOLID_THICK',  'color': rgb('AD1457')},
        'right':  {'style': 'SOLID_THICK',  'color': rgb('AD1457')},
        'innerHorizontal': {'style': 'SOLID', 'color': rgb('F8BBD0')},
        'innerVertical':   {'style': 'SOLID', 'color': rgb('F8BBD0')},
    }})
    # ヘッダー下線
    requests.append({'updateBorders': {
        'range': {'sheetId': SHEET_GID, 'startRowIndex': h, 'endRowIndex': h+1, 'startColumnIndex': 0, 'endColumnIndex': COL_END},
        'bottom': {'style': 'SOLID_MEDIUM', 'color': rgb('AD1457')},
    }})

result = service.spreadsheets().batchUpdate(
    spreadsheetId=SPREADSHEET_ID, body={'requests': requests}
).execute()
print('完了! リクエスト数:', len(requests))
