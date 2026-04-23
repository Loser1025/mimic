import gspread
from google.oauth2.credentials import Credentials
import json

# Configuration
TOKEN_FILE = r'C:\Users\Loser\Desktop\-\-\nurse_list_deploy\token.json'
SPREADSHEET_URL = 'https://docs.google.com/spreadsheets/d/1sapVRFFAHcXFwB7GRlkRp5kjFDogd7unkDNDLi9avEc/edit'
TARGET_SHEET_NAME = '勤続年数別'

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
        ws = sh.worksheet(TARGET_SHEET_NAME)
        all_values = ws.get_all_values()
        
        requests = []
        major_depts = ["全体", "PL合計", "BC合計", "WEB合計", "メディカル合計", "人事", "新規事業合計", "その他"]
        
        for r_idx, row in enumerate(all_values):
            for dept in major_depts:
                if dept in row:
                    # 1. Format Block Header
                    requests.append({
                        "repeatCell": {
                            "range": {"sheetId": ws.id, "startRowIndex": r_idx, "endRowIndex": r_idx + 1, "startColumnIndex": 1, "endColumnIndex": 15},
                            "cell": {
                                "userEnteredFormat": {
                                    "backgroundColor": {"red": 0.1, "green": 0.45, "blue": 0.9},
                                    "textFormat": {"foregroundColor": {"red": 1.0, "green": 1.0, "blue": 1.0}, "bold": True},
                                    "horizontalAlignment": "CENTER",
                                    "verticalAlignment": "MIDDLE"
                                }
                            },
                            "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment,verticalAlignment)"
                        }
                    })
                    
                    # 2. Format Category Rows
                    for offset in range(1, 5):
                        curr_row = r_idx + offset
                        if curr_row >= len(all_values): break
                        
                        requests.append({
                            "repeatCell": {
                                "range": {"sheetId": ws.id, "startRowIndex": curr_row, "endRowIndex": curr_row + 1, "startColumnIndex": 1, "endColumnIndex": 2},
                                "cell": {
                                    "userEnteredFormat": {
                                        "backgroundColor": {"red": 0.95, "green": 0.95, "blue": 0.95},
                                        "textFormat": {"bold": True},
                                        "horizontalAlignment": "LEFT"
                                    }
                                },
                                "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment)"
                            }
                        })
                        
                        requests.append({
                            "repeatCell": {
                                "range": {"sheetId": ws.id, "startRowIndex": curr_row, "endRowIndex": curr_row + 1, "startColumnIndex": 2, "endColumnIndex": 15},
                                "cell": {
                                    "userEnteredFormat": {
                                        "horizontalAlignment": "CENTER"
                                    }
                                },
                                "fields": "userEnteredFormat(horizontalAlignment)"
                            }
                        })
                    
                    # 3. Add Block Borders
                    requests.append({
                        "repeatCell": {
                            "range": {"sheetId": ws.id, "startRowIndex": r_idx, "endRowIndex": r_idx + 5, "startColumnIndex": 1, "endColumnIndex": 15},
                            "cell": {
                                "userEnteredFormat": {
                                    "borders": {
                                        "top": {"style": "SOLID", "color": {"red": 0.8, "green": 0.8, "blue": 0.8}},
                                        "bottom": {"style": "SOLID", "color": {"red": 0.8, "green": 0.8, "blue": 0.8}},
                                        "left": {"style": "SOLID", "color": {"red": 0.8, "green": 0.8, "blue": 0.8}},
                                        "right": {"style": "SOLID", "color": {"red": 0.8, "green": 0.8, "blue": 0.8}}
                                    }
                                }
                            },
                            "fields": "userEnteredFormat(borders)"
                        }
                    })

        sh.batch_update({'requests': requests})
        print("Success: '勤続年数別' sheet visually enhanced!")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
