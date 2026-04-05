"""
circusﾘｽﾄ たま作業中 スクレイパー

列構成:
  A: 会社名
  B: 紹介料
  C: 電話番号
  D: 公式サイトURL
  E: 業種
  F: ランク（業種から自動判定: A / B / C / その他）

業種カテゴリ:
  Aランク: 建設・土木 / 警備・保安 / 物流・倉庫・運送
  Bランク: 設備・メンテナンス / 介護・福祉 / 農業・林業・漁業 / 飲食・食品現場 / インフラ・公共系現場
  Cランク: 製造・工場 / 清掃・環境・廃棄物
  その他:  上記以外

取得ロジック（多段フォールバック）:
  電番/URL: tel:DOM → コンタクトページ → iタウン → Yahoo → Groq → regex
  業種:     URL訪問 → キーワードマッチ → Yahoo検索 → Groq分類 → その他（必ず埋める）
"""
import os, sys, re, time, random, json, urllib.parse, urllib.request
sys.stdout.reconfigure(encoding='utf-8')

import requests
from playwright.sync_api import sync_playwright

# ===== 設定 =====
CREDS_PATH   = 'C:/Users/弁護士法人響/.config/gws/authorized_user.json'
SSID         = '1Gg-2dcjTyrdDJy_t45kwNq3FJUB5kgXPer8nQKtVHhw'
SHEET_NAME   = 'circusﾘｽﾄ たま作業中'
GROQ_API_KEY = os.environ.get('GROQ_API_KEY', '')

GROQ_MODELS = [
    'llama-3.3-70b-versatile',
    'llama3-70b-8192',
    'llama3-8b-8192',
    'gemma2-9b-it',
]
groq_model_idx = 0
groq_disabled  = False

EXCLUDE_DOMAINS = [
    'yahoo.co.jp', 'yahoo.com', 'google.com', 'google.co.jp',
    'bing.com', 'duckduckgo.com', 'wikipedia.org',
    'facebook.com', 'twitter.com', 'instagram.com', 'linkedin.com', 'youtube.com',
    'indeed.com', 'rikunabi.', 'mynavi.', 'doda.jp', 'hellowork', 'careerindex',
    'tabelog.com', 'hotpepper.', 'tripadvisor.', 'ekiten.jp',
    'baseconnect.in', 'nikkei.com', 'townnews', 'townpage.jp',
    'lifull.com', 'suumo.', 'homes.co.jp', 'athome.co.jp',
    'amazon.co.jp', 'rakuten.co.jp',
    'mhlw.go.jp', 'caloo.jp', 'medley.life', 'qlife.jp',
]

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

# 電話番号パターン
TEL_PATTERNS = [
    re.compile(r'(?:電話|TEL|Tel|tel|☎|📞)[^\d]{0,8}(0\d[\d\-－\(\)（）\s]{7,14}\d)'),
    re.compile(r'(?<!\d)(0\d{1,4}[-－]\d{1,4}[-－]\d{3,4})(?!\d)'),
    re.compile(r'(?<!\d)(0\d{1,4}[（\(]\d{1,4}[）\)]\d{3,4})(?!\d)'),
    re.compile(r'(?<!\d)(0[789]0\d{8}|0\d{9,10})(?!\d)'),
    re.compile(r'(?<!\d)(0\d{1,4}[\s　]\d{1,4}[\s　]\d{3,4})(?!\d)'),
]

