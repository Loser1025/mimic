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
        # Handle cases where days_str might be float or have decimals
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
        
        # Count occurrences: { (major_dept, category, reason): count }
        counts = defaultdict(int)
        
        for row in raw_data[1:]: # skip header
            if len(row) < 12: continue
            
            dept_raw = row[2]
            days_raw = row[6]
            reason_raw = row[11]
            
            major_dept = get_major_dept(dept_raw)
            category = get_service_category(days_raw)
            
            # Normalize and split reasons
            reasons = [p.strip() for p in reason_raw.split(',') if p.strip()]
            
            if category:
                for r in reasons:
                    if "待遇" in r: r = "待遇"
                    # Count for specific major dept
                    counts[(major_dept, category, r)] += 1
                    # Count for overall
                    counts[("全体", category, r)] += 1

        # Map Target Sheet cells and prepare updates
        major_depts_to_fill = ["全体", "PL合計", "BC合計", "WEB合計", "メディカル合計", "人事", "新規事業合計", "その他"]
        
        updates = [] # list of (range, value)
        
        for r_idx, row in enumerate(target_data):
            # Find block headers (e.g., '全体', 'PL合計')
            for dept in major_depts_to_fill:
                if dept in row:
                    # Found header. Identify reason columns.
                    reason_col_map = {}
                    for c_idx, cell in enumerate(row):
                        if cell and cell != dept and cell != '':
                            reason_col_map[cell] = c_idx + 1 # 1-indexed
                    
                    # Category mapping: name -> offset from header row
                    category_offsets = {
                        '1000日以上': 1,
                        '500日~999日': 2,
                        '499日以下': 3,
                        '365日以下': 4
                    }
                    
                    for cat_name, offset in category_offsets.items():
                        curr_row_idx = r_idx + offset
                        if curr_row_idx >= len(target_data): continue
                        
                        # Only update if the row label matches the category
                        if cat_name in target_data[curr_row_idx]:
                            for reason, col in reason_col_map.items():
                                val = counts[(dept, cat_name, reason)]
                                # Store cell address and value
                                updates.append((gspread.utils.rowcol_to_a1(curr_row_idx + 1, col), val))
        
        # Execute updates
        print(f"Starting update of {len(updates)} cells...")
        for cell_range, value in updates:
            ws_target.update(cell_range, [[value]])
        
        print(f"Success: All {len(updates)} cells have been updated in {TARGET_SHEET_NAME}!")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
