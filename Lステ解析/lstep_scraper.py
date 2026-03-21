import asyncio
import csv
import json
import re
import os
import sys
import unicodedata
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
from playwright.async_api import async_playwright, Playwright

# --- 設定項目 ---
LOGIN_URL = "https://manager.linestep.net/account/login"
LSTEP_BASE_URL = "https://manager.linestep.net"

ACCOUNTS_FILE = r"C:\Users\弁護士法人響\Desktop\-\Lステ解析\アカウント.json"
CSV_FILE = r"C:\Users\弁護士法人響\Desktop\-\Lステ解析\処理用シート - シート1.csv"
LOG_FILE = r"C:\Users\弁護士法人響\Desktop\-\Lステ解析\result_log.csv"

# テスト用: 何行目から開始するか（0 = 最初から）、何件処理するか（0 = 全件）
TEST_START = 2164
TEST_LIMIT = 0
# ピンポイント指定（空リストの場合は無効）
TEST_ROWS = []

CREDENTIALS = {
    "username": "double_juno",
    "password": "evhiBp4B"
}

KEYWORDS = ["解約", "キャンセル", "クーリングオフ"]

LOGIN_USERNAME_SELECTOR = "input#input_name"
LOGIN_PASSWORD_SELECTOR = "input#input_password"

CHAT_CONTAINER_SELECTOR = ".tw-overflow-y-scroll"
LOAD_MORE_BUTTON_SELECTOR = 'button[data-testid="linyBtn"]'
# data-message-id が負値 → 日付ヘッダー、正値 → メッセージ/システムイベント
DATE_HEADER_SELECTOR = "div[data-message-id^='-'] p.tw-text-center"
MESSAGE_CONTENT_SELECTOR = "p.text-content"  # 実メッセージ本文のみ（システムイベントは p.tw-text-center なので除外される）

# --- 補助関数 ---

def extract_account_name(cell_text):
    """セル内テキストからアカウント名を抽出（旧・新フォーマット両対応）"""
    # 旧フォーマット: アカウント：xxx
    m = re.search(r'アカウント[：:]\s*(.+)', cell_text)
    if m:
        return m.group(1).strip()

    # 新フォーマット: LステURLの前後の行からアカウント名を取得
    lines = [l.strip() for l in cell_text.strip().split('\n')]
    lstep_pattern = re.compile(r'https://manager\.linestep\.net')
    lstep_idx = next((j for j, l in enumerate(lines) if lstep_pattern.search(l)), None)
    if lstep_idx is None:
        return None

    candidates = []
    if lstep_idx > 0:
        candidates.append(lines[lstep_idx - 1])
    if lstep_idx + 1 < len(lines):
        candidates.append(lines[lstep_idx + 1])

    for candidate in candidates:
        name = normalize_bracket_name(candidate)
        if name:
            return name
    return None

def normalize_bracket_name(text):
    """＜＞【】〈〉<>ブラケットからアカウント名を抽出・正規化"""
    if not text or 'http' in text or re.match(r'ID[：:Ｆ]', text):
        return None

    # ＜...＞ / 〈...〉 / <...> パターン（全角・半角混在も対応）
    m = re.search(r'[＜〈<](.+?)[＞〉>]', text)
    if m:
        inner = m.group(1).strip()
        # SP経由を含む場合はSPアカウントとして扱う
        if 'SP経由' in inner:
            return 'SP'
        # 内部に【】があればその中を優先（例: 【ED治療】アトムクリニック → ED治療）
        m2 = re.search(r'[【\[](.+?)[】\]]', inner)
        if m2:
            return m2.group(1).strip()
        # （）内の補足説明を除去
        inner = re.sub(r'[（(].+?[）)]', '', inner).strip()
        return inner if inner else None

    # 【...】単独パターン
    m = re.search(r'[【\[](.+?)[】\]]', text)
    if m:
        return m.group(1).strip()

    # ブラケットなし: URLや患者ID行でなければそのまま返す
    if not re.search(r'https?://', text) and len(text) < 30:
        return text
    return None

