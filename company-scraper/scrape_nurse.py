"""
看護 媒体ﾘｽﾄ たま作業中 スクレイパー

列構成:
  A: 会社名
  B: 職種（読み取りのみ）
  C: 電話番号
  D: 公式サイトURL
  E: ナニ科（診療科・施設種別）

取得ロジック（多段フォールバック）:
  電番/URL: tel:DOM → コンタクトページ → iタウン → Yahoo複数クエリ → Groq → 強化regex
  診療科:   公式URL訪問 → 診療科ページ探索 → Yahoo検索 → Groq → キーワードマッチ
"""
import os, sys, re, time, random, json, urllib.parse, urllib.request
sys.stdout.reconfigure(encoding='utf-8')

import requests
from playwright.sync_api import sync_playwright

# ===== 設定 =====
CREDS_PATH   = 'C:/Users/弁護士法人響/.config/gws/authorized_user.json'
SSID         = '1Gg-2dcjTyrdDJy_t45kwNq3FJUB5kgXPer8nQKtVHhw'
SHEET_NAME   = '看護 媒体ﾘｽﾄ たま作業中'
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
    # 医療・介護系ディレクトリ（公式サイトではない）
    'mhlw.go.jp',       # 厚生労働省・医療機関検索
    'caloo.jp',         # 病院検索サイト
    'medley.life',      # 病院・クリニック検索
    'qlife.jp',         # 病院検索
    'minnano-kaigo.com',# 介護施設検索
    'kaigonohonne.com', # 介護施設検索
    'kaigo.com',        # 介護検索
    'e-kaigo.net',      # 介護検索
    'homemate-rc.',     # 施設検索
    'ucare.tokyo',      # 医療検索
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

# 診療科ページのサフィックス候補
DEPT_SUFFIXES = [
    '/department', '/department/',
    '/shinryoka', '/shinryo',
    '/診療科', '/科目',
    '/service', '/service/',
    '/services', '/services/',
    '/medical', '/medical/',
    '/about/department',
    '/about/medical',
    '/clinic',
    '/care',
]

# 電話番号パターン（優先度順）
TEL_PATTERNS = [
    re.compile(r'(?:電話|TEL|Tel|tel|☎|📞)[^\d]{0,8}(0\d[\d\-－\(\)（）\s]{7,14}\d)'),
    re.compile(r'(?<!\d)(0\d{1,4}[-－]\d{1,4}[-－]\d{3,4})(?!\d)'),
    re.compile(r'(?<!\d)(0\d{1,4}[（\(]\d{1,4}[）\)]\d{3,4})(?!\d)'),
    re.compile(r'(?<!\d)(0[789]0\d{8}|0\d{9,10})(?!\d)'),
    re.compile(r'(?<!\d)(0\d{1,4}[\s　]\d{1,4}[\s　]\d{3,4})(?!\d)'),
]