# ===== 業種カテゴリ定義 =====
GYOSHU_CATEGORIES = {
    '建設・土木':       ['建設', '土木', '建築', '工事', '施工', 'ゼネコン', 'リフォーム', '造成', '舗装', '基礎工事', '解体'],
    '警備・保安':       ['警備', 'セキュリティ', '保安', 'ガード', '防犯', '警護'],
    '物流・倉庫・運送': ['物流', '倉庫', '運送', '配送', 'トラック', '宅配', '運輸', '輸送', '配達', '引越', 'ロジスティクス'],
    '設備・メンテナンス': ['設備', 'メンテナンス', '保守', '点検', '修理', '電気工事', '管工事', '空調', '給排水', 'エレベーター', 'ビルメン'],
    '介護・福祉':       ['介護', '福祉', 'デイサービス', '老人ホーム', '障害者', '訪問介護', 'ケア', '高齢者', '障がい'],
    '農業・林業・漁業': ['農業', '林業', '漁業', '農園', '牧場', '養殖', '農家', '畜産', '水産'],
    '飲食・食品現場':   ['飲食', '食品', 'レストラン', '居酒屋', '給食', '食堂', '弁当', '惣菜', '食料', 'フード'],
    'インフラ・公共系現場': ['インフラ', '電力', 'ガス', '水道', '公共', '電気', '通信', '鉄道', '道路', '公営', '電気通信'],
    '製造・工場':       ['製造', '工場', '生産', '加工', 'メーカー', '製品', '組立', '溶接', '鋳造', '板金'],
    '清掃・環境・廃棄物': ['清掃', '環境', '廃棄物', 'ゴミ', '衛生', 'リサイクル', '廃棄', 'クリーン', '産廃', '汚水'],
}

RANK_MAP = {
    '建設・土木':           'A',
    '警備・保安':           'A',
    '物流・倉庫・運送':     'A',
    '設備・メンテナンス':   'B',
    '介護・福祉':           'B',
    '農業・林業・漁業':     'B',
    '飲食・食品現場':       'B',
    'インフラ・公共系現場': 'B',
    '製造・工場':           'C',
    '清掃・環境・廃棄物':   'C',
}

GYOSHU_LIST_STR = '／'.join(GYOSHU_CATEGORIES.keys()) + '／その他'

def gyoshu_to_rank(gyoshu: str) -> str:
    return RANK_MAP.get(gyoshu, 'その他')

def keyword_match_gyoshu(text: str) -> str:
    """テキストから業種キーワードマッチで分類"""
    scores = {cat: 0 for cat in GYOSHU_CATEGORIES}
    for cat, keywords in GYOSHU_CATEGORIES.items():
        for kw in keywords:
            if kw in text:
                scores[cat] += 1
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else ''

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

def format_tel_digits(d: str) -> str:
    if len(d) == 11:
        if d[:3] in ('090', '080', '070', '050'):
            return f'{d[:3]}-{d[3:7]}-{d[7:]}'
        if d[:4] in ('0120', '0800', '0570', '0990'):
            return f'{d[:4]}-{d[4:7]}-{d[7:]}'
        if d[:2] in ('03', '06'):
            return f'{d[:2]}-{d[2:6]}-{d[6:]}'
        return f'{d[:3]}-{d[3:7]}-{d[7:]}'
    if len(d) == 10:
        if d[:2] in ('03', '06'):
            return f'{d[:2]}-{d[2:6]}-{d[6:]}'
        if d[:4] in ('0120', '0800', '0570', '0990'):
            return f'{d[:4]}-{d[4:7]}-{d[7:]}'
        return f'{d[:3]}-{d[3:6]}-{d[6:]}'
    if len(d) == 9:
        return f'{d[:2]}-{d[2:5]}-{d[5:]}'
    return d

def normalize_tel(t: str) -> str:
    if not t:
        return ''
    t = t.translate(str.maketrans('０１２３４５６７８９－（）　', '0123456789-() '))
    t = re.sub(r'[（\(\)）]', '-', t)
    t = re.sub(r'[\s\u2010\u2011\uff0d]', '-', t)
    t = re.sub(r'-{2,}', '-', t).strip('-')
    t = re.sub(r'[^\d\-]', '', t)
    digits = re.sub(r'\D', '', t)
    if not (9 <= len(digits) <= 11):
        return ''
    if '-' not in t:
        return format_tel_digits(digits)
    return t

