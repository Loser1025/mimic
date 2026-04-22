import gspread
from google.oauth2.service_account import Credentials

# Configuration
SERVICE_ACCOUNT_FILE = r'C:\Users\Loser\Desktop\-\-\automation-visitor-shindan\ageless-impulse-488713-m6-03014b3cddad.json'
SPREADSHEET_URL = 'https://docs.google.com/spreadsheets/d/1sapVRFFAHcXFwB7GRlkRp5kjFDogd7unkDNDLi9avEc/edit'
DASHBOARD_SHEET = 'ダッシュボード'

def get_color_for_value(value_str):
    """ Returns a hex color based on percentage value for heatmap """
    try:
        val = float(value_str.strip('%'))
        if val >= 30: return {'red': 1.0, 'green': 0.8, 'blue': 0.8} # Light Red
        if val >= 20: return {'red': 1.0, 'green': 0.9, 'blue': 0.7} # Light Orange
        if val >= 10: return {'red': 1.0, 'green': 1.0, 'blue': 0.8} # Light Yellow
        return None # White
    except:
        return None

def main():
    scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=scopes)
    client = gspread.authorize(creds)

    try:
        sh = client.open_by_url(SPREADSHEET_URL)
        ws = sh.worksheet(DASHBOARD_SHEET)
        
        # Get current data to determine ranges
        all_values = ws.get_all_values()
        
        requests = []

        # 1. Main Title (A1)
        requests.append({
            "repeatCell": {
                "range": {"sheetId": ws.id, "startRowIndex": 0, "endRowIndex": 1, "startColumnIndex": 0, "endColumnIndex": 10},
                "cell": {
                    "userEnteredFormat": {
                        "backgroundColor": {"red": 0.1, "green": 0.45, "blue": 0.9}, # Blue
                        "textFormat": {"foregroundColor": {"red": 1.0, "green": 1.0, "blue": 1.0}, "bold": True, "fontSize": 14},
                        "horizontalAlignment": "CENTER",
                        "verticalAlignment": "MIDDLE"
                    }
                },
                "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment,verticalAlignment)"
            }
        })

        # 2. Summary Section (A3:C6)
        requests.append({
            "repeatCell": {
                "range": {"sheetId": ws.id, "startRowIndex": 2, "endRowIndex": 3, "startColumnIndex": 0, "endColumnIndex": 3},
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

        # 3. Overall Ranking Table (A7:D...)
        # Header
        requests.append({
            "repeatCell": {
                "range": {"sheetId": ws.id, "startRowIndex": 7, "endRowIndex": 8, "startColumnIndex": 0, "endColumnIndex": 4},
                "cell": {
                    "userEnteredFormat": {
                        "backgroundColor": {"red": 0.2, "green": 0.2, "blue": 0.2},
                        "textFormat": {"foregroundColor": {"red": 1.0, "green": 1.0, "blue": 1.0}, "bold": True},
                        "horizontalAlignment": "CENTER"
                    }
                },
                "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment)"
            }
        })
        # Data body (Zebra stripes)
        for i in range(8, 25): # Approximate range
            bg = {"red": 0.98, "green": 0.98, "blue": 0.98} if i % 2 == 0 else {"red": 1.0, "green": 1.0, "blue": 1.0}
            requests.append({
                "repeatCell": {
                    "range": {"sheetId": ws.id, "startRowIndex": i, "endRowIndex": i+1, "startColumnIndex": 1, "endColumnIndex": 4},
                    "cell": {
                        "userEnteredFormat": {
                            "backgroundColor": bg,
                            "horizontalAlignment": "CENTER"
                        }
                    },
                    "fields": "userEnteredFormat(backgroundColor,horizontalAlignment)"
                }
            })

        # 4. Matrix Section (E7:...)
        # Header
        requests.append({
            "repeatCell": {
                "range": {"sheetId": ws.id, "startRowIndex": 7, "endRowIndex": 8, "startColumnIndex": 4, "endColumnIndex": 20},
                "cell": {
                    "userEnteredFormat": {
                        "backgroundColor": {"red": 0.2, "green": 0.2, "blue": 0.2},
                        "textFormat": {"foregroundColor": {"red": 1.0, "green": 1.0, "blue": 1.0}, "bold": True},
                        "horizontalAlignment": "CENTER"
                    }
                },
                "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment)"
            }
        })

        # Heatmap for Matrix
        # Row 0 is header, start from index 8
        for r_idx in range(8, len(all_values)):
            row = all_values[r_idx]
            if len(row) < 5: continue
            
            for c_idx in range(4, len(row)):
                val = row[c_idx]
                color = get_color_for_value(val)
                if color:
                    requests.append({
                        "repeatCell": {
                            "range": {"sheetId": ws.id, "startRowIndex": r_idx, "endRowIndex": r_idx+1, "startColumnIndex": c_idx, "endColumnIndex": c_idx+1},
                            "cell": {
                                "userEnteredFormat": {
                                    "backgroundColor": color,
                                    "horizontalAlignment": "CENTER"
                                }
                            },
                            "fields": "userEnteredFormat(backgroundColor,horizontalAlignment)"
                        }
                    })
                else:
                    requests.append({
                        "repeatCell": {
                            "range": {"sheetId": ws.id, "startRowIndex": r_idx, "endRowIndex": r_idx+1, "startColumnIndex": c_idx, "endColumnIndex": c_idx+1},
                            "cell": {
                                "userEnteredFormat": {
                                    "horizontalAlignment": "CENTER"
                                }
                            },
                            "fields": "userEnteredFormat(horizontalAlignment)"
                        }
                    })

        # 5. Insights Section (Bottom)
        # We need to find the bottom row
        last_row = len(all_values)
        # Find where '【インサイト' starts
        insight_row = -1
        for i, row in enumerate(all_values):
            if row and '【インサイト' in row[0]:
                insight_row = i
                break
        
        if insight_row != -1:
            requests.append({
                "repeatCell": {
                    "range": {"sheetId": ws.id, "startRowIndex": insight_row, "endRowIndex": insight_row+1, "startColumnIndex": 0, "endColumnIndex": 3},
                    "cell": {
                        "userEnteredFormat": {
                            "backgroundColor": {"red": 0.9, "green": 0.9, "blue": 1.0}, # Light Blue
                            "textFormat": {"bold": True},
                            "horizontalAlignment": "LEFT"
                        }
                    },
                    "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment)"
                }
            })

        # Apply all updates
        sh.batch_update({'requests': requests})
        print("Success: Dashboard visually enhanced!")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