# 診療科キーワード（細分類）
DEPT_KEYWORDS = [
    # 内科系
    '内科', '循環器内科', '循環器科', '消化器内科', '消化器科', '呼吸器内科', '呼吸器科',
    '腎臓内科', '内分泌内科', '代謝内科', '糖尿病内科', '神経内科', '脳神経内科',
    '血液内科', '腫瘍内科', 'アレルギー科', '膠原病内科', 'リウマチ科', '感染症内科',
    '老年内科', '総合内科', '一般内科',
    # 外科系
    '外科', '消化器外科', '消化器・一般外科', '一般外科', '心臓血管外科', '呼吸器外科',
    '乳腺外科', '乳腺・内分泌外科', '小児外科', '脳神経外科', '形成外科', '美容外科',
    '整形外科', '骨折外科', '関節外科',
    # 専門科
    '産婦人科', '産科', '婦人科', '小児科', '新生児科', '小児神経科',
    '眼科', '耳鼻咽喉科', '耳鼻科', '皮膚科', '泌尿器科', '腎臓科',
    '精神科', '神経科', '心療内科', '精神神経科',
    '歯科', '口腔外科', '矯正歯科', '小児歯科', '歯科口腔外科',
    '麻酔科', '放射線科', '放射線治療科', '核医学科',
    'リハビリテーション科', 'リハビリ科', 'リハビリテーション',
    '救急科', '救急・総合診療科', '総合診療科', '総合診療',
    '病理診断科', '臨床検査科',
    # 介護・看護系施設
    '訪問看護', '訪問介護', '訪問診療', '在宅医療', '在宅診療',
    '老人保健施設', '介護老人保健施設', '特別養護老人ホーム', '特養',
    'デイサービス', '通所介護', '通所リハビリ', '通所リハビリテーション',
    'グループホーム', '認知症対応型', '有料老人ホーム', 'サービス付き高齢者向け住宅',
    '居宅介護支援', 'ケアマネジャー', '地域包括支援センター',
    '障害者支援', '就労支援', '放課後等デイサービス',
    # 施設種別
    '病院', 'クリニック', '診療所', '医院', '歯科医院', 'センター',
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

def format_tel_digits(d: str) -> str:
    """数字のみの電話番号をハイフン区切りにフォーマット"""
    if len(d) == 11:
        if d[:3] in ('090', '080', '070', '050'):
            return f'{d[:3]}-{d[3:7]}-{d[7:]}'
        if d[:4] in ('0120', '0800', '0570', '0990'):
            return f'{d[:4]}-{d[4:7]}-{d[7:]}'
        # 市外局番2桁（03, 06）+ 残り9桁 = 11桁
        if d[:2] in ('03', '06'):
            return f'{d[:2]}-{d[2:6]}-{d[6:]}'
        return f'{d[:3]}-{d[3:7]}-{d[7:]}'
    if len(d) == 10:
        if d[:2] in ('03', '06'):
            return f'{d[:2]}-{d[2:6]}-{d[6:]}'
        # フリーダイヤル・特番（4桁プレフィックス）
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
    # ハイフンが入っていない場合は整形する
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

# ===== 診療科キーワードマッチ =====
def extract_dept_by_keyword(text: str) -> str:
    """テキストから診療科キーワードにマッチするものを全て抽出"""
    found = []
    for kw in DEPT_KEYWORDS:
        if kw in text and kw not in found:
            found.append(kw)
    return '・'.join(found) if found else ''

# ===== tel: リンクDOM直接取得 =====
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

# ===== 診療科ページ探索 =====
def search_dept_pages(page, base_url: str) -> str:
    """診療科専用ページを探して科目テキストを収集"""
    base = base_url.rstrip('/')
    collected = []
    for suffix in DEPT_SUFFIXES:
        try:
            page.goto(base + suffix, timeout=10000, wait_until='domcontentloaded')
            page.wait_for_timeout(600)
            text = page.inner_text('body')
            dept = extract_dept_by_keyword(text)
            if dept:
                print(f'  ✓ 診療科ページ({suffix}): {dept[:50]}')
                collected.append(text[:3000])
        except:
            pass
    return '\n\n'.join(collected) if collected else ''

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

# ===== Yahoo検索（電番・URL用） =====
def search_yahoo_tel_url(page, company: str, need_url: bool) -> tuple:
    queries = [f'{company} 電話番号' + (' 公式サイト' if need_url else '')]
    queries += [
        f'{company} 連絡先',
        f'{company} お問い合わせ 電話',
        f'{company} TEL 代表',
    ]
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

    official_url = found_urls[0] if found_urls else ''
    return best_tel, official_url, all_texts

# ===== Yahoo検索（診療科用） =====
def search_yahoo_dept(page, company: str) -> str:
    queries = [
        f'{company} 診療科',
        f'{company} 診療内容',
        f'{company} 科目',
    ]
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
            dept = extract_dept_by_keyword(text)
            if dept:
                print(f'  ✓ Yahoo診療科検索({q[:20]}): {dept[:50]}')
        except Exception as e:
            print(f'  Yahoo診療科検索失敗({q[:20]}): {e}')
        time.sleep(random.uniform(1.0, 1.8))
    return '\n\n'.join(all_texts)

# ===== Groq API =====
def groq_extract_tel_url(company: str, text: str) -> dict | None:
    global groq_model_idx, groq_disabled
    if groq_disabled:
        return None

    prompt = (
        f'以下のテキストから「{company}」の情報を抽出してください。\n'
        '・tel: 代表電話番号を1つ(ハイフン区切り例:03-1234-5678)。不明はnull。\n'
        '・url: 公式サイトURL1つ(求人・口コミ・SNS除く)。不明はnull。\n'
        f'テキスト:\n{text[:4000]}\n\n'
        'JSONのみ返答: {"tel": "...", "url": "..."}'
    )
    return _groq_call(prompt)

def groq_extract_dept(company: str, text: str) -> str:
    """診療科をできるだけ細かく抽出するGroqプロンプト"""
    global groq_model_idx, groq_disabled
    if groq_disabled:
        return ''

    prompt = (
        f'以下のテキストから「{company}」が行っている診療科・サービス・施設種別を\n'
        'できるだけ細かく・網羅的に日本語で列挙してください。\n'
        '・病院・クリニックなら具体的な科目名（内科、外科、整形外科 など）\n'
        '・介護施設なら施設種別とサービス（訪問看護、デイサービス など）\n'
        '・複数ある場合は「・」区切りで全て列挙\n'
        '・不明・対象外の場合は「不明」と返す\n'
        '・余計な説明は不要。科目名のみ返す\n'
        f'\nテキスト:\n{text[:4000]}\n\n'
        '回答例: 内科・外科・整形外科・小児科\n'
        '回答:'
    )

    result = _groq_call_text(prompt)
    if result and result != '不明':
        # 改行・余計な記号を整理
        result = re.sub(r'[\n\r]+', '・', result.strip())
        result = re.sub(r'[、,，,]+', '・', result)
        result = re.sub(r'・{2,}', '・', result).strip('・')
        print(f'  ✓ Groq診療科: {result[:60]}')
        return result
    return ''

def _groq_call(prompt: str) -> dict | None:
    global groq_model_idx, groq_disabled
    if groq_disabled:
        return None
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

def _groq_call_text(prompt: str) -> str:
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
                      'temperature': 0, 'max_tokens': 300},
                timeout=30
            )
            if r.status_code == 200:
                return r.json()['choices'][0]['message']['content'].strip()
            elif r.status_code == 429:
                print(f'  [Groq 429] {model} → 65秒待機後 次モデルへ')
                time.sleep(65)
                groq_model_idx += 1
                if groq_model_idx >= len(GROQ_MODELS):
                    groq_disabled = True
                    return ''
            elif r.status_code == 403:
                groq_disabled = True
                return ''
            else:
                return ''
        except Exception as e:
            print(f'  [Groq ERROR] {e}')
            return ''
    return ''

