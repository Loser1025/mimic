"""
電番巻取りスクリプト（強化版）
B列が空の会社に対して以下を順番に試みる：
  1. tel: リンクDOM直接取得（既存URLまたは検索で発見したURL）
  2. コンタクトページ探索（/contact /company /access /about 等）
  3. iタウンページ検索
  4. Yahoo検索 × 複数クエリ（電話番号 / 連絡先 / お問い合わせ）
  5. Groq抽出（全収集テキストに対して）
  6. 強化正規表現（括弧形式・ハイフンなし含む）
"""
import os, sys, re, time, random, json, urllib.parse, urllib.request
sys.stdout.reconfigure(encoding='utf-8')

import requests
from playwright.sync_api import sync_playwright

# ===== 設定 =====
CREDS_PATH   = 'C:/Users/弁護士法人響/.config/gws/authorized_user.json'
SSID         = '1Gg-2dcjTyrdDJy_t45kwNq3FJUB5kgXPer8nQKtVHhw'
SHEET_NAME   = 'ﾌﾞﾙｶﾗ 媒体ﾘｽﾄ たま作業中'
GROQ_API_KEY = os.environ.get('GROQ_API_KEY', '')
GROQ_MODELS  = [
    'llama-3.3-70b-versatile',
    'llama3-70b-8192',
    'llama3-8b-8192',
    'gemma2-9b-it',
]
groq_model_idx = 0
groq_disabled  = False

EXCLUDE_DOMAINS = [
    'yahoo.co.jp', 'google.com', 'google.co.jp', 'bing.com', 'duckduckgo.com',
    'wikipedia.org', 'facebook.com', 'twitter.com', 'instagram.com', 'youtube.com',
    'indeed.com', 'rikunabi.', 'mynavi.', 'doda.jp', 'hellowork', 'careerindex',
    'tabelog.com', 'hotpepper.', 'tripadvisor.', 'ekiten.jp',
    'baseconnect.in', 'nikkei.com', 'townpage.jp', 'amazon.co.jp', 'rakuten.co.jp',
]

# コンタクト系サフィックス（優先度順）
CONTACT_SUFFIXES = [
    '/contact', '/contact.html', '/contact/',
    '/company', '/company.html', '/company/',
    '/access', '/access.html', '/access/',
    '/about', '/about.html', '/about/',
    '/info', '/info.html',
    '/inquiry', '/inquiry.html',
    '/corporate', '/corporate/',
    '/overview', '/overview.html',
]

# 電話番号正規表現（強化版）
TEL_PATTERNS = [
    # TEL/電話ラベル付き（最優先）
    re.compile(r'(?:電話|TEL|Tel|tel|☎|📞)[^\d]{0,8}(0\d[\d\-－\(\)（）\s]{7,14}\d)'),
    # ハイフン区切り標準形式
    re.compile(r'(?<!\d)(0\d{1,4}[-－]\d{1,4}[-－]\d{3,4})(?!\d)'),
    # 括弧形式: 03(1234)5678
    re.compile(r'(?<!\d)(0\d{1,4}[（\(]\d{1,4}[）\)]\d{3,4})(?!\d)'),
    # ハイフンなし10-11桁
    re.compile(r'(?<!\d)(0[789]0\d{8}|0\d{9,10})(?!\d)'),
    # スペース区切り
    re.compile(r'(?<!\d)(0\d{1,4}[\s　]\d{1,4}[\s　]\d{3,4})(?!\d)'),
]

# ===== Google Sheets =====
def get_token():
    creds = json.load(open(CREDS_PATH))
    data = urllib.parse.urlencode({**creds, 'grant_type': 'refresh_token'}).encode()
    return json.loads(urllib.request.urlopen(
        urllib.request.Request('https://oauth2.googleapis.com/token', data=data)
    ).read())['access_token']

def sheets_get(token, range_str):
    enc = urllib.parse.quote(range_str)
    req = urllib.request.Request(
        f'https://sheets.googleapis.com/v4/spreadsheets/{SSID}/values/{enc}',
        headers={'Authorization': f'Bearer {token}'}
    )
    return json.loads(urllib.request.urlopen(req).read())

