"""
面談日=今日 で指定4拠点を検索 → 相談者一覧CSV取得 → スプレッドシートに貼り付け

貼り付け先: スプレッドシートを自動スキャンして各事務所の位置を検出
  - シート内にドメイン名（hibiki / honoka / aegislo / thank）またはオフィス名が
    記載されたラベルがあり、その近くにCSV列名と一致するヘッダー行があると仮定

使い方:
  python run_mendan.py                     # 全事務所（今日の面談日）
  python run_mendan.py --domain hibiki     # hibikiのみ
  python run_mendan.py 2026/03/22          # 日付指定
  python run_mendan.py --scan              # 自動検出結果だけ確認（書き込みなし）

  python run_mendan.py --mitenca           # 未転化モード（hibikiのみ・面談予約日フィルタ）
  python run_mendan.py --mitenca 2026/03/22
"""

import csv
import io
import json
import os
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
        'login_id': None,   # config.json から読む
        'login_pw': None,
        'keywords': ['hibiki', '響', 'amugi'],
    },
    'honoka': {
        'base_url': 'https://honoka.leaduplus.pro',
        'login_id': 'n.ikeuchi',
        'login_pw': 'jR#MEF9t8fdP',
        'keywords': ['honoka', '穂', 'ほのか'],
    },
    'aegislo': {
        'base_url': 'https://aegislo.leaduplus.pro',
        'login_id': 'help7',
        'login_pw': 'Msn8mk1dV\\',
        'keywords': ['aegislo', 'アジスロ', 'aegis'],
    },
    'thank': {
        'base_url': 'https://thank.leaduplus.pro',
        'login_id': 'thank_help2',
        'login_pw': 't4$aqKoxjGRr',
        'keywords': ['thank', 'サンク'],
    },
}

SPREADSHEET_ID = '13cK3BhIxFot0cZilbDHa4dzZoH_tocmNYWEk-pTnkJo'
TARGET_GID     = 2037838844   # URLのgid → シート特定用

# ── 未転化モード設定 ──────────────────────────────────
MITENCA_SS_ID  = '13cK3BhIxFot0cZilbDHa4dzZoH_tocmNYWEk-pTnkJo'
MITENCA_GID    = 743925757
MITENCA_HEADER_ROW = 1   # ヘッダーは1行目
MITENCA_DATA_ROW   = 2   # データは2行目から

# --- aegislo 認証情報は config_mendan.json で上書き可能 ---
# config_mendan.json 例:
# {
#   "aegislo": {"login_id": "xxxx", "login_pw": "yyyy"},
#   "hibiki":  {"login_id": "xxxx", "login_pw": "yyyy"}
# }
CONFIG_MENDAN_PATH = Path(__file__).parent / 'config_mendan.json'
CONFIG_PATH        = Path(__file__).parent.parent / 'csv-to-sheet' / 'config.json'
SA_PATH            = Path(__file__).parent.parent / 'csv-to-sheet' / 'sa_credentials.json'

HTTP_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                  '(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'ja,en-US;q=0.7,en;q=0.3',
}


# ── 設定読み込み ──────────────────────────────────────
def load_credentials(hibiki_cfg: dict):
    """config_mendan.json / config.json から認証情報を補完"""
    extra = {}
    if CONFIG_MENDAN_PATH.exists():
        extra = json.loads(CONFIG_MENDAN_PATH.read_text(encoding='utf-8'))

    for domain, dcfg in DOMAIN_CONFIG.items():
        src = extra.get(domain, {})
        if not dcfg['login_id']:
            dcfg['login_id'] = src.get('login_id', '')
        if not dcfg['login_pw']:
            dcfg['login_pw'] = src.get('login_pw', '')

    # hibiki は既存 config.json も参照
    if not DOMAIN_CONFIG['hibiki']['login_id']:
        DOMAIN_CONFIG['hibiki']['login_id'] = hibiki_cfg.get('login_id', '')
        DOMAIN_CONFIG['hibiki']['login_pw'] = hibiki_cfg.get('login_pw', '')