# ===== メインスクレイパー =====
def scrape_company(page, company: str, existing_url: str,
                   need_tel: bool, need_url: bool, need_dept: bool) -> dict:
    result    = {'tel': '', 'url': '', 'dept': ''}
    all_texts = []
    found_url = existing_url

    # =========================================================
    # STEP 1: 既存URLがあれば直接訪問 → tel:DOM + テキスト + 診療科
    # =========================================================
    site_text_main = ''
    if existing_url:
        try:
            page.goto(existing_url, timeout=15000, wait_until='domcontentloaded')
            page.wait_for_timeout(random.randint(1000, 1800))

            if need_tel:
                tel = get_tel_from_dom(page)
                if tel:
                    result['tel'] = tel

            site_text_main = page.inner_text('body')
            all_texts.append(f'[{existing_url}]\n{site_text_main[:2500]}')

            if need_tel and not result['tel']:
                result['tel'] = extract_tel_from_text(site_text_main)

            if need_dept:
                result['dept'] = extract_dept_by_keyword(site_text_main)

        except Exception as e:
            print(f'  既存URL訪問失敗: {type(e).__name__}')

    # =========================================================
    # STEP 2: 診療科ページ専用探索（既存URLがある場合）
    # =========================================================
    if existing_url and need_dept and not result['dept']:
        dept_text = search_dept_pages(page, existing_url)
        if dept_text:
            all_texts.append(dept_text)
            result['dept'] = extract_dept_by_keyword(dept_text)

    # =========================================================
    # STEP 3: コンタクトページ探索（電番まだ不明の場合）
    # =========================================================
    if existing_url and need_tel and not result['tel']:
        result['tel'] = search_contact_pages(page, existing_url)

    # =========================================================
    # STEP 4: iタウンページ（電番まだ不明）
    # =========================================================
    if need_tel and not result['tel']:
        result['tel'] = search_itp(page, company)

    # =========================================================
    # STEP 5: Yahoo検索（電番/URL用）
    # =========================================================
    if (need_tel and not result['tel']) or need_url:
        tel_y, url_y, yahoo_texts = search_yahoo_tel_url(page, company, need_url)
        all_texts.extend(yahoo_texts)

        if need_tel and not result['tel'] and tel_y:
            result['tel'] = tel_y

        if need_url and not found_url and url_y:
            found_url = url_y

        # 検索で発見したURLも訪問
        if url_y and url_y != existing_url and (need_tel and not result['tel'] or need_dept):
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

                if need_dept and not result['dept']:
                    result['dept'] = extract_dept_by_keyword(site_text_y)
                    if not result['dept']:
                        dept_text = search_dept_pages(page, url_y)
                        if dept_text:
                            all_texts.append(dept_text)
                            result['dept'] = extract_dept_by_keyword(dept_text)

            except:
                pass

    # =========================================================
    # STEP 6: Yahoo診療科検索（診療科まだ不明の場合）
    # =========================================================
    if need_dept and not result['dept']:
        yahoo_dept_text = search_yahoo_dept(page, company)
        if yahoo_dept_text:
            all_texts.append(yahoo_dept_text)
            result['dept'] = extract_dept_by_keyword(yahoo_dept_text)

    # =========================================================
    # STEP 7: Groq（全収集テキストに対して）
    # =========================================================
    combined = '\n\n'.join(all_texts)
    still_need_tel  = need_tel  and not result['tel']
    still_need_url  = need_url  and not found_url
    still_need_dept = need_dept and not result['dept']

    if (still_need_tel or still_need_url) and combined:
        extracted = groq_extract_tel_url(company, combined)
        if extracted:
            raw_tel = str(extracted.get('tel') or '')
            raw_url = str(extracted.get('url') or '')
            if still_need_tel and raw_tel not in ('null', 'None', ''):
                t = normalize_tel(raw_tel)
                if t:
                    print(f'  ✓ Groq tel: {t}')
                    result['tel'] = t
            if still_need_url and raw_url not in ('null', 'None', '') and is_official(raw_url):
                print(f'  ✓ Groq url: {raw_url[:60]}')
                found_url = raw_url

    if still_need_dept and combined:
        dept = groq_extract_dept(company, combined)
        if dept:
            result['dept'] = dept

    # =========================================================
    # STEP 8: 強化regex fallback（全テキスト結合）
    # =========================================================
    if need_tel and not result['tel']:
        result['tel'] = extract_tel_from_text(combined)

    if need_url:
        result['url'] = found_url

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

    print(f'=== 看護媒体リスト スクレイパー インスタンス {instance_n}/{instance_total} ===\n')
    token = get_token()

    res  = sheets_get(token, f'{SHEET_NAME}!A1:E1200')
    rows = res.get('values', [])

    all_targets = []
    for i, row in enumerate(rows[1:], start=2):
        company      = (row[0] if len(row) > 0 else '').strip()
        tel          = (row[2] if len(row) > 2 else '').strip()
        existing_url = (row[3] if len(row) > 3 else '').strip()
        dept         = (row[4] if len(row) > 4 else '').strip()

        if not company:
            continue

        need_tel  = not tel
        need_url  = not existing_url
        need_dept = not dept

        if need_tel or need_url or need_dept:
            all_targets.append({
                'row': i, 'company': company,
                'existing_url': existing_url,
                'need_tel': need_tel, 'need_url': need_url, 'need_dept': need_dept,
            })

    # インターリーブ分割
    targets = [t for idx, t in enumerate(all_targets) if idx % instance_total == (instance_n - 1)]

    total = len(targets)
    print(f'全体: {len(all_targets)}件 → このインスタンス担当: {total}件\n')

    success_tel  = 0
    success_url  = 0
    success_dept = 0
    failed_tel   = []

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
            if t['need_tel']:  tasks.append('電番')
            if t['need_url']:  tasks.append('URL')
            if t['need_dept']: tasks.append('診療科')
            print(f'[{idx}/{total}] {company}  [取得: {"/".join(tasks)}]')

            result = scrape_company(
                page, company, t['existing_url'],
                t['need_tel'], t['need_url'], t['need_dept']
            )

            tel_out  = result['tel']
            url_out  = result['url']
            dept_out = result['dept']
            print(f'  TEL:  {tel_out or "(不明)"}')
            print(f'  URL:  {url_out[:65] if url_out else "(不明)"}')
            print(f'  科目: {dept_out[:60] if dept_out else "(不明)"}')

            row_num = t['row']
            if t['need_tel'] and tel_out:
                sheets_update(token, f'{SHEET_NAME}!C{row_num}', [[tel_out]])
                success_tel += 1
            elif t['need_tel']:
                failed_tel.append(company)

            if t['need_url'] and url_out:
                sheets_update(token, f'{SHEET_NAME}!D{row_num}', [[url_out]])
                success_url += 1

            if t['need_dept'] and dept_out:
                sheets_update(token, f'{SHEET_NAME}!E{row_num}', [[dept_out]])
                success_dept += 1

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
    print(f'   診療科:   {success_dept}/{sum(1 for t in targets if t["need_dept"])}件 取得')
    if failed_tel:
        print(f'\n❌ 電番取得できなかった会社 ({len(failed_tel)}件):')
        for c in failed_tel:
            print(f'   - {c}')

if __name__ == '__main__':
    main()
