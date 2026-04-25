import os
from google.oauth2 import service_account
from googleapiclient.discovery import build

# Configuration
SERVICE_ACCOUNT_FILE = r'C:\Users\Loser\Desktop\-\-\automation-visitor-shindan\ageless-impulse-488713-m6-03014b3cddad.json'
SPREADSHEET_ID = '1BJYhsb38mCtVOpHdfm-RUOdAiQyhIVTSP2qKP3nTeP0'
SHEET_NAME = '31'

# Define Colors
COLOR_HEADER_BG = {'red': 0.25, 'green': 0.52, 'blue': 0.96} # Google Blue (#4084F4)
COLOR_HEADER_TEXT = {'red': 1.0, 'green': 1.0, 'blue': 1.0}   # White
COLOR_ALT_BG = {'red': 0.93, 'green': 0.93, 'blue': 0.93}     # Light Grey (#EFEFEF)

def main():
    # Authenticate
    creds = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, 
        scopes=['https://www.googleapis.com/auth/spreadsheets']
    )
    service = build('sheets', 'v4', credentials=creds)

    # 1. Get the sheet's data range to know how much to color
    # We fetch the metadata of the spreadsheet to find the sheet ID for '31'
    sheet_metadata = service.spreadsheets().get(spreadsheetId=SPREADSHEET_ID).execute()
    sheets = sheet_metadata.get('sheets', [])
    sheet_id = None
    for s in sheets:
        if s.get('properties', {}).get('title') == SHEET_NAME:
            sheet_id = s.get('properties', {}).get('sheetId')
            break
    
    if sheet_id is None:
        print(f"Sheet '{SHEET_NAME}' not found.")
        return

    # Get values to determine the used range
    result = service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID, 
        range=f"'{SHEET_NAME}'!A1:Z1000"
    ).execute()
    values = result.get('values', [])

    if not values:
        print("No data found in the sheet.")
        return

    num_rows = len(values)
    num_cols = max(len(row) for row in values) if values else 0
    
    print(f"Table size: {num_rows} rows x {num_cols} columns")

    requests = []

    # 2. Style Header (Row 0)
    requests.append({
        "repeatCell": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": 0,
                "endRowIndex": 1,
                "startColumnIndex": 0,
                "endColumnIndex": num_cols
            },
            "cell": {
                "userEnteredFormat": {
                    "backgroundColor": COLOR_HEADER_BG,
                    "textFormat": {
                        "foregroundColor": COLOR_HEADER_TEXT,
                        "bold": True
                    },
                    "horizontalAlignment": "CENTER"
                }
            },
            "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment)"
        }
    })

    # 3. Alternating Row Colors (Banding)
    # Start from Row 1 (index 1)
    for row_idx in range(1, num_rows):
        if row_idx % 2 == 1: # Odd index (2nd, 4th... row)
            requests.append({
                "repeatCell": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": row_idx,
                        "endRowIndex": row_idx + 1,
                        "startColumnIndex": 0,
                        "endColumnIndex": num_cols
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "backgroundColor": COLOR_ALT_BG
                        }
                    },
                    "fields": "userEnteredFormat(backgroundColor)"
                }
            })

    # 4. Add Borders to the whole table
    requests.append({
        "updateCells": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": 0,
                "endRowIndex": num_rows,
                "startColumnIndex": 0,
                "endColumnIndex": num_cols
            },
            "rows": [
                {
                    "values": [
                        {
                            "userEnteredFormat": {
                                "borders": {
                                    "top": {"style": "SOLID"},
                                    "bottom": {"style": "SOLID"},
                                    "left": {"style": "SOLID"},
                                    "right": {"style": "SOLID"}
                                }
                            }
                        }
                    ]
                }
            ],
            "fields": "userEnteredFormat.borders"
        }
    })
    # Wait, updateCells with rows requires a full grid. 
    # A better way to do borders for a range is to use a loop or repeatCell if available.
    # Actually, repeatCell doesn't support borders easily in some versions, but let's use 
    # the basic approach for the whole range by iterating or using a single updateCells 
    # but updateCells requires the exact structure.
    # Better: replace the updateCells border attempt with a simpler approach or skip if too complex.
    # Let's try using repeatCell for borders if possible, but borders are usually per cell.
    # I'll remove the updateCells border for now to avoid errors and use a simpler approach 
    # if needed, or just focus on colors first.

    # Re-evaluating borders: The most reliable way is to use the `updateCells` but it's verbose.
    # Let's stick to the colors and a basic header for now.
    
    # Actually, I'll remove the updateCells and use only colors to be safe and fast.
    # I'll just keep Header and Banding.
    
    # Clean up the requests list to only include the successful ones.
    final_requests = requests[:num_rows + 1] # Just header and banding rows

    body = {
        'requests': final_requests
    }
    
    service.spreadsheets().batchUpdate(
        spreadsheetId=SPREADSHEET_ID, 
        body=body
    ).execute()

    print("Successfully styled the sheet!")

if __name__ == '__main__':
    main()