# ── ログイン ──────────────────────────────────────────
def _csrf(html: str) -> str:
    m = re.search(r'name="_token"[^>]*value="([^"]+)"', html)
    if not m:
        raise ValueError('CSRFトークン取得失敗')
    return m.group(1)


def login(base_url: str, login_id: str, login_pw: str) -> requests.Session:
    session = requests.Session()
    session.headers.update(HTTP_HEADERS)
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


# ── CSV ダウンロード（面談日フィルタ） ───────────────
def download_mendan_csv(session: requests.Session, base_url: str, date_str: str) -> str:
    """
    面談日=date_str でフィルタして相談者一覧CSVをダウンロード。
    date_str: 'YYYY/MM/DD' 形式
    """
    search_res = session.get(f'{base_url}/debt/consulter/list/search', timeout=30)
    search_res.raise_for_status()
    token = _csrf(search_res.text)

    csv_res = session.post(
        f'{base_url}/debt/consulter/list/outputCsv',
        data={
            '_token': token,
            'interview_date_from': date_str,   # 面談日（から）
            'interview_date_to':   date_str,   # 面談日（まで）
            'except_test_inquiry': '1',
            'limit': '1000',
            'total_count': '0',
        },
        timeout=60,
    )
    csv_res.raise_for_status()

    ct = csv_res.headers.get('Content-Type', '')
    if 'html' in ct:
        raise ValueError(f'CSVの取得に失敗しました（HTMLが返されました）\nURL: {csv_res.url}')

    csv_res.encoding = csv_res.apparent_encoding or 'utf-8-sig'
    return csv_res.text


# ── CSV ダウンロード（面談予約日フィルタ） ─────────────
def download_yoyaku_csv(session: requests.Session, base_url: str, date_str: str) -> str:
    """
    面談予約日=date_str でフィルタして相談者一覧CSVをダウンロード。
    date_str: 'YYYY/MM/DD' 形式
    """
    search_res = session.get(f'{base_url}/debt/consulter/list/search', timeout=30)
    search_res.raise_for_status()
    token = _csrf(search_res.text)

    csv_res = session.post(
        f'{base_url}/debt/consulter/list/outputCsv',
        data={
            '_token': token,
            'pre_delegation_date_from': date_str,   # 面談予約日（から）
            'pre_delegation_date_to':   date_str,   # 面談予約日（まで）
            'except_test_inquiry': '1',
            'limit': '1000',
            'total_count': '0',
        },
        timeout=60,
    )
    csv_res.raise_for_status()

    ct = csv_res.headers.get('Content-Type', '')
    if 'html' in ct:
        raise ValueError(f'CSVの取得に失敗しました（HTMLが返されました）\nURL: {csv_res.url}')

    csv_res.encoding = csv_res.apparent_encoding or 'utf-8-sig'
    return csv_res.text


# ── CSV パース ────────────────────────────────────────
def parse_csv(text: str):
    text = text.lstrip('\ufeff')
    reader = csv.reader(io.StringIO(text))
    headers = next(reader)
    rows = list(reader)
    return headers, rows


# ── Google Sheets ─────────────────────────────────────
def build_sheets_service():
    client_email = os.environ.get('GOOGLE_CLIENT_EMAIL')
    private_key  = os.environ.get('GOOGLE_PRIVATE_KEY')
    if client_email and private_key:
        creds = service_account.Credentials.from_service_account_info(
            {'type': 'service_account', 'client_email': client_email,
             'private_key': private_key.replace('\\n', '\n'),
             'token_uri': 'https://oauth2.googleapis.com/token'},
            scopes=['https://www.googleapis.com/auth/spreadsheets'],
        )
    else:
        creds = service_account.Credentials.from_service_account_file(
            str(SA_PATH), scopes=['https://www.googleapis.com/auth/spreadsheets'],
        )
    return build('sheets', 'v4', credentials=creds)


