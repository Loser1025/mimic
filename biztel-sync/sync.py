import requests, ssl, re, io, csv, os
from requests.adapters import HTTPAdapter
from datetime import datetime
from collections import Counter
from googleapiclient.discovery import build
from google.oauth2.service_account import Credentials

# ===== 設定 =====
BIZTEL_BASE     = 'https://210.129.157.5:8000'
BIZTEL_USER     = os.environ['BIZTEL_USER']
BIZTEL_PASS     = os.environ['BIZTEL_PASS']
SPREADSHEET_ID  = '1kNprw6I8gHmgWzkvAhvtnGKXJrmGHU3u9wQOWPEx9gQ'
SHEET_NAME      = 'テレグラム管理'
START_COL       = 'T'  # T列: 内線番号, U列: コール数, V列: 日時


class LegacySSLAdapter(HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.set_ciphers('DEFAULT:@SECLEVEL=0')
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        kwargs['ssl_context'] = ctx
        return super().init_poolmanager(*args, **kwargs)

    def send(self, request, **kwargs):
        kwargs['verify'] = False
        return super().send(request, **kwargs)


def get_biztel_csv():
    s = requests.Session()
    s.mount('https://', LegacySSLAdapter())
    s.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})

    # ログイン
    s.post(BIZTEL_BASE + '/adminlogin.php', data={
        'login_type': '', 'inpAccount': BIZTEL_USER, 'inpPassword': BIZTEL_PASS,
    }, verify=False, timeout=15)

    # token_key取得
    r = s.get(BIZTEL_BASE + '/user_history_referenceS.php',
              headers={'Referer': BIZTEL_BASE + '/index.php'}, verify=False, timeout=15)
    m = (re.search(rb'name=["\']token_key["\'][^>]*value=["\']([^"\']+)["\']', r.content) or
         re.search(rb'value=["\']([^"\']+)["\'][^>]*name=["\']token_key["\']', r.content))
    if not m:
        raise RuntimeError('token_key not found')
    token = m.group(1).decode()

    # 今日00:00〜現在で発信履歴をCSVダウンロード
    today = datetime.now()
    params = {
        'token_key': token, 'type': '1',
        'caller_id': '', 'called_id': '', 'transfer_to': '',
        'start_dt_y': str(today.year), 'start_dt_m': str(today.month),
        'start_dt_d': str(today.day), 'start_dt_h': '00', 'start_dt_min': '00',
        'end_dt_y': '--', 'end_dt_m': '--', 'end_dt_d': '--',
        'end_dt_h': '', 'end_dt_min': '',
        'SortID': '', 'Ppage': '', 'sip_username': BIZTEL_USER,
        'sn_no': 'on', 'DownLoadFileNmae': 'download.txt', 'disptype': '0', 'background': '',
    }
    r_dl = s.post(BIZTEL_BASE + '/download_qry.php', data=params,
                  headers={'Referer': BIZTEL_BASE + '/user_history_referenceS.php'},
                  verify=False, timeout=30)

    if 'error' in r_dl.headers.get('Content-Disposition', ''):
        raise RuntimeError('Download failed: ' + r_dl.text[:200])

    return r_dl.content.decode('shift-jis', errors='replace')


def aggregate_by_extension(csv_text):
    reader = csv.reader(io.StringIO(csv_text))
    counter = Counter()
    for row in reader:
        if len(row) >= 3:
            ext = row[2].strip()
            # 内線番号のみ（外部番号は0始まりや10桁以上なので除外）
            if ext and not ext.startswith('0') and len(ext) <= 6:
                counter[ext] += 1
    return counter


def append_to_sheets(counter):
    creds = Credentials.from_service_account_info({
        'type': 'service_account',
        'client_email': os.environ['GOOGLE_CLIENT_EMAIL'],
        'private_key': os.environ['GOOGLE_PRIVATE_KEY'].replace('\\n', '\n'),
        'token_uri': 'https://oauth2.googleapis.com/token',
    }, scopes=['https://www.googleapis.com/auth/spreadsheets'])
    service = build('sheets', 'v4', credentials=creds)

    now_str = datetime.now().strftime('%Y/%m/%d %H:%M')
    rows = [[ext, count, now_str] for ext, count in sorted(counter.items())]

    service.spreadsheets().values().append(
        spreadsheetId=SPREADSHEET_ID,
        range=f'{SHEET_NAME}!{START_COL}:{START_COL}',
        valueInputOption='USER_ENTERED',
        insertDataOption='INSERT_ROWS',
        body={'values': rows}
    ).execute()

    print(f'{now_str} - {len(rows)}件の内線番号を書き込みました')
    for ext, count, _ in rows:
        print(f'  {ext}: {count}件')


if __name__ == '__main__':
    csv_text = get_biztel_csv()
    counter = aggregate_by_extension(csv_text)
    append_to_sheets(counter)