def sheets_update(token, range_str, values):
    enc = urllib.parse.quote(range_str)
    body = json.dumps({'values': values}).encode()
    req = urllib.request.Request(
        f'https://sheets.googleapis.com/v4/spreadsheets/{SSID}/values/{enc}?valueInputOption=RAW',
        data=body, method='PUT',
        headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
    )
    urllib.request.urlopen(req)

# ===== ユーティリティ =====
def is_official(url: str) -> bool:
    return bool(url) and url.startswith('http') and not any(d in url.lower() for d in EXCLUDE_DOMAINS)

def normalize_tel(t: str) -> str:
    if not t:
        return ''
    t = t.translate(str.maketrans('０１２３４５６７８９－（）　', '0123456789-() '))
    t = re.sub(r'[（\(\)）]', '-', t)
    t = re.sub(r'[\s\u2010\u2011\uff0d]', '-', t)
    t = re.sub(r'-{2,}', '-', t).strip('-')
    t = re.sub(r'[^\d\-]', '', t)
    # 短すぎ・長すぎは除外
    digits = re.sub(r'\D', '', t)
    if len(digits) < 9 or len(digits) > 11:
        return ''
    return t

def extract_tel_from_text(text: str) -> str:
    """強化正規表現で電話番号を抽出（優先度順）"""
    for pattern in TEL_PATTERNS:
        for m in pattern.finditer(text):
            normalized = normalize_tel(m.group(1))
            if normalized:
                return normalized
    return ''

# ===== tel: リンクDOM直接取得 =====
def get_tel_from_dom(page) -> str:
    """<a href="tel:..."> を直接取得（最も確実）"""
    try:
        tel_links = page.query_selector_all('a[href^="tel:"]')
        for el in tel_links:
            href = el.get_attribute('href') or ''
            raw = href.replace('tel:', '').strip()
            normalized = normalize_tel(raw)
            if normalized:
                print(f'  ✓ tel:リンク発見: {normalized}')
                return normalized
    except:
        pass
    return ''

# ===== コンタクトページ探索 =====
def search_contact_pages(page, base_url: str) -> str:
    """base_urlのコンタクト系ページを順に試してtel取得"""
    base = base_url.rstrip('/')
    for suffix in CONTACT_SUFFIXES:
        url = base + suffix
        try:
            page.goto(url, timeout=10000, wait_until='domcontentloaded')
            page.wait_for_timeout(600)
            # DOM tel:リンク優先
            tel = get_tel_from_dom(page)
            if tel:
                print(f'  ✓ コンタクトページ({suffix}): {tel}')
                return tel
            # テキスト抽出
            text = page.inner_text('body')
            tel = extract_tel_from_text(text)
            if tel:
                print(f'  ✓ コンタクトページ({suffix}) regex: {tel}')
                return tel
        except:
            pass
    return ''

# ===== iタウンページ検索 =====
def search_itp(page, company: str) -> str:
    """iタウンページで会社名検索して電番取得"""
    try:
        query = urllib.parse.quote(company)
        page.goto(f'https://itp.ne.jp/result/?svc=0&keyword={query}', timeout=8000, wait_until='domcontentloaded')
        page.wait_for_timeout(1000)
        # tel:リンク
        tel = get_tel_from_dom(page)
        if tel:
            print(f'  ✓ iタウンページ tel:リンク: {tel}')
            return tel
        # テキスト抽出
        text = page.inner_text('body')
        tel = extract_tel_from_text(text)
        if tel:
            print(f'  ✓ iタウンページ regex: {tel}')
            return tel
    except Exception as e:
        print(f'  iタウンページ失敗: {e}')
    return ''

