import gspread
from google.oauth2.credentials import Credentials
import json

# Configuration
TOKEN_FILE = r'C:\Users\Loser\Desktop\-\-\nurse_list_deploy\token.json'
SPREADSHEET_URL = 'https://docs.google.com/spreadsheets/d/1sapVRFFAHcXFwB7GRlkRp5kjFDogd7unkDNDLi9avEc/edit'
SHEET_DASHBOARD = 'ダッシュボード'
SHEET_SERVICE_LENGTH = '勤続年数別'

# Theme Color Map (RGB values 0.0 to 1.0)
COLOR_MAP = {
    "全体": {"red": 0.1, "green": 0.2, "blue": 0.6},        # Dark Blue
    "PL合計": {"red": 0.13, "green": 0.59, "blue": 0.92},    # Blue
    "BC合計": {"red": 0.3, "green": 0.7, "blue": 0.31},      # Green
    "WEB合計": {"red": 1.0, "green": 0.75, "blue": 0.04},    # Gold/Yellow
    "メディカル合計": {"red": 0.95, "green": 0.26, "blue": 0.2}, # Red
    "人事": {"red": 0.6, "green": 0.15, "blue": 0.65},       # Purple
    "新規事業合計": {"red": 1.0, "green": 0.6, "blue": 0.0},  # Orange
    "その他": {"red": 0.6, "green": 0.6, "blue": 0.6},       # Grey
}

def main():
    try:
        with open(TOKEN_FILE, 'r') as f:
            creds_data = json.load(f)
        creds = Credentials.from_authorized_user_info(creds_data)
        client = gspread.authorize(creds)
    except Exception as e:
        print(f"Authentication Error: {e}")
        return

    try:
        sh = client.open_by_url(SPREADSHEET_URL)
        
        # 1. Format "勤続年数別" Sheet
        ws_sl = sh.worksheet(SHEET_SERVICE_LENGTH)
        sl_values = ws_sl.get_all_values()
        sl_requests = []
        
        for r_idx, row in enumerate(sl_values):
            for dept, color in COLOR_MAP.items():
                if dept in row:
                    sl_requests.append({
                        "repeatCell": {
                            "range": {"sheetId": ws_sl.id, "startRowIndex": r_idx, "endRowIndex": r_idx + 1, "startColumnIndex": 1, "endColumnIndex": 15},
                            "cell": {
                                "userEnteredFormat": {
                                    "backgroundColor": color,
                                    "textFormat": {"foregroundColor": {"red": 1, "green": 1, "blue": 1}, "bold": True},
                                    "horizontalAlignment": "CENTER"
                                }
                            },
                            "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment)"
                        }
                    })
        
        # 2. Format "ダッシュボード" Sheet
        ws_db = sh.worksheet(SHEET_DASHBOARD)
        db_values = ws_db.get_all_values()
        db_requests = []
        
        # Find matrix area in Dashboard
        for r_idx, row in enumerate(db_values):
            for dept, color in COLOR_MAP.items():
                if dept in row:
                    # Color the category cell (usually Col F / index 5 in the matrix)
                    # Let's find the exact column where 'dept' is
                    for c_idx, cell in enumerate(row):
                        if cell == dept:
                            db_requests.append({
                                "repeatCell": {
                                    "range": {"sheetId": ws_db.id, "startRowIndex": r_idx, "endRowIndex": r_idx + 1, "startColumnIndex": c_idx, "endColumnIndex": c_idx + 1},
                                    "cell": {
                                        "userEnteredFormat": {
                                            "backgroundColor": color,
                                            "textFormat": {"foregroundColor": {"red": 1, "green": 1, "blue": 1}, "bold": True},
                                            "horizontalAlignment": "CENTER"
                                        }
                                    },
                                    "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment)"
                                }
                            })

        # Apply updates
        if sl_requests:
            sh.batch_update({'requests': sl_requests})
            print(f"Success: {SHEET_SERVICE_LENGTH} formatted with dept colors!")
        
        if db_requests:
            sh.batch_update({'requests': db_requests})
            print(f"Success: {SHEET_DASHBOARD} formatted with dept colors!")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