def extract_tel_from_text(text: str) -> str:
    for pattern in TEL_PATTERNS:
        for m in pattern.finditer(text):
            n = normalize_tel(m.group(1))
            if n:
                return n
    return ''

def get_search_links(page) -> list:
    links = []
    try:
        for el in page.query_selector_all('a[href]'):
            href = el.get_attribute('href') or ''
            if is_official(href) and href not in links:
                links.append(href)
            if len(links) >= 6:
                break
    except:
        pass
    return links

# ===== tel: リンクDOM取得 =====
def get_tel_from_dom(page) -> str:
    try:
        for el in page.query_selector_all('a[href^="tel:"]'):
            raw = (el.get_attribute('href') or '').replace('tel:', '').strip()
            n = normalize_tel(raw)
            if n:
                print(f'  ✓ tel:リンク: {n}')
                return n
    except:
        pass
    return ''

# ===== コンタクトページ探索 =====
def search_contact_pages(page, base_url: str) -> str:
    base = base_url.rstrip('/')
    for suffix in CONTACT_SUFFIXES:
        try:
            page.goto(base + suffix, timeout=10000, wait_until='domcontentloaded')
            page.wait_for_timeout(600)
            tel = get_tel_from_dom(page) or extract_tel_from_text(page.inner_text('body'))
            if tel:
                print(f'  ✓ コンタクトページ({suffix}): {tel}')
                return tel
        except:
            pass
    return ''

# ===== iタウンページ検索 =====
def search_itp(page, company: str) -> str:
    try:
        page.goto(
            f'https://itp.ne.jp/result/?svc=0&keyword={urllib.parse.quote(company)}',
            timeout=8000, wait_until='domcontentloaded'
        )
        page.wait_for_timeout(1000)
        tel = get_tel_from_dom(page) or extract_tel_from_text(page.inner_text('body'))
        if tel:
            print(f'  ✓ iタウンページ: {tel}')
            return tel
    except:
        pass
    return ''

# ===== Yahoo検索（電番・URL用）=====
def search_yahoo_tel_url(page, company: str, need_url: bool) -> tuple:
    queries = [f'{company} 電話番号' + (' 公式サイト' if need_url else '')]
    queries += [f'{company} 連絡先', f'{company} お問い合わせ 電話', f'{company} TEL 代表']
    all_texts  = []
    found_urls = []
    best_tel   = ''

    for q in queries:
        if best_tel and found_urls:
            break
        try:
            page.goto(
                f'https://search.yahoo.co.jp/search?p={urllib.parse.quote(q)}',
                timeout=20000, wait_until='domcontentloaded'
            )
            page.wait_for_timeout(random.randint(1500, 2200))
            text = page.inner_text('body')
            all_texts.append(f'[Yahoo: {q}]\n{text[:2000]}')

            if not best_tel:
                best_tel = get_tel_from_dom(page) or extract_tel_from_text(text)
                if best_tel:
                    print(f'  ✓ Yahoo({q[:25]}): {best_tel}')
            if not found_urls:
                found_urls = get_search_links(page)
        except Exception as e:
            print(f'  Yahoo検索失敗({q[:20]}): {e}')

        if not best_tel:
            time.sleep(random.uniform(1.2, 2.0))

    return best_tel, (found_urls[0] if found_urls else ''), all_texts

# ===== Yahoo検索（業種用）=====
def search_yahoo_gyoshu(page, company: str) -> str:
    queries = [f'{company} 事業内容', f'{company} 業種', f'{company} 会社概要']
    all_texts = []
    for q in queries:
        try:
            page.goto(
                f'https://search.yahoo.co.jp/search?p={urllib.parse.quote(q)}',
                timeout=20000, wait_until='domcontentloaded'
            )
            page.wait_for_timeout(random.randint(1200, 2000))
            text = page.inner_text('body')
            all_texts.append(f'[Yahoo: {q}]\n{text[:2000]}')
            match = keyword_match_gyoshu(text)
            if match:
                print(f'  ✓ Yahoo業種検索({q[:20]}): {match}')
        except:
            pass
        time.sleep(random.uniform(1.0, 1.8))
    return '\n\n'.join(all_texts)

