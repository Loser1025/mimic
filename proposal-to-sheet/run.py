"""
提案日=今日 で指定ドメインを検索 → 相談者一覧CSV取得 → スプレッドシートに貼り付け

対象シート: 【PL】速報結果シート > daily分析（AMUGI / honoka / thank）
貼り付け先: P列～Z列（P1:Z1のヘッダーに一致する列のみ）

使い方:
  python run.py                    # hibiki（デフォルト）
  python run.py --domain honoka    # honoka
  python run.py --domain thank     # thank
  python run.py --domain hibiki 2026/03/19  # 日付指定も可
"""

import csv
import io
import json
import re
import sys
from datetime import datetime
from pathlib import Path

import requests
from google.oauth2 import service_account
from googleapiclient.discovery import build

# ── ドメイン設定 ───────────────────────────────────────
DOMAIN_CONFIG = {
    'hibiki': {
        'base_url': 'https://hibiki.leaduplus.pro',
        'sheet_name': 'daily分析（AMUGI）',
        'login_id': None,  # config.json から読む
        'login_pw': None,
    },
    'honoka': {
        'base_url': 'https://honoka.leaduplus.pro',
        'sheet_name': 'daily分析（honoka）',
        'login_id': 'n.ikeuchi',
        'login_pw': 'jR#MEF9t8fdP',
    },
    'thank': {
        'base_url': 'https://thank.leaduplus.pro',
        'sheet_name': 'daily分析（thank） ',
        'login_id': 'thank_help2',
        'login_pw': 't4$aqKoxjGRr',
    },
}

SPREADSHEET_ID = '1SXM-kKPu1nuq0sZKrsl-m_O2vmNl-HyJ9TrYtRi2Xrs'
DATA_START_COL = 'P'   # P列 = 16列目
DATA_START_ROW = 2

CONFIG_PATH = Path(__file__).parent.parent / 'csv-to-sheet' / 'config.json'
SA_PATH = Path(__file__).parent.parent / 'csv-to-sheet' / 'sa_credentials.json'

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                  '(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'ja,en-US;q=0.7,en;q=0.3',
}


# ── ログイン ──────────────────────────────────────────
def _csrf(html: str) -> str:
    m = re.search(r'name="_token"[^>]*value="([^"]+)"', html)
    if not m:
        raise ValueError('CSRFトークン取得失敗')
    return m.group(1)


def login(base_url: str, login_id: str, login_pw: str) -> requests.Session:
    session = requests.Session()
    session.headers.update(HEADERS)
    page = session.get(f'{base_url}/debt/login', timeout=30)
    page.raise_for_status()
    token = _csrf(page.text)
    res = session.post(
        f'{base_url}/debt/login',
        data={'_token': token, 'name': login_id, 'password': login_pw},
        allow_redirects=True,
        timeout=30,
    )
    if 'name="_token"' in res.text and '/debt/login' in res.url:
        raise ValueError('ログイン失敗: IDまたはパスワードが違います')
    return session


# ── CSV ダウンロード（相談者一覧） ───────────────────
def download_consulter_csv(session: requests.Session, base_url: str, date_str: str) -> str:
    """
    提案日=date_str でフィルタして相談者一覧CSVをダウンロード。
    date_str: 'YYYY/MM/DD' 形式
    """
    search_res = session.get(f'{base_url}/debt/consulter/list/search', timeout=30)
    search_res.raise_for_status()
    token = _csrf(search_res.text)

    csv_res = session.post(
        f'{base_url}/debt/consulter/list/outputCsv',
        data={
            '_token': token,
            'proposal_date_from': date_str,
            'proposal_date_to': date_str,
            'except_test_inquiry': '1',
            'limit': '1000',
            'total_count': '0',
        },
        timeout=60,
    )
    csv_res.raise_for_status()

    # Content-Type が HTML ならエラーページ
    ct = csv_res.headers.get('Content-Type', '')
    if 'html' in ct:
        raise ValueError(f'CSVの取得に失敗しました（HTMLが返されました）\nURL: {csv_res.url}')

    csv_res.encoding = csv_res.apparent_encoding or 'utf-8-sig'
    return csv_res.text