def normalize_for_match(text):
    """マッチング用正規化: 全角→半角, コンマ除去, 空白正規化"""
    text = unicodedata.normalize('NFKC', text)
    text = re.sub(r'[,，、]', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def find_account_id(accounts, name):
    """アカウント名からIDを検索（強化版）"""
    if not name:
        return ""

    # --- 前処理: ノイズ除去 ---
    # Lステ種別：プレフィックス除去
    name = re.sub(r'^Lステ種別[：:]\s*', '', name).strip()
    # 壊れたブラケット除去（例: 【ED治療 → ED治療）
    name = re.sub(r'^[【\[〈＜<]+', '', name).strip()
    # 全角・半角 先頭（）ブラケット除去（例: （AND美容外科）ポイントアカウント → ポイントアカウント）
    name = re.sub(r'^[（(].+?[）)]\s*', '', name).strip()
    # 異体字統一（瘦→痩）
    name = name.replace('瘦', '痩')

    norm = normalize_for_match(name)

    # === 特殊パターン優先マッチング ===

    # SP 含有（例: ATOM（SP）/ ATOM CLINIC（SP経由））→ SPアカウント
    if re.search(r'[（(]SP[）)経]', norm) and 'SP' in accounts:
        return accounts['SP']

    # メディア経由を含む名前（例: メディア経由・980円クーポン）→ メディア経由優先
    if name.startswith('メディア') and 'メディア経由' in accounts:
        return accounts['メディア経由']

    # （メディア）サフィックス（例: ATOM CLINIC(メディア)）→ メディア経由
    if re.search(r'[（(]メディア[）)]', norm) and 'メディア経由' in accounts:
        return accounts['メディア経由']

    # 会員 含有（例: アトム会員様 / アトム会員様ご連絡用アカウント）→ 会員様アカウント
    if '会員' in name and '会員様アカウント' in accounts:
        return accounts['会員様アカウント']

    # P-strong 系 (Pスト / Pストロング / Pstrong / Pst / P-storong)
    if re.search(r'^[Pp]スト|^[Pp]ストロング', name):
        if re.search(r'980', norm) and 'Pスト980訴求' in accounts:
            return accounts['Pスト980訴求']
        if 'P-strong' in accounts:
            return accounts['P-strong']
    if re.search(r'^[Pp][- ]?st', norm, re.IGNORECASE):
        if re.search(r'980', norm) and 'Pスト980訴求' in accounts:
            return accounts['Pスト980訴求']
        if 'P-strong' in accounts:
            return accounts['P-strong']

    # 9800 系 → 9800円訴求（9,800 / 9800 / 9800訴求 など）
    if re.search(r'9[,，]?800', norm):
        if '9800円訴求' in accounts:
            return accounts['9800円訴求']

    # 980 系 → 980円訴求（9800系はすでに上で処理済み）
    if re.search(r'980', norm):
        if '980円訴求' in accounts:
            return accounts['980円訴求']

    # coupon / クーポン
    if re.search(r'coupon|クーポン', norm, re.IGNORECASE):
        if re.search(r'アトム|atom', norm, re.IGNORECASE) and 'アトムcoupon' in accounts:
            return accounts['アトムcoupon']
        if 'クーポン' in accounts:
            return accounts['クーポン']

    # AGA → アトムAGA
    if 'AGA' in norm and 'アトムAGA' in accounts:
        return accounts['アトムAGA']

    # === 通常マッチング ===
    norm_lower = norm.lower()
    norm_accounts = [(k, normalize_for_match(k).lower(), v) for k, v in accounts.items()]

    # 1. 完全一致（元の名前）
    if name in accounts:
        return accounts[name]

    # 2. NFKC正規化 + 大文字小文字無視
    for k, kn, v in norm_accounts:
        if kn == norm_lower:
            return v

    # 3. ハイフン・スペース除去（Pstrong ↔ P-strong）
    stripped = re.sub(r'[-\s]', '', norm_lower)
    for k, kn, v in norm_accounts:
        if re.sub(r'[-\s]', '', kn) == stripped:
            return v

    # 4. 円除去（980訴求 ↔ 980円訴求）
    no_yen = re.sub(r'円', '', norm_lower)
    for k, kn, v in norm_accounts:
        if re.sub(r'円', '', kn) == no_yen:
            return v

    # 5. 前方一致（JSONキーがCSV名で始まる: メディア → メディア経由）
    for k, kn, v in norm_accounts:
        if kn.startswith(norm_lower) or k.startswith(name):
            return v

    # 6. 後方一致（CSV名がJSONキーで始まる、最低3文字）
    for k, kn, v in norm_accounts:
        if len(kn) >= 3 and (norm_lower.startswith(kn) or name.startswith(k)):
            return v

    return ""

def load_accounts(file_path):
    try:
        if not os.path.exists(file_path):
            print(f"❌ アカウントファイルが見つかりません: {file_path}")
            return {}
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        result = {}
        for acc in data:
            acc_id = acc.get('id')
            name = acc.get('name')
            if not name:
                continue
            # "/" で区切られた名前をすべてのバリアントとして登録
            for variant in name.split('/'):
                key = variant.strip()
                if key:
                    result[key] = acc_id
        return result
    except Exception as e:
        print(f"⚠️ アカウントファイル読み込みエラー: {e}")
        return {}

def read_csv(file_path):
    try:
        if not os.path.exists(file_path):
            print(f"❌ CSVファイルが見つかりません: {file_path}")
            return []
        with open(file_path, 'r', encoding='utf-8-sig', newline='') as f:
            return list(csv.reader(f))
    except Exception as e:
        print(f"⚠️ CSV読み込みエラー: {e}")
        return []

def write_log(row_num, patient_id, account_name, result, detail=""):
    try:
        with open(LOG_FILE, 'a', encoding='utf-8-sig', newline='') as lf:
            csv.writer(lf).writerow([row_num, patient_id, account_name, result, detail])
    except Exception as e:
        print(f"⚠️ ログ書き込みエラー: {e}")

def write_csv(file_path, data):
    try:
        with open(file_path, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.writer(f)
            writer.writerows(data)
        print(f"💾 進捗をCSVに保存しました")
    except Exception as e:
        print(f"❌ CSV書き込みエラー: {e}")

async def load_all_chat_history(page):
    """「続きをロード」ボタンを繰り返しクリックして全履歴を表示させる"""
    print("⏳ 過去ログを遡っています...")
    while True:
        btn = page.locator(LOAD_MORE_BUTTON_SELECTOR).filter(has_text="続きをロード")
        if await btn.count() > 0 and await btn.is_visible():
            await btn.click()
            await asyncio.sleep(2)
        else:
            break
    print("✅ すべての履歴を表示しました")

async def scrape_chat_for_keywords(page):
    """チャット画面からキーワードを探し、最初に見つかった日付を返す。
    - 日付ヘッダー: data-message-id が負値の div 内 p.tw-text-center
    - メッセージ本文: p.text-content（システムイベントの p.tw-text-center は対象外）
    DOMの順序がそのまま時系列なので、上から順に走査する。
    """
    current_date = "日付不明"
    container = page.locator(CHAT_CONTAINER_SELECTOR)

    # 日付ヘッダー（負ID）とメッセージ本文を一括取得し、y座標で時系列ソート
    items = []
    for el in await container.locator(DATE_HEADER_SELECTOR).all():
        box = await el.bounding_box()
        if box:
            items.append(("date", el, box["y"]))
    for el in await container.locator(MESSAGE_CONTENT_SELECTOR).all():
        box = await el.bounding_box()
        if box:
            items.append(("msg", el, box["y"]))

    items.sort(key=lambda x: x[2])

    for kind, el, _ in items:
        if kind == "date":
            current_date = (await el.text_content()).strip()
        else:
            msg_text = await el.text_content()
            if msg_text and any(k in msg_text for k in KEYWORDS):
                return current_date

    return None

async def switch_account(page, account_name, account_id_str):
    """マイページでアカウントIDを検索して切り替える"""
    if not account_id_str:
        print(f"⚠️ アカウントID未登録: '{account_name}' → スキップ")
        return False

    print(f"🔄 アカウント切り替え: {account_name} ({account_id_str})")

    await page.goto(f"{LSTEP_BASE_URL}/account", wait_until="domcontentloaded", timeout=30000)
    await asyncio.sleep(1)

    search_box = page.locator("input[placeholder*='アカウントID']").first
    await search_box.wait_for(state="visible", timeout=10000)
    await search_box.fill(account_id_str)
    await page.locator("text=検索").first.click()

    account_card = page.locator(f"text=@{account_id_str}").first
    try:
        await account_card.wait_for(state="visible", timeout=10000)
    except Exception:
        print(f"⚠️ アカウントが見つかりませんでした: {account_name} ({account_id_str})")
        return False

    open_btn = page.locator("text=メイン画面を開く").first
    await open_btn.click()

    await page.wait_for_function(
        "window.location.pathname !== '/account'",
        timeout=15000
    )
    await page.wait_for_load_state("domcontentloaded")
    await asyncio.sleep(1)
    print(f"✅ 切り替え完了: {account_name}")
    return True


async def run(playwright: Playwright):
    print("🚀 ブラウザを起動しています...")

    try:
        browser = await playwright.chromium.launch(
            headless=False,
            args=["--no-sandbox", "--disable-setuid-sandbox"]
        )
    except Exception as e:
        print(f"❌ ブラウザの起動に失敗しました: {e}")
        return

    context = await browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        viewport={'width': 1280, 'height': 800},
        locale="ja-JP"
    )
    page = await context.new_page()

    csv_data = read_csv(CSV_FILE)
    if not csv_data:
        await browser.close()
        return

    try:
        # --- 1. ログイン処理 ---
        print(f"🚀 ログイン画面へ移動中: {LOGIN_URL}")
        await page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(3)

        await page.wait_for_selector(LOGIN_USERNAME_SELECTOR, timeout=30000)
        print("⌨️ ログイン情報を入力中...")
        await page.fill(LOGIN_USERNAME_SELECTOR, CREDENTIALS["username"])
        await page.fill(LOGIN_PASSWORD_SELECTOR, CREDENTIALS["password"])

        print("=" * 50)
        print("⚠️  reCAPTCHAが検出されました")
        print("ブラウザ画面で「私はロボットではありません」にチェックを入れ、")
        print("ログインボタンを押してください。")
        print("=" * 50)

        print("⏳ ログイン完了を待機しています...")
        await page.wait_for_function(
            "window.location.href.indexOf('login') === -1",
            timeout=180000
        )
        print(f"🔓 ログイン成功")
        await asyncio.sleep(2)

        accounts = load_accounts(ACCOUNTS_FILE)

        # --- 2. CSVの各行をループ処理 ---
        processed_count = 0
        total = sum(1 for i, r in enumerate(csv_data) if i > 0 and len(r) >= 5 and not r[0])
        print(f"📋 処理対象: {total} 件")

        # ログファイル初期化
        with open(LOG_FILE, 'w', encoding='utf-8-sig', newline='') as lf:
            csv.writer(lf).writerow(["行番号", "患者ID", "アカウント名", "結果", "詳細"])

        for i, row in enumerate(csv_data):
            if i == 0: continue
            if TEST_ROWS and i not in TEST_ROWS: continue
            if TEST_START > 0 and not TEST_ROWS and i < TEST_START: continue
            if len(row) < 5 or row[0]: continue

            url_match = re.search(r'https://manager\.linestep\.net/line/visual\?(?:show=detail&)?member=\S+', row[4])
            if not url_match: continue

            patient_id = row[3] if len(row) > 3 else ""
            account_name = extract_account_name(row[4])
            if not account_name:
                print(f"⚠️ アカウント名が見つかりません (行{i}) → スキップ")
                write_log(i, patient_id, "", "スキップ", "アカウント名が見つかりません")
                continue
            account_id_str = find_account_id(accounts, account_name)
            switched = await switch_account(page, account_name, account_id_str)
            if not switched:
                write_log(i, patient_id, account_name, "IDヒットなし", f"JSONにID未登録: {account_name}")
                continue

            target_url = url_match.group().strip().rstrip(')>]"\'')
            processed_count += 1
            print(f"\n🔍 処理中 ({processed_count}/{total}) 行{i}: {target_url}")

            try:
                response = await page.goto(target_url, wait_until="domcontentloaded", timeout=30000)

                if response.status == 404:
                    print(f"⚠️ 404エラー。スキップします。")
                    write_log(i, patient_id, account_name, "404エラー", target_url)
                    continue

                await page.wait_for_selector(CHAT_CONTAINER_SELECTOR, timeout=20000)
                await page.wait_for_function(
                    "!document.body.innerText.includes('友だちを選択してください')",
                    timeout=30000
                )

                # 「友達が見つかりませんでした」ポップアップ検出（アカウント違い）
                await asyncio.sleep(1)
                not_found_popup = page.locator("text=友だちが見つかりませんでした").first
                if await not_found_popup.is_visible():
                    print(f"⚠️ 友だちが見つかりませんでした（アカウント違い）→ スキップ")
                    write_log(i, patient_id, account_name, "アカウント違い", "友だちが見つかりませんでした")
                    continue

                await load_all_chat_history(page)
                found_date = await scrape_chat_for_keywords(page)

                if found_date:
                    csv_data[i][0] = found_date
                    print(f"✨ キーワード発見: {found_date}")
                    write_csv(CSV_FILE, csv_data)
                    write_log(i, patient_id, account_name, "キーワード発見", found_date)
                else:
                    print("🤷 キーワードは見つかりませんでした")
                    write_log(i, patient_id, account_name, "キーワードなし", "")

            except Exception as e:
                print(f"⚠️ 行 {i+1} でエラー: {e}")
                write_log(i, patient_id, account_name, "エラー", str(e))
                continue

            if TEST_LIMIT > 0 and processed_count >= TEST_LIMIT:
                print(f"\n🛑 テスト制限 ({TEST_LIMIT}件) に達したので終了します")
                break

    except Exception as e:
        print(f"❌ エラーが発生しました: {e}")
        await page.screenshot(path=r"C:\Users\弁護士法人響\Desktop\-\Lステ解析\fatal_error.png")
    finally:
        await browser.close()
        print("🏁 すべての工程が終了しました")

async def main():
    async with async_playwright() as p:
        await run(p)

if __name__ == "__main__":
    asyncio.run(main())