# ===== Groq API =====
def _groq_call(prompt: str, max_tokens: int = 200) -> str:
    global groq_model_idx, groq_disabled
    if groq_disabled:
        return ''
    while groq_model_idx < len(GROQ_MODELS):
        model = GROQ_MODELS[groq_model_idx]
        try:
            r = requests.post(
                'https://api.groq.com/openai/v1/chat/completions',
                headers={'Authorization': f'Bearer {GROQ_API_KEY}'},
                json={'model': model,
                      'messages': [{'role': 'user', 'content': prompt}],
                      'temperature': 0, 'max_tokens': max_tokens},
                timeout=30
            )
            if r.status_code == 200:
                return r.json()['choices'][0]['message']['content'].strip()
            elif r.status_code == 429:
                print(f'  [Groq 429] {model} → 65秒待機後 次モデルへ')
                time.sleep(65)
                groq_model_idx += 1
                if groq_model_idx >= len(GROQ_MODELS):
                    print('  [Groq] 全モデル制限 → 無効化')
                    groq_disabled = True
                    return ''
            elif r.status_code == 403:
                print('  [Groq 403] 認証エラー → 無効化')
                groq_disabled = True
                return ''
            else:
                return ''
        except Exception as e:
            print(f'  [Groq ERROR] {e}')
            return ''
    return ''

def groq_extract_tel_url(company: str, text: str) -> dict:
    prompt = (
        f'以下のテキストから「{company}」の情報を抽出してください。\n'
        '・tel: 代表電話番号を1つ(ハイフン区切り例:03-1234-5678)。不明はnull。\n'
        '・url: 公式サイトURL1つ(求人・口コミ・SNS除く)。不明はnull。\n'
        f'テキスト:\n{text[:4000]}\n\n'
        'JSONのみ返答: {"tel": "...", "url": "..."}'
    )
    raw = _groq_call(prompt)
    if raw:
        try:
            m = re.search(r'\{.*?\}', raw, re.DOTALL)
            return json.loads(m.group()) if m else {}
        except:
            pass
    return {}

def groq_classify_gyoshu(company: str, text: str) -> str:
    """会社の業種を定義済みカテゴリに分類。必ず何かを返す。"""
    prompt = (
        f'「{company}」の事業内容・業種を以下のカテゴリから1つだけ選んでください。\n'
        f'カテゴリ: {GYOSHU_LIST_STR}\n\n'
        '・会社の主な事業に最も近いカテゴリを選ぶ\n'
        '・どれにも当てはまらない場合は「その他」\n'
        '・カテゴリ名のみ返答（説明不要）\n\n'
        f'参考テキスト:\n{text[:3000]}\n\n'
        '回答:'
    )
    result = _groq_call(prompt, max_tokens=50)
    if not result:
        return ''
    # カテゴリ名が含まれているか確認
    for cat in GYOSHU_CATEGORIES:
        if cat in result:
            return cat
    if 'その他' in result:
        return 'その他'
    return ''