def get_sheet_name_by_gid(service) -> str:
    """TARGET_GID からシート名を取得"""
    meta = service.spreadsheets().get(spreadsheetId=SPREADSHEET_ID).execute()
    for sheet in meta.get('sheets', []):
        if sheet['properties']['sheetId'] == TARGET_GID:
            return sheet['properties']['title']
    # gid が見つからない場合は全シート名を表示して終了
    names = [s['properties']['title'] for s in meta.get('sheets', [])]
    raise ValueError(
        f'gid={TARGET_GID} のシートが見つかりません。\n'
        f'利用可能なシート: {names}'
    )


def col_letter_to_index(letter: str) -> int:
    """A→0, P→15"""
    result = 0
    for ch in letter.upper():
        result = result * 26 + (ord(ch) - ord('A') + 1)
    return result - 1


def index_to_col_letter(idx: int) -> str:
    """0→A, 15→P"""
    result = ''
    n = idx + 1
    while n > 0:
        n, rem = divmod(n - 1, 26)
        result = chr(ord('A') + rem) + result
    return result


# ── 自動検出 ──────────────────────────────────────────
HEADER_ROW = 2   # ヘッダーは2行目固定
DATA_ROW   = 3   # データは3行目から

def detect_office_ranges(service, sheet_name: str) -> dict:
    """
    シートをスキャンして各事務所の貼り付け範囲を自動検出。

    レイアウト:
      1行目: 各事務所のラベル（hibiki / honoka / aegislo / thank 等のキーワード）
      2行目: CSV列名と一致するヘッダー（固定）
      3行目～: データ貼り付け先

    1行目でドメインキーワードの列位置を特定 →
    2行目の同列以降にある連続した非空セルブロックをその事務所のヘッダーとして確定。

    Returns:
      {
        'hibiki': {'start_col': 0,  'end_col': 10, 'headers': [...]},
        ...
      }
      列番号は 0始まり
    """
    # 1〜2行目 × 300列 を読む
    scan_range = f"'{sheet_name}'!A1:KN2"
    result = service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=scan_range,
    ).execute()
    rows = result.get('values', [])
    if len(rows) < 2:
        raise ValueError(f'シート "{sheet_name}" の1〜2行目が読み込めません')

    max_cols = max(len(r) for r in rows)
    label_row  = rows[0] + [''] * (max_cols - len(rows[0]))   # 1行目
    header_row = rows[1] + [''] * (max_cols - len(rows[1]))   # 2行目

    office_ranges = {}

    # 1行目で全ドメインのラベル列位置を収集
    anchors = {}   # {domain: col_idx}
    for domain, dcfg in DOMAIN_CONFIG.items():
        keywords = [kw.lower() for kw in dcfg['keywords']]
        for c_idx, cell in enumerate(label_row):
            if any(kw in str(cell).lower() for kw in keywords):
                anchors[domain] = c_idx
                break

    # 列位置でソート → 各事務所の終端 = 次の事務所の開始列 - 1
    sorted_domains = sorted(anchors.items(), key=lambda x: x[1])

    # 2行目の最終非空列を求める（最後の事務所の終端用）
    last_header_col = max_cols - 1
    while last_header_col >= 0 and not str(header_row[last_header_col]).strip():
        last_header_col -= 1

    for i, (domain, anchor_c) in enumerate(sorted_domains):
        # 終端: 次事務所の開始列 - 1、または2行目の最終列
        if i + 1 < len(sorted_domains):
            ec = sorted_domains[i + 1][1] - 1
        else:
            ec = last_header_col

        # 2行目のアンカー列以降で最初の非空列を開始点にする
        sc = anchor_c
        while sc <= ec and not str(header_row[sc]).strip():
            sc += 1

        if sc > ec:
            print(f'  WARNING: [{domain}] の2行目ヘッダーが空です（スキップ）')
            continue

        headers = [str(header_row[c]).strip() for c in range(sc, ec + 1)]
        office_ranges[domain] = {
            'start_col': sc,
            'end_col':   ec,
            'headers':   headers,
        }

    for domain in DOMAIN_CONFIG:
        if domain not in anchors:
            print(f'  WARNING: [{domain}] のラベルが1行目に見つかりませんでした（スキップ）')

    return office_ranges


