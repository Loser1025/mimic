import os
import json
import unicodedata
from google.oauth2 import service_account
from googleapiclient.discovery import build

# 設定
_HERE = os.path.dirname(os.path.abspath(__file__))
SERVICE_ACCOUNT_FILE = os.path.join(_HERE, '..', 'automation-visitor-shindan', 'ageless-impulse-488713-m6-03014b3cddad.json')
SPREADSHEET_ID = '1YXES6PFY1feRXdAE_9WlUCEE22nWgkFEGCXaZDIZHrg'

HAN = 'ｦｧｨｩｪｫｬｭｮｯｰｱｲｳｴｵｶｷｸｹｺｻｼｽｾｿﾀﾁﾂﾃﾄﾅﾆﾇﾈﾉﾊﾋﾌﾍﾎﾏﾐﾑﾒﾓﾔﾕﾖﾗﾘﾙﾚﾛﾜﾝﾞﾟ'
ZEN = 'ヲァィゥェォャュョッーアイウエオカキクケコサシスセソタチツテトナニヌネノハヒフヘホマミムメモヤユヨラリルレロワン゛゜'

def normalize(name):
    if not name:
        return ''
    s = str(name).strip()
    # 全角英数記号 → 半角
    s = ''.join(chr(ord(c) - 0xFEE0) if '！' <= c <= '～' else c for c in s)
    # 半角カタカナ → 全角
    s = ''.join(ZEN[HAN.index(c)] if c in HAN else c for c in s)
    # 全角カタカナ → ひらがな
    s = ''.join(chr(ord(c) - 0x60) if '\u30A1' <= c <= '\u30F6' else c for c in s)
    # 空白除去
    s = ''.join(c for c in s if not unicodedata.category(c).startswith('Z') and c not in '\u200b\ufeff')
    return s.lower()

def get_values(service, sheet_name, range_str):
    result = service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=f"'{sheet_name}'!{range_str}"
    ).execute()
    return result.get('values', [])

def get_row6_format():
    """受電リスト 6行目のセルフォーマットを取得して表示する"""
    creds = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=['https://www.googleapis.com/auth/spreadsheets.readonly'])
    service = build('sheets', 'v4', credentials=creds)

    # シートIDを取得
    meta = service.spreadsheets().get(spreadsheetId=SPREADSHEET_ID).execute()
    sheet_id = None
    for s in meta['sheets']:
        if s['properties']['title'] == '受電リスト':
            sheet_id = s['properties']['sheetId']
            break

    if sheet_id is None:
        print('受電リスト シートが見つかりません')
        return

    # 6行目（インデックス5）のフォーマット取得
    result = service.spreadsheets().get(
        spreadsheetId=SPREADSHEET_ID,
        ranges=["'受電リスト'!B6:P6"],
        includeGridData=True
    ).execute()

    rows = result['sheets'][0]['data'][0].get('rowData', [])
    if not rows:
        print('データなし')
        return

    print('=== 受電リスト 6行目 フォーマット情報 ===\n')
    for ci, cell in enumerate(rows[0].get('values', [])):
        fmt = cell.get('effectiveFormat', {})
        text_fmt = fmt.get('textFormat', {})
        bg = fmt.get('backgroundColor', {})
        fg = text_fmt.get('foregroundColor', {})

        def to_hex(c):
            r = int(c.get('red', 0) * 255)
            g = int(c.get('green', 0) * 255)
            b = int(c.get('blue', 0) * 255)
            return f'#{r:02x}{g:02x}{b:02x}'

        col_label = chr(ord('B') + ci)
        print(f'[{col_label}列]')
        print(f'  背景色       : {to_hex(bg)}')
        print(f'  文字色       : {to_hex(fg)}')
        print(f'  フォント名   : {text_fmt.get("fontFamily", "(未設定)")}')
        print(f'  フォントサイズ: {text_fmt.get("fontSize", "(未設定)")}')
        print(f'  太字         : {text_fmt.get("bold", False)}')
        print(f'  斜体         : {text_fmt.get("italic", False)}')
        print(f'  水平揃え     : {fmt.get("horizontalAlignment", "(未設定)")}')
        print()

def main():
    try:
        creds = service_account.Credentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE, scopes=['https://www.googleapis.com/auth/spreadsheets.readonly'])
        service = build('sheets', 'v4', credentials=creds)

        # ── 受電リスト から名前を収集 ──
        list_rows = get_values(service, '受電リスト', 'A1:R200')

        # "No." がある行を探してデータ開始行を特定
        data_start = 7
        for i, row in enumerate(list_rows):
            if len(row) > 1 and str(row[1]).strip() == 'No.':
                data_start = i + 1
                break

        # Group1=D(3), Group2=J(9), Group3=P(15)
        group_cols = {3: 'Group1', 9: 'Group2', 15: 'Group3'}
        list_names = {}  # normalized → (original, group)
        for i in range(data_start, len(list_rows)):
            row = list_rows[i]
            for col, grp in group_cols.items():
                if col < len(row) and str(row[col]).strip():
                    orig = str(row[col]).strip()
                    norm = normalize(orig)
                    if norm:
                        list_names[norm] = (orig, grp)

        print(f"受電リスト 登録名数: {len(list_names)} 名\n")

        # ── シート1 B列から名前を収集 ──
        sheet1_rows = get_values(service, 'シート1', 'B1:B2000')
        sheet1_names = {}  # normalized → original
        for row in sheet1_rows[1:]:  # ヘッダースキップ
            if row and str(row[0]).strip():
                orig = str(row[0]).strip()
                norm = normalize(orig)
                if norm not in sheet1_names:
                    sheet1_names[norm] = orig

        print(f"シート1 ユニーク名数: {len(sheet1_names)} 名\n")

        # ── マッチ結果 ──
        matched   = {k: v for k, v in list_names.items() if k in sheet1_names}
        unmatched = {k: v for k, v in list_names.items() if k not in sheet1_names}

        print(f"=== マッチした名前 ({len(matched)} 件) ===")
        for norm, (orig, grp) in sorted(matched.items(), key=lambda x: x[1][1]):
            sheet1_orig = sheet1_names[norm]
            diff = f"  ※表記違い: 受電リスト「{orig}」← シート1「{sheet1_orig}」" if orig != sheet1_orig else ""
            print(f"  [{grp}] {orig}{diff}")

        print(f"\n=== マッチしなかった名前 ({len(unmatched)} 件) ===")
        for norm, (orig, grp) in sorted(unmatched.items(), key=lambda x: x[1][1]):
            # シート1で部分一致候補を探す
            candidates = [s1 for n1, s1 in sheet1_names.items() if norm in n1 or n1 in norm]
            hint = f"  → シート1候補: 「{candidates[0]}」" if candidates else "  → シート1に候補なし"
            print(f"  [{grp}] {orig}  (正規化: {norm}){hint}")

    except Exception as e:
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    get_row6_format()