# ===== Yahoo検索（複数クエリ）=====
def search_yahoo_multi(page, company: str) -> tuple[str, str, list]:
    """
    複数クエリでYahoo検索。
    Returns: (tel, official_url, collected_texts)
    """
    queries = [
        f'{company} 電話番号',
        f'{company} 連絡先',
        f'{company} お問い合わせ 電話',
        f'{company} TEL 代表',
    ]
    all_texts = []
    found_urls = []
    best_tel = ''

    for q in queries:
        if best_tel:
            break
        try:
            enc = urllib.parse.quote(q)
            page.goto(f'https://search.yahoo.co.jp/search?p={enc}', timeout=20000, wait_until='domcontentloaded')
            page.wait_for_timeout(random.randint(1500, 2200))
            text = page.inner_text('body')
            all_texts.append(f'[Yahoo: {q}]\n{text[:2000]}')

            # tel:リンク
            tel = get_tel_from_dom(page)
            if tel:
                best_tel = tel
                print(f'  ✓ Yahoo検索({q[:20]}) tel:リンク: {tel}')
                break

            # テキスト抽出
            tel = extract_tel_from_text(text)
            if tel:
                best_tel = tel
                print(f'  ✓ Yahoo検索({q[:20]}) regex: {tel}')

            # URL収集
            for el in page.query_selector_all('a[href]'):
                href = el.get_attribute('href') or ''
                if is_official(href) and href not in found_urls:
                    found_urls.append(href)
                if len(found_urls) >= 6:
                    break

        except Exception as e:
            print(f'  Yahoo検索失敗({q[:20]}): {e}')

        time.sleep(random.uniform(1.5, 2.5))

    official_url = found_urls[0] if found_urls else ''
    return best_tel, official_url, all_texts

# ===== Groq抽出 =====
def groq_extract(company: str, text: str) -> dict | None:
    global groq_model_idx, groq_disabled
    if groq_disabled:
        return None

    prompt = (
        f'以下のテキストから「{company}」の代表電話番号を抽出してください。\n'
        '・tel: 代表電話番号1つ(ハイフン区切り例:03-1234-5678)。不明はnull。\n'
        '・url: 公式サイトURL1つ(求人・口コミ・SNS除く)。不明はnull。\n'
        f'テキスト:\n{text[:4000]}\n\n'
        'JSONのみ: {"tel": "...", "url": "..."}'
    )

    while groq_model_idx < len(GROQ_MODELS):
        model = GROQ_MODELS[groq_model_idx]
        try:
            r = requests.post(
                'https://api.groq.com/openai/v1/chat/completions',
                headers={'Authorization': f'Bearer {GROQ_API_KEY}'},
                json={'model': model,
                      'messages': [{'role': 'user', 'content': prompt}],
                      'temperature': 0, 'max_tokens': 200},
                timeout=30
            )
            if r.status_code == 200:
                content = r.json()['choices'][0]['message']['content'].strip()
                m = re.search(r'\{.*?\}', content, re.DOTALL)
                return json.loads(m.group()) if m else None
            elif r.status_code == 429:
                print(f'  [Groq 429] {model} → 65秒待機後 次モデルへ')
                time.sleep(65)
                groq_model_idx += 1
                if groq_model_idx >= len(GROQ_MODELS):
                    print('  [Groq] 全モデル制限 → regex onlyへ')
                    groq_disabled = True
                    return None
            elif r.status_code == 403:
                print('  [Groq 403] 認証エラー → Groq無効化')
                groq_disabled = True
                return None
            else:
                print(f'  [Groq {r.status_code}]')
                return None
        except Exception as e:
            print(f'  [Groq ERROR] {e}')
            return None
    return None

