import gspread
from google.oauth2.service_account import Credentials

# Configuration
SERVICE_ACCOUNT_FILE = r'C:\Users\Loser\Desktop\-\-\automation-visitor-shindan\ageless-impulse-488713-m6-03014b3cddad.json'
SPREADSHEET_URL = 'https://docs.google.com/spreadsheets/d/1sapVRFFAHcXFwB7GRlkRp5kjFDogd7unkDNDLi9avEc/edit'
SHEET_NAME = '分析'

# The data we calculated previously
overall_data = [
    ["退職理由", "件数", "割合"],
    ["キャリア形成不安", 55, "26.96%"],
    ["働き方", 35, "17.16%"],
    ["組織運営への不満", 31, "15.20%"],
    ["業績不振", 18, "8.82%"],
    ["待遇（待遇・給与含む）", 14, "6.86%"],
    ["退職代行のため不明", 11, "5.39%"],
    ["人間関係", 9, "4.41%"],
    ["業務内容", 9, "4.41%"],
    ["結婚", 7, "3.43%"],
    ["体調不良等", 6, "2.94%"],
    ["挑戦", 5, "2.45%"],
    ["採用ミス", 3, "1.47%"],
    ["その他", 1, "0.49%"],
]

dept_data_raw = {
    "メディカル": [("キャリア形成不安", 7, "36.84%"), ("待遇", 3, "15.79%"), ("退職代行のため不明", 2, "10.53%"), ("組織運営への不満", 2, "10.53%"), ("働き方", 2, "10.53%"), ("業績不振", 1, "5.26%"), ("人間関係", 1, "5.26%"), ("結婚", 1, "5.26%")],
    "新規事業(大阪)": [("業績不振", 1, "100.00%")],
    "PL-第2G": [("キャリア形成不安", 16, "29.09%"), ("組織運営への不満", 11, "20.00%"), ("働き方", 8, "14.55%"), ("業績不振", 4, "7.27%"), ("待遇", 4, "7.27%"), ("退職代行のため不明", 3, "5.45%"), ("人間関係", 3, "5.45%"), ("業務内容", 2, "3.64%"), ("結婚", 1, "1.82%"), ("採用ミス", 1, "1.82%"), ("体調不良等", 1, "1.82%"), ("挑戦", 1, "1.82%")],
    "PL-第1G（督促）": [("業績不振", 1, "100.00%")],
    "WEBﾏｰｹﾃｨﾝｸﾞ": [("キャリア形成不安", 4, "44.44%"), ("働き方", 2, "22.22%"), ("待遇", 1, "11.11%"), ("組織運営への不満", 1, "11.11%"), ("結婚", 1, "11.11%")],
    "PL-第2G(出社無)": [("組織運営への不満", 1, "100.00%")],
    "PL-第3G": [("キャリア形成不安", 3, "42.86%"), ("働き方", 2, "28.57%"), ("業績不振", 1, "14.29%"), ("結婚", 1, "14.29%")],
    "PL-第1G": [("働き方", 12, "17.91%"), ("キャリア形成不安", 11, "16.42%"), ("組織運営への不満", 10, "14.93%"), ("業績不振", 8, "11.94%"), ("退職代行のため不明", 6, "8.96%"), ("業務内容", 5, "7.46%"), ("体調不良等", 4, "5.97%"), ("人間関係", 3, "4.48%"), ("待遇", 3, "4.48%"), ("結婚", 2, "2.99%"), ("挑戦", 2, "2.99%"), ("採用ミス", 1, "1.49%")],
    "BC": [("キャリア形成不安", 4, "30.77%"), ("働き方", 3, "23.08%"), ("組織運営への不満", 2, "15.38%"), ("人間関係", 2, "15.38%"), ("待遇", 1, "7.69%"), ("結婚", 1, "7.69%")],
    "新規事業開発部": [("働き方", 2, "25.00%"), ("業績不振", 2, "25.00%"), ("キャリア形成不安", 2, "25.00%"), ("組織運営への不満", 1, "12.50%"), ("待遇", 1, "12.50%")],
    "PL-第1G（SU）": [("組織運営への不満", 2, "40.00%"), ("キャリア形成不安", 2, "40.00%"), ("働き方", 1, "20.00%")],
    "BC大阪": [("キャリア形成不安", 2, "40.00%"), ("働き方", 1, "20.00%"), ("組織運営への不満", 1, "20.00%"), ("待遇", 1, "20.00%")],
    "メディカル-第1G": [("働き方", 1, "100.00%")],
    "WEB第2G": [("業務内容", 1, "100.00%")],
    "WEB第1G": [("キャリア形成不安", 3, "75.00%"), ("働き方", 1, "25.00%")],
    "人事部": [("挑戦", 2, "66.67%"), ("業務内容", 1, "33.33%")],
    "配属前": [("体調不良等", 1, "33.33%"), ("採用ミス", 1, "33.33%"), ("キャリア形成不安", 1, "33.33%")],
    "退職時所属": [("退職カテゴリ①", 1, "100.00%")],
}

def main():
    # Authenticate
    scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=scopes)
    client = gspread.authorize(creds)

    try:
        # Open spreadsheet
        sh = client.open_by_url(SPREADSHEET_URL)
        
        # Get or create '分析' sheet
        try:
            ws = sh.worksheet(SHEET_NAME)
        except gspread.exceptions.WorksheetNotFound:
            ws = sh.add_worksheet(title=SHEET_NAME, rows="100", cols="20")

        ws.clear()

        # --- Section 1: Overall ---
        ws.update('A1', [['【全体集計：退職理由の割合】']])
        ws.update('A2', overall_data)
        
        # --- Section 2: By Department ---
        start_row = len(overall_data) + 4
        ws.update(f'A{start_row}', [['【事業部別集計】']])
        
        dept_header = ["事業部", "退職理由", "件数", "割合"]
        ws.update(f'A{start_row+1}', [dept_header])
        
        rows_to_write = []
        for dept, reasons in dept_data_raw.items():
            for reason, count, pct in reasons:
                rows_to_write.append([dept, reason, count, pct])
        
        ws.update(f'A{start_row+2}', rows_to_write)

        # Simple formatting: Bold headers (A1, A2:C2, A_start_row, A_start_row+1:D_start_row+1)
        # Note: gspread's format method is complex, but we can use batch_update for formatting if needed.
        # For now, just writing the data.

        print("Success: Analysis sheet updated!")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
