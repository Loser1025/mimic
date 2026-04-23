import gspread
import gspread.utils
from google.oauth2.service_account import Credentials

# Credentials path
SERVICE_ACCOUNT_FILE = r'C:\Users\Loser\Desktop\-\-\automation-visitor-shindan\ageless-impulse-488713-m6-03014b3cddad.json'
SPREADSHEET_ID = '1sapVRFFAHcXFwB7GRlkRp5kjFDogd7unkDNDLi9avEc'
TARGET_GID = 709002610

def extract_number(s):
    """ '13 (9.7%)' や '1,000' から数値 13.0 や 1000.0 を抽出する """
    if not s: return None
    # '(' があればそれより前を、なければそのまま
    clean_s = s.split('(')[0].split(' ')[0].replace(',', '').strip()
    try:
        return float(clean_s)
    except ValueError:
        return None

def main():
    try:
        # Auth
        scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
        creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=scopes)
        gc = gspread.authorize(creds)

        # Open spreadsheet
        ss = gc.open_by_key(SPREADSHEET_ID)

        # Find sheet by GID
        worksheet = None
        for ws in ss.worksheets():
            if ws.id == TARGET_GID:
                worksheet = ws
                break

        if not worksheet:
            print("Error: Target worksheet with GID not found.")
            return

        # Read all data
        data = worksheet.get_all_values()
        rows = len(data)
        if rows == 0:
            print("Error: Sheet is empty.")
            return
        cols = len(data[0])

        # Identify division blocks
        divisions = []
        for i in range(rows):
            cell_value = data[i][1] if len(data[i]) > 1 else ""
            # 「合計」「全体」に加えて「人事」もヘッダーとして認識させる
            if cell_value and (isinstance(cell_value, str) and 
                               ("合計" in cell_value or cell_value == "全体" or cell_value == "人事")):
                divisions.append({
                    "headerRow": i,
                    "startRow": i + 1,
                    "endRow": i + 4
                })

        if not divisions:
            print("Error: No division headers found in Column B.")
            return

        # Process each division
        for div in divisions:
            div_total = 0
            # Sum values in division block (Row startRow to endRow, Col C onwards)
            for r in range(div["startRow"], min(div["endRow"] + 1, rows)):
                for c in range(2, cols):
                    val_str = data[r][c] if len(data[r]) > c else ""
                    num = extract_number(val_str)
                    if num is not None:
                        div_total += num

            if div_total == 0:
                print(f"Skipping division at row {div['headerRow']+1} due to zero total.")
                continue

            # Prepare updates
            updates = []
            for r in range(div["startRow"], min(div["endRow"] + 1, rows)):
                for c in range(2, cols):
                    val_str = data[r][c] if len(data[r]) > c else ""
                    if not val_str: continue
                    
                    num = extract_number(val_str)
                    if num is not None:
                        percent = (num / div_total) * 100
                        display_num = int(num) if num.is_integer() else num
                        new_val = f"{display_num} ({percent:.1f}%)"
                        
                        range_a1 = gspread.utils.rowcol_to_a1(r + 1, c + 1)
                        updates.append({
                            'range': range_a1,
                            'values': [[new_val]]
                        })
            
            if updates:
                worksheet.batch_update(updates)
                print(f"Updated division at row {div['headerRow']+1} with {len(updates)} cells.")

        print("Successfully updated all percentages, including '人事'.")

    except Exception as e:
        print(f"An unexpected error occurred: {e}")

def typeof_check(val):
    return type(val).__name__

if __name__ == '__main__':
    main()