# ===== メイン巻取り処理 =====
def retry_company(page, company: str, existing_url: str) -> str:
    """
    電番を全手段で取得。取得できた電番を返す。取得できなければ ''。
    """
    print(f'  戦略: tel:DOM → コンタクトページ → iタウン → Yahoo複数 → Groq')
    all_texts = []

    # -------------------------------------------------------
    # STEP 1: 既存URLがあれば直接訪問 → tel:リンク + コンタクトページ
    # -------------------------------------------------------
    if existing_url:
        try:
            page.goto(existing_url, timeout=15000, wait_until='domcontentloaded')
            page.wait_for_timeout(1000)

            tel = get_tel_from_dom(page)
            if tel:
                return tel

            site_text = page.inner_text('body')
            all_texts.append(f'[{existing_url}]\n{site_text[:2500]}')

            tel = extract_tel_from_text(site_text)
            if tel:
                return tel

            # コンタクトページ探索
            tel = search_contact_pages(page, existing_url)
            if tel:
                return tel

        except Exception as e:
            print(f'  既存URL訪問失敗: {e}')

    # -------------------------------------------------------
    # STEP 2: iタウンページ
    # -------------------------------------------------------
    tel = search_itp(page, company)
    if tel:
        return tel

    # -------------------------------------------------------
    # STEP 3: Yahoo 複数クエリ検索
    # -------------------------------------------------------
    tel, found_url, yahoo_texts = search_yahoo_multi(page, company)
    all_texts.extend(yahoo_texts)
    if tel:
        return tel

    # 検索で見つかったURLも訪問してコンタクトページ探索
    if found_url and found_url != existing_url:
        try:
            page.goto(found_url, timeout=15000, wait_until='domcontentloaded')
            page.wait_for_timeout(1000)
            tel = get_tel_from_dom(page)
            if tel:
                return tel
            site_text = page.inner_text('body')
            all_texts.append(f'[{found_url}]\n{site_text[:2500]}')
            tel = search_contact_pages(page, found_url)
            if tel:
                return tel
        except:
            pass

    # -------------------------------------------------------
    # STEP 4: Groq（全収集テキストに対して）
    # -------------------------------------------------------
    if all_texts:
        extracted = groq_extract(company, '\n\n'.join(all_texts))
        if extracted:
            raw_tel = str(extracted.get('tel') or '')
            if raw_tel not in ('null', 'None', ''):
                tel = normalize_tel(raw_tel)
                if tel:
                    print(f'  ✓ Groq抽出: {tel}')
                    return tel

    # -------------------------------------------------------
    # STEP 5: 強化regex（全テキスト結合）
    # -------------------------------------------------------
    combined = '\n'.join(all_texts)
    tel = extract_tel_from_text(combined)
    if tel:
        print(f'  ✓ 強化regex: {tel}')
        return tel

    print('  × 全手段失敗')
    return ''

# ===== メイン =====
def main():
    print('=== 電番巻取りスクリプト（強化版）===\n')
    token = get_token()

    res = sheets_get(token, f'{SHEET_NAME}!A1:C300')
    rows = res.get('values', [])

    # B列（電番）が空の行のみ対象
    targets = []
    for i, row in enumerate(rows[1:], start=2):
        company     = row[0].strip() if len(row) > 0 else ''
        tel         = row[1].strip() if len(row) > 1 else ''
        existing_url = row[2].strip() if len(row) > 2 else ''
        if company and not tel:
            targets.append({'row': i, 'company': company, 'existing_url': existing_url})

    total = len(targets)
    print(f'電番未取得: {total}件\n')

    success = 0
    failed  = []

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-blink-features=AutomationControlled', '--disable-http2']
        )
        ctx = browser.new_context(
            user_agent=(
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/125.0.0.0 Safari/537.36'
            ),
            locale='ja-JP',
            viewport={'width': 1280, 'height': 900},
        )
        page = ctx.new_page()
        page.add_init_script(
            "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
        )

        for idx, t in enumerate(targets, start=1):
            company      = t['company']
            existing_url = t['existing_url']
            url_label    = existing_url[:40] if existing_url else '(なし)'
            print(f'[{idx}/{total}] {company}  既存URL:{url_label}')

            tel = retry_company(page, company, existing_url)

            if tel:
                sheets_update(token, f'{SHEET_NAME}!B{t["row"]}', [[tel]])
                success += 1
                print(f'  → ✅ 書込: {tel}')
            else:
                failed.append(company)
                print(f'  → ❌ 取得不可')

            if idx % 20 == 0:
                token = get_token()

            wait = random.uniform(4, 7)
            print(f'  → {wait:.1f}秒待機\n')
            time.sleep(wait)

        browser.close()

    print('=' * 50)
    print(f'✅ 完了: {success}/{total}件 取得成功')
    if failed:
        print(f'\n❌ 取得できなかった会社 ({len(failed)}件):')
        for c in failed:
            print(f'  - {c}')

if __name__ == '__main__':
    main()
