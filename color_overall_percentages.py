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
        # '(' と '%' の間の文字列を抽出
        p_str = s.split('(')[1].split('%')[0]
        return float(p_str)
    except (ValueError, IndexError):
        return None

def get_color_rgb(percent):
    """ 割合に応じたRGB値を返す (0.0 ~ 1.0) """
    if percent is None or percent <= 0:
        return None
    if percent >= 10.0:
        return {"red": 1.0, "green": 0.8, "blue": 0.8}  # 薄い赤 (#f4cccc)
    if percent >= 5.0:
        return {"red": 1.0, "green": 0.94, "blue": 0.8} # 薄い黄 (#fff2cc)
    return {"red": 0.85, "green": 0.92, "blue": 0.82}   # 薄い緑 (#d9ead3)

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
        # 全体ブロックは 2行目〜5行目 (index 1〜4), C列〜O列 (index 2〜14)
        # データの行数が足りない場合は調整
        end_row = min(5, len(data))
        end_col = len(data[0])

        requests = []
        for r in range(1, end_row):
            for c in range(2, end_col):
                val_str = data[r][c] if len(data[r]) > c else ""
                percent = extract_percentage(val_str)
                color = get_color_rgb(percent)

                if color:
                    # Google Sheets APIの updateCells リクエストを構築
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

        if requests:
            ss.batch_update({"requests": requests})
            print(f"Successfully colored {len(requests)} cells in 'Overall' section.")
        else:
            print("No cells matched the coloring criteria.")

    except Exception as e:
        print(f"An unexpected error occurred: {e}")

if __name__ == '__main__':
    main()