# ── CSV パース ────────────────────────────────────────
def parse_csv(text: str):
    """CSVテキスト → (headers list, rows list of list)"""
    text = text.lstrip('\ufeff')
    reader = csv.reader(io.StringIO(text))
    headers = next(reader)
    rows = list(reader)
    return headers, rows


# ── Google Sheets ─────────────────────────────────────
def build_sheets_service():
    creds = service_account.Credentials.from_service_account_file(
        str(SA_PATH),
        scopes=['https://www.googleapis.com/auth/spreadsheets'],
    )
    return build('sheets', 'v4', credentials=creds)


def list_sheet_names(service) -> list:
    """スプレッドシート内の全シート名を取得"""
    meta = service.spreadsheets().get(spreadsheetId=SPREADSHEET_ID).execute()
    return [s['properties']['title'] for s in meta.get('sheets', [])]


def get_sheet_headers(service, sheet_name: str) -> list:
    """P1:Z1 のヘッダーを取得"""
    # シート名が存在するか事前確認
    available = list_sheet_names(service)
    if sheet_name not in available:
        print(f'ERROR: シート "{sheet_name}" が見つかりません。')
        print(f'利用可能なシート一覧:')
        for s in available:
            print(f'  - {repr(s)}')
        raise ValueError(f'シート "{sheet_name}" が存在しません')

    header_range = f"'{sheet_name}'!P1:Z1"
    result = service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=header_range,
    ).execute()
    return result.get('values', [[]])[0]


def col_letter_to_index(letter: str) -> int:
    """P → 15（0始まり）"""
    result = 0
    for ch in letter.upper():
        result = result * 26 + (ord(ch) - ord('A') + 1)
    return result - 1


def index_to_col_letter(idx: int) -> str:
    """15（0始まり）→ P"""
    result = ''
    n = idx + 1
    while n > 0:
        n, rem = divmod(n - 1, 26)
        result = chr(ord('A') + rem) + result
    return result


def write_to_sheet(service, sheet_name: str, sheet_headers: list, csv_headers: list, csv_rows: list) -> int:
    """
    sheet_headers（P1:Z1）に対応するCSV列を抽出してシートに貼り付け。
    既存データ（P2以降）はクリアしてから書き込む。
    """
    start_col_idx = col_letter_to_index(DATA_START_COL)  # P=15

    # シートヘッダー → CSVヘッダーのインデックスマッピング
    col_map = []  # (sheet_col_idx, csv_col_idx) のリスト（空ヘッダーはスキップ）
    for i, sh in enumerate(sheet_headers):
        sh = sh.strip()
        if not sh:
            col_map.append((i, None))
            continue
        # CSVヘッダーと完全一致を探す
        csv_idx = None
        for j, ch in enumerate(csv_headers):
            if ch.strip() == sh:
                csv_idx = j
                break
        col_map.append((i, csv_idx))

    # マッピング確認
    print(f'\n■ ヘッダーマッピング (P1:Z1):')
    for i, (sh_i, csv_i) in enumerate(col_map):
        col_letter = index_to_col_letter(start_col_idx + sh_i)
        sh_name = sheet_headers[sh_i].strip() if sh_i < len(sheet_headers) else ''
        if not sh_name:
            print(f'  {col_letter}: (空欄) → スキップ')
        elif csv_i is not None:
            print(f'  {col_letter}: "{sh_name}" → CSV列[{csv_i}] "{csv_headers[csv_i]}"')
        else:
            print(f'  {col_letter}: "{sh_name}" → ★未一致（CSV側に列なし）')

    if not csv_rows:
        print('\n対象データが0件でした（提案日=今日のデータなし）')
        return 0

    # 書き込む列範囲を確定
    num_sheet_cols = len(sheet_headers)  # = 11 (P~Z)
    end_col_letter = index_to_col_letter(start_col_idx + num_sheet_cols - 1)
    clear_range = f"'{sheet_name}'!{DATA_START_COL}{DATA_START_ROW}:{end_col_letter}"

    # クリア
    service.spreadsheets().values().clear(
        spreadsheetId=SPREADSHEET_ID,
        range=clear_range,
    ).execute()
    print(f'\n[クリア] {clear_range}')

    # 書き込みデータ作成
    write_rows = []
    for row in csv_rows:
        out_row = []
        for _, csv_i in col_map:
            if csv_i is not None and csv_i < len(row):
                out_row.append(row[csv_i])
            else:
                out_row.append('')
        write_rows.append(out_row)

    write_range = f"'{sheet_name}'!{DATA_START_COL}{DATA_START_ROW}"
    service.spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID,
        range=write_range,
        valueInputOption='RAW',
        body={'values': write_rows},
    ).execute()

    return len(write_rows)


