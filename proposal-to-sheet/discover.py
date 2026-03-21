"""
hibiki の検索ページを調査して
1. 提案日フィルターのパラメータ名
2. CSVエクスポートエンドポイント
3. 利用可能な全フォームフィールド
を表示するスクリプト
"""
import re
import json
import sys
from pathlib import Path

import requests

HIBIKI_BASE = 'https://hibiki.leaduplus.pro'
CONFIG_PATH = Path(__file__).parent.parent / 'csv-to-sheet' / 'config.json'

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                  '(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'ja,en-US;q=0.7,en;q=0.3',
}


def load_config():
    if CONFIG_PATH.exists():
        return json.loads(CONFIG_PATH.read_text(encoding='utf-8'))
    return {}


def _csrf(html: str) -> str:
    m = re.search(r'name="_token"[^>]*value="([^"]+)"', html)
    if not m:
        raise ValueError('CSRFトークン取得失敗')
    return m.group(1)


def login(login_id: str, login_pw: str) -> requests.Session:
    session = requests.Session()
    session.headers.update(HEADERS)
    page = session.get(f'{HIBIKI_BASE}/debt/login', timeout=30)
    page.raise_for_status()
    token = _csrf(page.text)
    res = session.post(
        f'{HIBIKI_BASE}/debt/login',
        data={'_token': token, 'name': login_id, 'password': login_pw},
        allow_redirects=True,
        timeout=30,
    )
    if 'name="_token"' in res.text and '/debt/login' in res.url:
        raise ValueError('ログイン失敗')
    print(f'ログイン成功: {res.url}')
    return session


def discover_search_form(session: requests.Session):
    """検索ページのフォームフィールドを全て表示"""
    print('\n=== 検索ページ調査 ===')
    res = session.get(f'{HIBIKI_BASE}/debt/consulter/list/search', timeout=30)
    res.raise_for_status()
    html = res.text

    print(f'URL: {res.url}')
    print(f'ステータス: {res.status_code}')

    # フォームのaction/method
    forms = re.findall(r'<form[^>]*>', html, re.IGNORECASE)
    print(f'\n■ フォーム要素 ({len(forms)}件):')
    for f in forms:
        print(f'  {f[:200]}')

    # input要素
    inputs = re.findall(r'<input[^>]+>', html, re.IGNORECASE)
    print(f'\n■ inputフィールド ({len(inputs)}件):')
    for inp in inputs:
        name_m = re.search(r'name=["\']([^"\']*)["\']', inp)
        type_m = re.search(r'type=["\']([^"\']*)["\']', inp)
        val_m = re.search(r'value=["\']([^"\']*)["\']', inp)
        if name_m:
            name = name_m.group(1)
            typ = type_m.group(1) if type_m else 'text'
            val = val_m.group(1) if val_m else ''
            print(f'  name="{name}" type="{typ}" value="{val}"')

    # select要素
    selects = re.findall(r'<select[^>]+>', html, re.IGNORECASE)
    print(f'\n■ selectフィールド ({len(selects)}件):')
    for s in selects:
        name_m = re.search(r'name=["\']([^"\']*)["\']', s)
        if name_m:
            print(f'  name="{name_m.group(1)}"')

    # 提案日関連を抽出
    print('\n■ 提案日関連の検索:')
    teian_matches = re.findall(r'.{0,100}提案.{0,100}', html)
    for m in teian_matches[:20]:
        print(f'  {m.strip()[:150]}')

    # CSVエクスポートリンク/ボタン
    print('\n■ CSV/エクスポート関連:')
    csv_links = re.findall(r'(?:href|action|onclick)[^>]*(?:csv|CSV|export|output)[^>]*', html, re.IGNORECASE)
    for link in csv_links[:20]:
        print(f'  {link[:200]}')

    # form action を探す
    actions = re.findall(r'action=["\']([^"\']+)["\']', html, re.IGNORECASE)
    print(f'\n■ form actionリスト:')
    for a in actions:
        print(f'  {a}')

    return html


def try_csv_endpoints(session: requests.Session):
    """よくあるCSVエンドポイントを試す"""
    print('\n=== CSVエンドポイント探索 ===')
    candidates = [
        '/debt/consulter/list/outputCsv',
        '/debt/consulter/list/outputConsulterCsv',
        '/debt/consulter/list/outputSearchCsv',
        '/debt/consulter/list/exportCsv',
        '/debt/consulter/list/download',
    ]
    for endpoint in candidates:
        url = HIBIKI_BASE + endpoint
        try:
            res = session.get(url, timeout=10, allow_redirects=False)
            print(f'  GET {endpoint} → {res.status_code}')
        except Exception as e:
            print(f'  GET {endpoint} → ERROR: {e}')


def main():
    cfg = load_config()
    login_id = cfg.get('login_id', '')
    login_pw = cfg.get('login_pw', '')

    if not login_id:
        login_id = input('hibiki ログインID: ').strip()
    if not login_pw:
        login_pw = input('hibiki パスワード: ').strip()

    print(f'ログイン中... ({login_id})')
    session = login(login_id, login_pw)

    html = discover_search_form(session)
    try_csv_endpoints(session)

    # HTMLをファイルに保存（詳細確認用）
    out = Path(__file__).parent / '_search_page.html'
    out.write_text(html, encoding='utf-8')
    print(f'\n[保存] 検索ページHTML: {out}')
    print('\n完了。上記の出力を確認してください。')


if __name__ == '__main__':
    main()