# ── シートへの書き込み ────────────────────────────────
def write_to_sheet(service, sheet_name: str, office_range: dict,
                   csv_headers: list, csv_rows: list) -> int:
    """
    office_range で指定された位置に CSV データを書き込む。
    既存データをクリアしてから書き込む。
    """
    start_col  = office_range['start_col']   # 0始まり
    end_col    = office_range['end_col']     # 0始まり inclusive
    sh_headers = office_range['headers']

    start_letter = index_to_col_letter(start_col)
    end_letter   = index_to_col_letter(end_col)

    # シートヘッダー → CSV列インデックス のマッピング
    col_map = []
    for sh in sh_headers:
        sh = sh.strip()
        csv_idx = next((j for j, ch in enumerate(csv_headers) if ch.strip() == sh), None)
        col_map.append(csv_idx)

    # マッピング確認
    print(f'\n  ■ ヘッダーマッピング ({start_letter}～{end_letter}):')
    for i, (sh, csv_i) in enumerate(zip(sh_headers, col_map)):
        col_letter = index_to_col_letter(start_col + i)
        if not sh:
            print(f'    {col_letter}: (空欄) → スキップ')
        elif csv_i is not None:
            print(f'    {col_letter}: "{sh}" → CSV列[{csv_i}]')
        else:
            print(f'    {col_letter}: "{sh}" → ★未一致')

    if not csv_rows:
        print('\n  対象データが0件でした（面談日=今日のデータなし）')
        return 0

    # クリア
    clear_range = f"'{sheet_name}'!{start_letter}{DATA_ROW}:{end_letter}"
    service.spreadsheets().values().clear(
        spreadsheetId=SPREADSHEET_ID,
        range=clear_range,
    ).execute()
    print(f'\n  [クリア] {clear_range}')

    # 書き込みデータ作成
    write_rows = []
    for row in csv_rows:
        out_row = []
        for csv_i in col_map:
            if csv_i is not None and csv_i < len(row):
                out_row.append(row[csv_i])
            else:
                out_row.append('')
        write_rows.append(out_row)

    write_range = f"'{sheet_name}'!{start_letter}{DATA_ROW}"
    service.spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID,
        range=write_range,
        valueInputOption='USER_ENTERED',
        body={'values': write_rows},
    ).execute()

    return len(write_rows)


# ── 1ドメイン処理 ─────────────────────────────────────
def run_one_domain(domain: str, today: str, service, sheet_name: str,
                   office_ranges: dict) -> str:
    dcfg = DOMAIN_CONFIG[domain]
    login_id = dcfg['login_id']
    login_pw = dcfg['login_pw']

    print(f'\n{"="*50}')
    print(f'[{domain}] 開始')
    print(f'{"="*50}')

    if not login_id or not login_pw:
        print(f'  SKIP: ログイン情報が未設定です（config_mendan.json に設定してください）')
        return 'スキップ（認証情報なし）'

    if domain not in office_ranges:
        print(f'  SKIP: スプレッドシート上の貼り付け範囲が検出できませんでした')
        return 'スキップ（貼り付け範囲未検出）'

    try:
        # 1. ログイン
        print(f'  ログイン中 ({login_id})...')
        session = login(dcfg['base_url'], login_id, login_pw)
        print('  ログイン成功')

        # 2. CSV ダウンロード
        print(f'  CSV取得中 (面談日={today})...')
        csv_text = download_mendan_csv(session, dcfg['base_url'], today)
        session.close()

        csv_headers, csv_rows = parse_csv(csv_text)
        print(f'  CSV: {len(csv_rows)}件 / {len(csv_headers)}列')

        # 3. シートへ書き込み
        count = write_to_sheet(service, sheet_name, office_ranges[domain],
                               csv_headers, csv_rows)
        return f'完了 {count}件'

    except Exception as e:
        print(f'  ERROR: {e}')
        return f'エラー: {e}'


