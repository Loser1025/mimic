import gspread
from google.oauth2.credentials import Credentials
import json
from datetime import datetime

# Configuration
TOKEN_FILE = r'C:\Users\Loser\Desktop\-\-\nurse_list_deploy\token.json'
SPREADSHEET_URL = 'https://docs.google.com/spreadsheets/d/1sapVRFFAHcXFwB7GRlkRp5kjFDogd7unkDNDLi9avEc/edit'
RAW_SHEET_NAME = '退職者管理(2504~2604'
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
        
        # 1. Check Target Sheet (勤続年数別)
        try:
            ws_target = sh.worksheet(TARGET_SHEET_NAME)
            target_data = ws_target.get_all_values()
            print(f"--- Target Sheet: {TARGET_SHEET_NAME} ---")
            for row in target_data[:15]: # Print first 15 rows to understand structure
                print(row)
        except gspread.exceptions.WorksheetNotFound:
            print(f"Error: Sheet {TARGET_SHEET_NAME} not found.")
            return

        # 2. Check Raw Data Sheet (退職者管理(2504~2604)
        try:
            ws_raw = sh.worksheet(RAW_SHEET_NAME)
            raw_data = ws_raw.get_all_values()
            print(f"\n--- Raw Sheet: {RAW_SHEET_NAME} (Header) ---")
            print(raw_data[0]) # Print header
            print(f"Total rows: {len(raw_data)}")
        except gspread.exceptions.WorksheetNotFound:
            print(f"Error: Sheet {RAW_SHEET_NAME} not found.")
            return

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