# ===== メインスクレイパー =====
def scrape_company(page, company: str, existing_url: str,
                   need_tel: bool, need_url: bool, need_gyoshu: bool) -> dict:
    result    = {'tel': '', 'url': '', 'gyoshu': ''}
    all_texts = []
    found_url = existing_url

    # =========================================================
    # STEP 1: 既存URLを直接訪問 → tel:DOM + テキスト + 業種
    # =========================================================
    if existing_url:
        try:
            page.goto(existing_url, timeout=15000, wait_until='domcontentloaded')
            page.wait_for_timeout(random.randint(1000, 1800))

            if need_tel:
                tel = get_tel_from_dom(page)
                if tel:
                    result['tel'] = tel

            site_text = page.inner_text('body')
            all_texts.append(f'[{existing_url}]\n{site_text[:2500]}')

            if need_tel and not result['tel']:
                result['tel'] = extract_tel_from_text(site_text)

            if need_gyoshu:
                result['gyoshu'] = keyword_match_gyoshu(site_text)

        except Exception as e:
            print(f'  既存URL訪問失敗: {type(e).__name__}')

    # =========================================================
    # STEP 2: コンタクトページ探索（電番まだ不明）
    # =========================================================
    if existing_url and need_tel and not result['tel']:
        result['tel'] = search_contact_pages(page, existing_url)

    # =========================================================
    # STEP 3: iタウンページ（電番まだ不明）
    # =========================================================
    if need_tel and not result['tel']:
        result['tel'] = search_itp(page, company)

    # =========================================================
    # STEP 4: Yahoo検索（電番・URL）
    # =========================================================
    if (need_tel and not result['tel']) or need_url:
        tel_y, url_y, yahoo_texts = search_yahoo_tel_url(page, company, need_url)
        all_texts.extend(yahoo_texts)

        if need_tel and not result['tel'] and tel_y:
            result['tel'] = tel_y
        if need_url and not found_url and url_y:
            found_url = url_y

        # 検索で発見したURLも訪問
        if url_y and url_y != existing_url:
            try:
                page.goto(url_y, timeout=15000, wait_until='domcontentloaded')
                page.wait_for_timeout(random.randint(800, 1400))

                if need_tel and not result['tel']:
                    tel = get_tel_from_dom(page)
                    if tel:
                        result['tel'] = tel

                site_text_y = page.inner_text('body')
                all_texts.append(f'[{url_y}]\n{site_text_y[:2500]}')

                if need_tel and not result['tel']:
                    result['tel'] = extract_tel_from_text(site_text_y)
                    if not result['tel']:
                        result['tel'] = search_contact_pages(page, url_y)

                if need_gyoshu and not result['gyoshu']:
                    result['gyoshu'] = keyword_match_gyoshu(site_text_y)
            except:
                pass

    # =========================================================
    # STEP 5: Yahoo業種検索（業種まだ不明）
    # =========================================================
    if need_gyoshu and not result['gyoshu']:
        yahoo_gyoshu_text = search_yahoo_gyoshu(page, company)
        if yahoo_gyoshu_text:
            all_texts.append(yahoo_gyoshu_text)
            result['gyoshu'] = keyword_match_gyoshu(yahoo_gyoshu_text)

    # =========================================================
    # STEP 6: Groq（電番・URL・業種）
    # =========================================================
    combined = '\n\n'.join(all_texts)

    if (need_tel and not result['tel']) or (need_url and not found_url):
        extracted = groq_extract_tel_url(company, combined)
        raw_tel = str(extracted.get('tel') or '')
        raw_url = str(extracted.get('url') or '')
        if need_tel and not result['tel'] and raw_tel not in ('null', 'None', ''):
            t = normalize_tel(raw_tel)
            if t:
                print(f'  ✓ Groq tel: {t}')
                result['tel'] = t
        if need_url and not found_url and raw_url not in ('null', 'None', '') and is_official(raw_url):
            print(f'  ✓ Groq url: {raw_url[:60]}')
            found_url = raw_url

    if need_gyoshu and not result['gyoshu'] and combined:
        g = groq_classify_gyoshu(company, combined)
        if g:
            result['gyoshu'] = g

    # =========================================================
    # STEP 7: regex fallback（電番）
    # =========================================================
    if need_tel and not result['tel']:
        result['tel'] = extract_tel_from_text(combined)

    if need_url:
        result['url'] = found_url

    # =========================================================
    # STEP 8: 業種の最終フォールバック → 必ず「その他」を入れる
    # =========================================================
    if need_gyoshu and not result['gyoshu']:
        result['gyoshu'] = 'その他'

    return result

