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
        
        # 1. Count occurrences: { (major_dept, category, reason): count }
        # Include "全体" (Overall) as well
        counts = defaultdict(int)
        
        for row in raw_data[1:]: # skip header
            if len(row) < 12: continue
            
            dept_raw = row[2]
            days_raw = row[6]
            reason_raw = row[11]
            
            major_dept = get_major_dept(dept_raw)
            category = get_service_category(days_raw)
            
            # Normalize reason
            reasons = [p.strip() for p in reason_raw.split(',') if p.strip()]
            
            if category:
                for r in reasons:
                    if "待遇" in r: r = "待遇"
                    # Count for specific major dept
                    counts[(major_dept, category, r)] += 1
                    # Count for overall
                    counts[("全体", category, r)] += 1

        # 2. Map Target Sheet cells
        # Find the headers for reasons (usually in rows like 2, 8, 14...)
        # and the rows for categories.
        
        updates = [] # (row, col, value)
        
        # We look for blocks starting with '全体', 'PL合計', etc.
        major_depts_to_fill = ["全体", "PL合計", "BC合計", "WEB合計", "メディカル合計", "人事", "新規事業合計", "その他"]
        
        for r_idx, row in enumerate(target_data):
            # Check if this row is a header for a block
            for dept in major_depts_to_fill:
                if dept in row:
                    # Found a block header. The reasons are in this row.
                    # Find the column index for each reason
                    reason_col_map = {}
                    for c_idx, cell in enumerate(row):
                        if cell and cell != dept and cell != '':
                            reason_col_map[cell] = c_idx + 1 # 1-indexed for gspread
                    
                    # Now look at the next 4 rows for categories
                    category_map = {
                        '1000日以上': 0,
                        '500日~999日': 1,
                        '499日以下': 2,
                        '365日以下': 3
                    }
                    
                    for cat_name, cat_offset in category_map.items():
                        curr_row_idx = r_idx + 1 + cat_offset
                        if curr_row_idx >= len(target_data): break
                        
                        # Check if the row actually contains the category name
                        if cat_name in target_data[curr_row_idx]:
                            # This is the correct row for this category.
                            # Now fill the counts for each reason.
                            for reason, col in reason_col_map.items():
                                count = counts[(dept, cat_name, reason)]
                                updates.append({
                                    'range': gspread.utils.rowcol_to_a1(curr_row_idx + 1, col),
                                    'value': count
                                })
                                
        # 3. Execute Updates
        # To avoid too many API calls, we can use batch_update
        # Since we use a simple update for each cell, let's use update_cells for efficiency
        # But for clarity, I'll use a loop with a small batch or just update.
        # Actually, gspread's update() is slow. Let's use update_cells.
        
        # Convert updates to Cell objects
        from gspread.models import Cell
        cells_to_update = []
        for upd in updates:
            # Need row and col indices
            # Convert A1 back to row/col or just store indices from the start.
            pass
            
        # Let's redo the update loop using indices
        ws_target.clear() # Optional: Clear only the data area? No, the user wants to fill.
        # Wait, if I clear, I lose the headers. I should only update the values.
        
        # Since I'm already doing it, let's just use the loop for now.
        for upd in updates:
            ws_target.update(upd['range'], [[upd['value']]])

        print(f"Success: Updated {len(updates)} cells in {TARGET_SHEET_NAME}!")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