# ── 未転化モード ──────────────────────────────────────
def get_mitenca_sheet_name(service) -> str:
    """MITENCA_GID からシート名を取得"""
    meta = service.spreadsheets().get(spreadsheetId=MITENCA_SS_ID).execute()
    for sheet in meta.get('sheets', []):
        if sheet['properties']['sheetId'] == MITENCA_GID:
            return sheet['properties']['title']
    names = [s['properties']['title'] for s in meta.get('sheets', [])]
    raise ValueError(f'gid={MITENCA_GID} のシートが見つかりません。利用可能: {names}')


def run_mitenca(today: str, service):
    """
    hibiki の面談予約日=today で CSV 取得 → 未転化シートに貼り付け。
    ヘッダーは1行目（A1:M1）固定、データは2行目から。
    """
    print(f'\n{"="*50}')
    print(f'[未転化モード] hibiki 面談予約日={today}')
    print(f'{"="*50}')

    dcfg = DOMAIN_CONFIG['hibiki']
    login_id = dcfg['login_id']
    login_pw = dcfg['login_pw']

    if not login_id or not login_pw:
        print('  SKIP: hibiki のログイン情報が未設定です')
        return 'スキップ（認証情報なし）'

    try:
        # シート名取得
        sheet_name = get_mitenca_sheet_name(service)
        print(f'  対象シート: "{sheet_name}"')

        # 1行目のヘッダーを読む（A1:M1）
        header_range = f"'{sheet_name}'!A{MITENCA_HEADER_ROW}:M{MITENCA_HEADER_ROW}"
        result = service.spreadsheets().values().get(
            spreadsheetId=MITENCA_SS_ID,
            range=header_range,
        ).execute()
        sh_headers = [h.strip() for h in (result.get('values', [[]])[0])]
        print(f'  ヘッダー: {sh_headers}')

        # ログイン
        print(f'  ログイン中 ({login_id})...')
        session = login(dcfg['base_url'], login_id, login_pw)
        print('  ログイン成功')

        # CSV ダウンロード（面談予約日フィルタ）
        print(f'  CSV取得中 (面談予約日={today})...')
        csv_text = download_yoyaku_csv(session, dcfg['base_url'], today)
        session.close()

        csv_headers, csv_rows = parse_csv(csv_text)
        print(f'  CSV: {len(csv_rows)}件 / {len(csv_headers)}列')

        # ヘッダーマッピング
        col_map = []
        for sh in sh_headers:
            csv_idx = next((j for j, ch in enumerate(csv_headers) if ch.strip() == sh), None)
            col_map.append(csv_idx)

        print(f'\n  ■ ヘッダーマッピング (A～M):')
        for i, (sh, csv_i) in enumerate(zip(sh_headers, col_map)):
            col_letter = index_to_col_letter(i)
            if not sh:
                print(f'    {col_letter}: (空欄) → スキップ')
            elif csv_i is not None:
                print(f'    {col_letter}: "{sh}" → CSV列[{csv_i}]')
            else:
                print(f'    {col_letter}: "{sh}" → ★未一致')

        if not csv_rows:
            print('\n  対象データが0件でした')
            return '0件（データなし）'

        # クリア（A2:M 以降）
        end_letter = index_to_col_letter(len(sh_headers) - 1)
        clear_range = f"'{sheet_name}'!A{MITENCA_DATA_ROW}:{end_letter}"
        service.spreadsheets().values().clear(
            spreadsheetId=MITENCA_SS_ID,
            range=clear_range,
        ).execute()
        print(f'\n  [クリア] {clear_range}')

        # 書き込み
        write_rows = []
        for row in csv_rows:
            out_row = []
            for csv_i in col_map:
                if csv_i is not None and csv_i < len(row):
                    out_row.append(row[csv_i])
                else:
                    out_row.append('')
            write_rows.append(out_row)

        write_range = f"'{sheet_name}'!A{MITENCA_DATA_ROW}"
        service.spreadsheets().values().update(
            spreadsheetId=MITENCA_SS_ID,
            range=write_range,
            valueInputOption='USER_ENTERED',
            body={'values': write_rows},
        ).execute()

        return f'完了 {len(write_rows)}件'

    except Exception as e:
        print(f'  ERROR: {e}')
        return f'エラー: {e}'