# ===== メイン =====
def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--n',     type=int, default=1, help='このインスタンスの番号 (1始まり)')
    parser.add_argument('--total', type=int, default=1, help='並列起動する総インスタンス数')
    args = parser.parse_args()
    instance_n     = args.n
    instance_total = args.total

    print(f'=== circusリスト スクレイパー インスタンス {instance_n}/{instance_total} ===\n')
    token = get_token()

    res  = sheets_get(token, f'{SHEET_NAME}!A1:F1200')
    rows = res.get('values', [])

    all_targets = []
    for i, row in enumerate(rows[1:], start=2):
        company      = (row[0] if len(row) > 0 else '').strip()
        tel          = (row[2] if len(row) > 2 else '').strip()
        existing_url = (row[3] if len(row) > 3 else '').strip()
        gyoshu       = (row[4] if len(row) > 4 else '').strip()

        if not company:
            continue

        need_tel    = not tel
        need_url    = not existing_url
        need_gyoshu = not gyoshu

        if need_tel or need_url or need_gyoshu:
            all_targets.append({
                'row': i, 'company': company,
                'existing_url': existing_url,
                'need_tel': need_tel, 'need_url': need_url, 'need_gyoshu': need_gyoshu,
            })

    # インターリーブ分割
    targets = [t for idx, t in enumerate(all_targets) if idx % instance_total == (instance_n - 1)]
    total = len(targets)
    print(f'全体: {len(all_targets)}件 → このインスタンス担当: {total}件\n')

    success_tel    = 0
    success_url    = 0
    success_gyoshu = 0
    success_rank   = 0

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
            company = t['company']
            tasks = []
            if t['need_tel']:    tasks.append('電番')
            if t['need_url']:    tasks.append('URL')
            if t['need_gyoshu']: tasks.append('業種')
            print(f'[{idx}/{total}] {company}  [取得: {"/".join(tasks)}]')

            result = scrape_company(
                page, company, t['existing_url'],
                t['need_tel'], t['need_url'], t['need_gyoshu']
            )

            tel_out    = result['tel']
            url_out    = result['url']
            gyoshu_out = result['gyoshu']
            rank_out   = gyoshu_to_rank(gyoshu_out) if gyoshu_out else ''

            print(f'  TEL:  {tel_out or "(不明)"}')
            print(f'  URL:  {url_out[:65] if url_out else "(不明)"}')
            print(f'  業種: {gyoshu_out}  ランク: {rank_out}')

            row_num = t['row']
            if t['need_tel'] and tel_out:
                sheets_update(token, f'{SHEET_NAME}!C{row_num}', [[tel_out]])
                success_tel += 1

            if t['need_url'] and url_out:
                sheets_update(token, f'{SHEET_NAME}!D{row_num}', [[url_out]])
                success_url += 1

            if t['need_gyoshu'] and gyoshu_out:
                sheets_update(token, f'{SHEET_NAME}!E{row_num}', [[gyoshu_out]])
                success_gyoshu += 1
                if rank_out:
                    sheets_update(token, f'{SHEET_NAME}!F{row_num}', [[rank_out]])
                    success_rank += 1

            if idx % 20 == 0:
                token = get_token()

            wait = random.uniform(4, 7)
            print(f'  → {wait:.1f}秒待機\n')
            time.sleep(wait)

        browser.close()

    print('=' * 50)
    print(f'✅ 完了！')
    print(f'   電話番号: {success_tel}/{sum(1 for t in targets if t["need_tel"])}件 取得')
    print(f'   URL:      {success_url}/{sum(1 for t in targets if t["need_url"])}件 取得')
    print(f'   業種:     {success_gyoshu}/{sum(1 for t in targets if t["need_gyoshu"])}件 取得')
    print(f'   ランク:   {success_rank}/{sum(1 for t in targets if t["need_gyoshu"])}件 取得')

if __name__ == '__main__':
    main()
