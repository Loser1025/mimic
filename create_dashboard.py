import gspread
from google.oauth2.service_account import Credentials
from collections import Counter, defaultdict

# Configuration
SERVICE_ACCOUNT_FILE = r'C:\Users\Loser\Desktop\-\-\automation-visitor-shindan\ageless-impulse-488713-m6-03014b3cddad.json'
SPREADSHEET_URL = 'https://docs.google.com/spreadsheets/d/1sapVRFFAHcXFwB7GRlkRp5kjFDogd7unkDNDLi9avEc/edit'
ANALYSIS_SHEET = '分析'
DASHBOARD_SHEET = 'ダッシュボード'

def get_visual_bar(percentage_str):
    """ percentage string (e.g., '26.96%') to a visual bar '■■■□□' """
    try:
        val = float(percentage_str.strip('%'))
        filled = int(val / 10) # 1 block per 10%
        return '■' * filled + '□' * (10 - filled)
    except:
        return '□' * 10

def main():
    scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=scopes)
    client = gspread.authorize(creds)

    try:
        sh = client.open_by_url(SPREADSHEET_URL)
        
        # Read data from Analysis sheet
        ws_analysis = sh.worksheet(ANALYSIS_SHEET)
        all_values = ws_analysis.get_all_values()
        
        # --- Parse Overall Data ---
        overall_table = []
        overall_start = -1
        for i, row in enumerate(all_values):
            if '【全体集計' in row[0]:
                overall_start = i + 2
                break
        
        # Find where overall table ends (empty row or next section)
        overall_end = overall_start
        while overall_end < len(all_values) and all_values[overall_end] and '【事業部別' not in all_values[overall_end][0]:
            overall_table.append(all_values[overall_end])
            overall_end += 1
        
        # --- Parse Dept Data ---
        dept_matrix = defaultdict(dict)
        all_reasons = set()
        
        dept_start = -1
        for i, row in enumerate(all_values):
            if '【事業部別集計】' in row[0]:
                dept_start = i + 2
                break
        
        if dept_start != -1:
            for row in all_values[dept_start:]:
                if len(row) >= 4 and row[0] and row[1]:
                    dept = row[0]
                    reason = row[1]
                    pct = row[3]
                    dept_matrix[dept][reason] = pct
                    all_reasons.add(reason)

        sorted_reasons = sorted(list(all_reasons), key=lambda x: (overall_table[0] if not overall_table else 0)) # simplistic
        # Better: Sort reasons based on overall ranking
        reason_rank = {row[0]: i for i, row in enumerate(overall_table) if len(row)>0}
        sorted_reasons = sorted(list(all_reasons), key=lambda x: reason_rank.get(x, 999))

        # --- Prepare Dashboard Layout ---
        ws_dash = None
        try:
            ws_dash = sh.worksheet(DASHBOARD_SHEET)
        except gspread.exceptions.WorksheetNotFound:
            ws_dash = sh.add_worksheet(title=DASHBOARD_SHEET, rows="100", cols="20")

        ws_dash.clear()

        # 1. Main Header
        ws_dash.update('A1', [['🚀 離職理由分析 エグゼクティブ・ダッシュボード']])

        # 2. Summary Block
        summary_rows = [
            ['【要約サマリー】', '', ''],
            ['最重要課題理由', overall_table[0][0] if overall_table else 'N/A', '→ 全体の最頻出理由です'],
            ['重点対策部署', 'PL-第1G / PL-第2G', '→ 離職件数および理由の多様性が高い部署です'],
            ['主要離職要因', 'キャリア形成不安・働き方', '→ 組織的なキャリアパス提示と環境改善が急務です'],
        ]
        ws_dash.update('A3', summary_rows)

        # 3. Overall Ranking with Visual Bar
        ranking_header = ['退職理由', '件数', '割合', '視覚的比率']
        ranking_data = []
        for row in overall_table:
            if len(row) >= 3 and row[0] != '退職理由':
                ranking_data.append([row[0], row[1], row[2], get_visual_bar(row[2])])
        
        ws_dash.update('A7', [['【全体ランキング】']])
        ws_dash.update('A8', [ranking_header])
        ws_dash.update('A9', ranking_data)

        # 4. Department Matrix (The most powerful part)
        matrix_start_col = 5 # Column E
        matrix_header = ['事業部'] + sorted_reasons
        ws_dash.update(f'E7', [['【部署別・理由別マトリクス】']])
        ws_dash.update(f'E8', [matrix_header])
        
        matrix_rows = []
        for dept in sorted(dept_matrix.keys()):
            row = [dept]
            for r in sorted_reasons:
                row.append(dept_matrix[dept].get(r, '0%'))
            matrix_rows.append(row)
        
        ws_dash.update(f'E9', matrix_rows)

        # 5. Insights & Actions
        insight_start_row = max(9 + len(ranking_data), 9 + len(matrix_rows)) + 3
        insight_rows = [
            ['【インサイトと推奨アクション】', '', ''],
            ['1. キャリアパスの可視化', '全社的に「キャリア形成不安」が最多。', '職能要件定義書の作成と、個別のキャリア面談を強化。'],
            ['2. 労働環境の改善', 'PL-第1Gにおいて「働き方」の不満が顕著。', '業務量の平準化と、定時退社を推奨する文化への転換を検討。'],
            ['3. 早期離職防止', '配属前・新卒期の「採用ミス・体調不良」が見られる。', 'オンボーディングプロセスの見直しと、メンタルケア体制の構築。'],
        ]
        ws_dash.update(f'A{insight_start_row}', insight_rows)

        print("Success: Dashboard sheet created!")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
