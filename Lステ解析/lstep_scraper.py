import asyncio
import csv
import json
import re
import os
from playwright.async_api import async_playwright, Playwright

# --- 設定項目 ---
LOGIN_URL = "https://manager.linestep.net/account/login"
LSTEP_BASE_URL = "https://manager.linestep.net"

ACCOUNTS_FILE = "/home/loser/projects/-/Lステ解析/アカウント.json"
CSV_FILE = "/home/loser/projects/-/Lステ解析/処理用シート - シート1.csv"

CREDENTIALS = {
    "username": "double_juno",
    "password": "evhiBp4B"
}

KEYWORDS = ["解約", "キャンセル", "クーリングオフ"]

LOGIN_USERNAME_SELECTOR = "input#input_name"
LOGIN_PASSWORD_SELECTOR = "input#input_password"

CHAT_CONTAINER_SELECTOR = ".tw-overflow-y-scroll"
LOAD_MORE_BUTTON_SELECTOR = 'button[data-testid="linyBtn"]'
MESSAGE_BLOCK_SELECTOR = "div[data-message-id]"
MESSAGE_CONTENT_SELECTOR = "p.text-content"
DATE_HEADER_SELECTOR = ".tw-bg-n-verypale p"

# --- 補助関数 ---

def load_accounts(file_path):
    try:
        if not os.path.exists(file_path):
            print(f"❌ アカウントファイルが見つかりません: {file_path}")
            return {}
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return {acc.get('name'): acc.get('id') for acc in data if acc.get('name')}
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
    """チャット画面からキーワードを探し、最初に見つかった日付を返す"""
    current_date = "日付不明"
    elements = await page.locator(f"{DATE_HEADER_SELECTOR}, {MESSAGE_BLOCK_SELECTOR}").all()

    for el in elements:
        text = await el.text_content()
        if "年" in text and "月" in text:
            current_date = text.strip()
            continue

        content_el = el.locator(MESSAGE_CONTENT_SELECTOR)
        if await content_el.count() > 0:
            msg_text = await content_el.text_content()
            if any(k in msg_text for k in KEYWORDS):
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

        for i, row in enumerate(csv_data):
            if i == 0: continue
            if len(row) < 5 or row[0]: continue

            url_match = re.search(r'https://manager\.linestep\.net/line/visual\?show=detail&member=\S+', row[4])
            if not url_match: continue

            account_match = re.search(r'アカウント[：:]\s*(.+)', row[4])
            if not account_match:
                print(f"⚠️ アカウント名が見つかりません (行{i}) → スキップ")
                continue
            account_name = account_match.group(1).strip()
            account_id_str = accounts.get(account_name, "")
            switched = await switch_account(page, account_name, account_id_str)
            if not switched:
                continue

            target_url = url_match.group().strip().rstrip(')>]"\'')
            processed_count += 1
            print(f"\n🔍 処理中 ({processed_count}/{total}) 行{i}: {target_url}")

            try:
                response = await page.goto(target_url, wait_until="domcontentloaded", timeout=30000)

                if response.status == 404:
                    print(f"⚠️ 404エラー。スキップします。")
                    continue

                await page.wait_for_selector(CHAT_CONTAINER_SELECTOR, timeout=20000)
                await page.wait_for_function(
                    "!document.body.innerText.includes('友だちを選択してください')",
                    timeout=30000
                )

                await load_all_chat_history(page)
                found_date = await scrape_chat_for_keywords(page)

                if found_date:
                    csv_data[i][0] = found_date
                    print(f"✨ キーワード発見: {found_date}")
                    write_csv(CSV_FILE, csv_data)
                else:
                    print("🤷 キーワードは見つかりませんでした")

            except Exception as e:
                print(f"⚠️ 行 {i+1} でエラー: {e}")
                continue

    except Exception as e:
        print(f"❌ エラーが発生しました: {e}")
        await page.screenshot(path="/home/loser/projects/-/Lステ解析/fatal_error.png")
    finally:
        await browser.close()
        print("🏁 すべての工程が終了しました")

async def main():
    async with async_playwright() as p:
        await run(p)

if __name__ == "__main__":
    asyncio.run(main())
