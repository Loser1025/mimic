import gspread
from google.oauth2.credentials import Credentials
import json
from collections import Counter, defaultdict

# Configuration
TOKEN_FILE = r'C:\Users\Loser\Desktop\-\-\nurse_list_deploy\token.json'
SPREADSHEET_URL = 'https://docs.google.com/spreadsheets/d/1sapVRFFAHcXFwB7GRlkRp5kjFDogd7unkDNDLi9avEc/edit'
RAW_SHEET_NAME = '退職者管理(2504~2604'
TARGET_SHEET_NAME = '勤続年数別'

def get_major_dept(dept_name):
    if not dept_name: return "その他"
    if dept_name.startswith("BC"): return "BC合計"
    if dept_name.startswith("PL"): return "PL合計"
    if dept_name.startswith("WEB"): return "WEB合計"
    if dept_name.startswith("メディカル"): return "メディカル合計"
    if "人事部" in dept_name: return "人事"
    if dept_name.startswith("新規事業"): return "新規事業合計"
    return "その他"

def get_service_category(days_str):
    try:
        days = int(float(days_str))
        if days >= 1000: return '1000日以上'
        if days >= 500: return '500日~999日'
        if days >= 366: return '499日以下'
        return '365日以下'
    except:
        return None

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
        ws_raw = sh.worksheet(RAW_SHEET_NAME)
        ws_target = sh.worksheet(TARGET_SHEET_NAME)
        
        raw_data = ws_raw.get_all_values()
        target_data = ws_target.get_all_values()
        
        # Count occurrences
        counts = defaultdict(int)
        for row in raw_data[1:]:
            if len(row) < 12: continue
            dept = get_major_dept(row[2])
            category = get_service_category(row[6])
            reasons = [p.strip() for p in row[11].split(',') if p.strip()]
            if category:
                for r in reasons:
                    if "待遇" in r: r = "待遇"
                    counts[(dept, category, r)] += 1
                    counts[("全体", category, r)] += 1

        major_depts_to_fill = ["全体", "PL合計", "BC合計", "WEB合計", "メディカル合計", "人事", "新規事業合計", "その他"]
        
        # Find block boundaries and update in chunks
        for r_idx, row in enumerate(target_data):
            for dept in major_depts_to_fill:
                if dept in row:
                    # Identify reason columns
                    reason_cols = []
                    for c_idx, cell in enumerate(row):
                        if cell and cell != dept and cell != '':
                            reason_cols.append((cell, c_idx + 1))
                    
                    category_map = {
                        '1000日以上': 1,
                        '500日~999日': 2,
                        '499日以下': 3,
                        '365日以下': 4
                    }
                    
                    # Prepare a 2D array for the 4xN block of values
                    block_values = []
                    for cat_name, offset in category_map.items():
                        curr_row_idx = r_idx + offset
                        if curr_row_idx >= len(target_data): break
                        
                        row_values = []
                        # We need to update only the cells that correspond to reasons.
                        # To update a range, we must include all cells in that range.
                        # Let's just update individual rows for each category.
                        
                        # Instead of a block, we'll update one row at a time (4 rows per dept).
                        # This reduces 364 calls to ~32 calls (8 depts * 4 categories).
                        
                        # Find the range: from the first reason col to the last reason col
                        start_col = reason_cols[0][1]
                        end_col = reason_cols[-1][1]
                        
                        # Get existing row data to preserve non-reason cells
                        target_row = target_data[curr_row_idx]
                        # Ensure target_row is long enough
                        while len(target_row) < end_col:
                            target_row.append('')
                        
                        # Update only reason cells
                        for reason, col_idx in reason_cols:
                            target_row[col_idx - 1] = counts[(dept, category_map.get(target_data[curr_row_idx][1], ''), reason)]
                            # Wait, the loop above uses cat_name.
                            # Let's use the current category being processed.
                            target_row[col_idx - 1] = counts[(dept, cat_name, reason)]
                        
                        # Convert to gspread range
                        range_label = f"{gspread.utils.rowcol_to_a1(curr_row_idx + 1, start_col)}:{gspread.utils.rowcol_to_a1(curr_row_idx + 1, end_col)}"
                        # Extract only the slice of values we want to update
                        update_vals = [target_row[start_col-1 : end_col]]
                        ws_target.update(range_label, update_vals)
                        print(f"Updated {dept} - {cat_name}")

        print("Success: All categories updated!")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