# ── 1ドメイン処理 ─────────────────────────────────────
def run_one_domain(domain: str, today: str, service, hibiki_cfg: dict) -> str:
    """
    1ドメイン分を処理してログ文字列を返す。
    service: 使い回しの Sheets サービスオブジェクト
    hibiki_cfg: config.json の内容（hibiki のみ使用）
    戻り値: '完了 N件' または 'エラー: ...' のステータス文字列
    """
    dcfg = DOMAIN_CONFIG[domain]
    base_url = dcfg['base_url']
    sheet_name = dcfg['sheet_name']
    login_id = dcfg['login_id']
    login_pw = dcfg['login_pw']

    if domain == 'hibiki':
        login_id = login_id or hibiki_cfg.get('login_id', '')
        login_pw = login_pw or hibiki_cfg.get('login_pw', '')

    print(f'\n{"="*50}')
    print(f'[{domain}] 開始 → シート: {sheet_name}')
    print(f'{"="*50}')

    try:
        # 1. ログイン
        print(f'  ログイン中 ({login_id})...')
        session = login(base_url, login_id, login_pw)
        print('  ログイン成功')

        # 2. CSV ダウンロード
        print(f'  CSV取得中 (提案日={today})...')
        csv_text = download_consulter_csv(session, base_url, today)
        session.close()  # セッションをすぐ解放

        csv_headers, csv_rows = parse_csv(csv_text)
        print(f'  CSV: {len(csv_rows)}件 / {len(csv_headers)}列')

        if not csv_rows:
            print('  対象データ0件')
            return '0件（データなし）'

        # 3. シートヘッダー取得 → 書き込み
        sheet_headers = get_sheet_headers(service, sheet_name)
        count = write_to_sheet(service, sheet_name, sheet_headers, csv_headers, csv_rows)
        return f'完了 {count}件'

    except Exception as e:
        print(f'  ERROR: {e}')
        return f'エラー: {e}'


# ── メイン ────────────────────────────────────────────
def main():
    # コマンドライン引数: [--domain <domain>] [<YYYY/MM/DD>]
    # --domain を省略すると全ドメインを順番に処理
    args = sys.argv[1:]
    target_domains = None  # None = 全ドメイン
    date_arg = None

    i = 0
    while i < len(args):
        if args[i] == '--domain' and i + 1 < len(args):
            target_domains = [args[i + 1]]
            i += 2
        else:
            date_arg = args[i]
            i += 1

    if target_domains and target_domains[0] not in DOMAIN_CONFIG:
        print(f'ERROR: 不明なドメイン "{target_domains[0]}"。指定可能: {list(DOMAIN_CONFIG.keys())}')
        sys.exit(1)

    domains = target_domains if target_domains else list(DOMAIN_CONFIG.keys())
    today = date_arg if date_arg else datetime.now().strftime('%Y/%m/%d')

    print(f'対象日: {today}')
    print(f'処理ドメイン: {domains}')

    # hibiki の config.json を先読み
    hibiki_cfg = {}
    if CONFIG_PATH.exists():
        hibiki_cfg = json.loads(CONFIG_PATH.read_text(encoding='utf-8'))

    # Google Sheets サービスは1回だけ初期化して使い回す
    print('\nGoogle Sheetsに接続中...')
    service = build_sheets_service()

    # 全ドメインを順番に処理
    results = {}
    for domain in domains:
        results[domain] = run_one_domain(domain, today, service, hibiki_cfg)

    # サマリー表示
    print(f'\n{"="*50}')
    print(f'■ 処理完了サマリー ({today})')
    print(f'{"="*50}')
    for domain, status in results.items():
        sheet_name = DOMAIN_CONFIG[domain]['sheet_name']
        print(f'  {domain:10s} [{sheet_name}] → {status}')


if __name__ == '__main__':
    main()