# ── メイン ────────────────────────────────────────────
def main():
    args = sys.argv[1:]
    target_domains = None
    date_arg = None
    scan_only = False
    mitenca_mode = False

    i = 0
    while i < len(args):
        if args[i] == '--domain' and i + 1 < len(args):
            target_domains = [args[i + 1]]
            i += 2
        elif args[i] == '--scan':
            scan_only = True
            i += 1
        elif args[i] == '--mitenca':
            mitenca_mode = True
            i += 1
        else:
            date_arg = args[i]
            i += 1

    if target_domains and target_domains[0] not in DOMAIN_CONFIG:
        print(f'ERROR: 不明なドメイン "{target_domains[0]}"。指定可能: {list(DOMAIN_CONFIG.keys())}')
        sys.exit(1)

    today = date_arg if date_arg else datetime.now().strftime('%Y/%m/%d')

    # 認証情報の補完（環境変数 → config.json の順）
    hibiki_cfg = {}
    if os.environ.get('HIBIKI_LOGIN_ID'):
        hibiki_cfg = {'login_id': os.environ['HIBIKI_LOGIN_ID'],
                      'login_pw': os.environ.get('HIBIKI_LOGIN_PW', '')}
    elif CONFIG_PATH.exists():
        hibiki_cfg = json.loads(CONFIG_PATH.read_text(encoding='utf-8'))
    load_credentials(hibiki_cfg)

    # Google Sheets 初期化
    print('\nGoogle Sheetsに接続中...')
    service = build_sheets_service()

    # ── 未転化モード ──
    if mitenca_mode:
        print(f'対象日: {today}')
        status = run_mitenca(today, service)
        print(f'\n■ 完了: {status}')
        return

    domains = target_domains if target_domains else list(DOMAIN_CONFIG.keys())
    print(f'対象日: {today}')
    print(f'処理ドメイン: {domains}')

    # シート名を gid から取得
    sheet_name = get_sheet_name_by_gid(service)
    print(f'対象シート: "{sheet_name}"')

    # 貼り付け範囲を自動検出
    print('\n貼り付け範囲を自動検出中...')
    office_ranges = detect_office_ranges(service, sheet_name)
    print('\n■ 検出結果:')
    for domain, rng in office_ranges.items():
        sc = index_to_col_letter(rng['start_col'])
        ec = index_to_col_letter(rng['end_col'])
        print(f'  {domain:10s} → ヘッダー行{HEADER_ROW}: {sc}{HEADER_ROW}:{ec}{HEADER_ROW} '
              f'({len(rng["headers"])}列) データ開始行={DATA_ROW}')
    for domain in domains:
        if domain not in office_ranges:
            print(f'  {domain:10s} → ★未検出')

    if scan_only:
        print('\n[--scan モード] 書き込みは行いません。')
        return

    # 全ドメインを処理
    results = {}
    for domain in domains:
        results[domain] = run_one_domain(domain, today, service, sheet_name, office_ranges)

    # サマリー
    print(f'\n{"="*50}')
    print(f'■ 処理完了サマリー ({today})')
    print(f'{"="*50}')
    for domain, status in results.items():
        print(f'  {domain:10s} → {status}')


if __name__ == '__main__':
    main()
