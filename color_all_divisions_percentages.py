import gspread
import gspread.utils
from google.oauth2.service_account import Credentials

# Credentials path
SERVICE_ACCOUNT_FILE = r'C:\Users\Loser\Desktop\-\-\automation-visitor-shindan\ageless-impulse-488713-m6-03014b3cddad.json'
SPREADSHEET_ID = '1sapVRFFAHcXFwB7GRlkRp5kjFDogd7unkDNDLi9avEc'
TARGET_GID = 709002610

def extract_percentage(s):
    """ '25 (12.6%)' から 12.6 を抽出する """
    if not s or '(' not in s: return None
    try:
        p_str = s.split('(')[1].split('%')[0]
        return float(p_str)
    except (ValueError, IndexError):
        return None

def get_color_rgb(percent):
    """ 
    0%は無色、それ以降は黄色〜赤の配分でRGBを返す
    """
    if percent is None or percent <= 0:
        return None # 無色
    
    if percent < 5.0:
        # ごく薄い黄色 (#fff9c4)
        return {"red": 1.0, "green": 0.98, "blue": 0.76}
    if percent < 15.0:
        # 黄色〜オレンジ (#ffe082)
        return {"red": 1.0, "green": 0.88, "blue": 0.51}
    
    # 薄い赤 (#ef9a9a)
    return {"red": 0.94, "green": 0.60, "blue": 0.60}

def main():
    try:
        scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
        creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=scopes)
        gc = gspread.authorize(creds)
        ss = gc.open_by_key(SPREADSHEET_ID)

        worksheet = None
        for ws in ss.worksheets():
            if ws.id == TARGET_GID:
                worksheet = ws
                break

        if not worksheet:
            print("Error: Target worksheet not found.")
            return

        data = worksheet.get_all_values()
        rows = len(data)
        if rows == 0: return
        cols = len(data[0])

        # 全事業部ブロックの特定
        divisions = []
        for i in range(rows):
            cell_value = data[i][1] if len(data[i]) > 1 else ""
            if cell_value and (isinstance(cell_value, str) and 
                               ("合計" in cell_value or cell_value == "全体" or cell_value == "人事")):
                divisions.append({
                    "headerRow": i,
                    "startRow": i + 1,
                    "endRow": i + 4
                })

        requests = []
        for div in divisions:
            for r in range(div["startRow"], min(div["endRow"] + 1, rows)):
                for c in range(2, cols):
                    val_str = data[r][c] if len(data[r]) > c else ""
                    percent = extract_percentage(val_str)
                    color = get_color_rgb(percent)

                    if color:
                        requests.append({
                            "updateCells": {
                                "rows": [
                                    {
                                        "values": [
                                            {
                                                "userEnteredFormat": {
                                                    "backgroundColor": color
                                                }
                                            }
                                        ]
                                    }
                                ],
                                "fields": "userEnteredFormat.backgroundColor",
                                "range": {
                                    "sheetId": TARGET_GID,
                                    "startRowIndex": r,
                                    "endRowIndex": r + 1,
                                    "startColumnIndex": c,
                                    "endColumnIndex": c + 1
                                }
                            }
                        })
                    else:
                        # 0%の場合は色を消す（白にする）
                        requests.append({
                            "updateCells": {
                                "rows": [
                                    {
                                        "values": [
                                            {
                                                "userEnteredFormat": {
                                                    "backgroundColor": {"red": 1.0, "green": 1.0, "blue": 1.0}
                                                }
                                            }
                                        ]
                                    }
                                ],
                                "fields": "userEnteredFormat.backgroundColor",
                                "range": {
                                    "sheetId": TARGET_GID,
                                    "startRowIndex": r,
                                    "endRowIndex": r + 1,
                                    "startColumnIndex": c,
                                    "endColumnIndex": c + 1
                                }
                            }
                        })

        if requests:
            # APIリクエスト制限を避けるため、適宜分割して送信（100件ずつなど）
            # ただし、今回の件数は数百件程度なので一括送信を試みる
            ss.batch_update({"requests": requests})
            print(f"Successfully colored {len(requests)} cells across all divisions.")
        else:
            print("No cells to color.")

    except Exception as e:
        print(f"An unexpected error occurred: {e}")

if __name__ == '__main__':
    main()
