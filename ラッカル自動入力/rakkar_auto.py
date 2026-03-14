"""
ラッカルURL自動入力スクリプト

処理内容:
  1. ATOMスプレッドシートの「★新★Lステ連携」シートを読む
  2. 名前あり・ラッカルURL空の行を抽出
  3. maestro.and-mg.com で名前検索 → rakkar.pro のURLを取得
  4. シートの「ラッカル」列に書き込む

実行前に一度だけ「セットアップ.bat」を実行してください。
"""

import asyncio
import re
import sys
import time

import gspread
from playwright.async_api import async_playwright

# ── 設定 ──────────────────────────────────────────────
SPREADSHEET_ID = "12fjFyhZ9vkYV_-KDMHH4O3mBRN8e6HZ9FXBLMREVSkQ"
SHEET_NAME = "★新★Lステ連携"
MAESTRO_SEARCH_URL = "https://maestro.and-mg.com/patients"
RESULT_SUFFIX = "/contact-history/view"
# 行の先頭何行がヘッダーか（0始まり、3行目まで = インデックス0〜2）
HEADER_ROWS = 3
# 検索ごとの待機秒数（負荷をかけすぎないため）
DELAY_SEC = 0.8
# ──────────────────────────────────────────────────────


def find_col(header_rows: list[list], keywords: list[str]) -> int | None:
    """ヘッダー複数行からキーワードにマッチする列インデックスを返す（最初にマッチした列）"""
    for row in header_rows:
        for i, cell in enumerate(row):
            if any(kw in str(cell) for kw in keywords):
                return i
    return None


def clean_name(name: str) -> str:
    """名前から検索用に不要な注釈を除去"""
    # ※キャンセル, ※退会 などを除去
    name = re.sub(r"[※＊\*].*", "", name)
    # 全角スペース・半角スペースを除去して1つの文字列に
    return name.replace(" ", "").replace("　", "").strip()


async def search_rakkar_url(page, name: str) -> str | None:
    """maestroで名前検索してrakkar.pro の完全URLを返す（見つからなければNone）"""
    clean = clean_name(name)
    if not clean:
        return None

    search_url = f"{MAESTRO_SEARCH_URL}?name={clean}"
    try:
        await page.goto(search_url, wait_until="networkidle", timeout=15000)
    except Exception:
        await page.wait_for_timeout(3000)

    # rakkar.pro へのリンクを探す
    links = await page.query_selector_all("a[href*='rakkar.pro']")
    for link in links:
        href = await link.get_attribute("href")
        if not href:
            continue
        # clinic_id / patient_id を正規表現で抽出
        m = re.search(r"https://rakkar\.pro/clinic/(\d+)/patient/(\d+)", href)
        if m:
            base = f"https://rakkar.pro/clinic/{m.group(1)}/patient/{m.group(2)}"
            return base + RESULT_SUFFIX

    return None


async def main():
    # ── Google Sheets 接続 ──────────────────────────────
    print("Google Sheetsに接続中...")
    try:
        gc = gspread.oauth(
            credentials_filename="credentials.json",
            authorized_user_filename="token.json",
        )
    except Exception as e:
        print(f"\n[ERROR] Google認証失敗: {e}")
        print("credentials.json が正しく配置されているか確認してください。")
        input("\nEnterキーで終了...")
        sys.exit(1)

    try:
        sh = gc.open_by_key(SPREADSHEET_ID)
        ws = sh.worksheet(SHEET_NAME)
    except Exception as e:
        print(f"\n[ERROR] シート取得失敗: {e}")
        input("\nEnterキーで終了...")
        sys.exit(1)

    print("シートデータ取得中...")
    data = ws.get_all_values()

    if len(data) <= HEADER_ROWS:
        print("データ行が見つかりません。")
        input("\nEnterキーで終了...")
        return

    # ── 列インデックス検出 ─────────────────────────────
    headers = data[:HEADER_ROWS]
    name_col = find_col(headers, ["名前", "顧客名"])
    rakkar_col = find_col(headers, ["ラッカル", "rakkar", "RaKKaR", "RAKKAR"])

    if name_col is None:
        print("[ERROR] 名前列が見つかりません。ヘッダーを確認してください。")
        input("\nEnterキーで終了...")
        sys.exit(1)
    if rakkar_col is None:
        print("[ERROR] ラッカル列が見つかりません。ヘッダーを確認してください。")
        input("\nEnterキーで終了...")
        sys.exit(1)

    print(f"  名前列: {name_col + 1}列目 ({chr(64 + name_col + 1)}列)")
    print(f"  ラッカル列: {rakkar_col + 1}列目 ({chr(64 + rakkar_col + 1)}列)")

    # ── 処理対象行の抽出（名前あり・ラッカルURL空） ─────
    targets = []
    for i, row in enumerate(data[HEADER_ROWS:], start=HEADER_ROWS + 1):
        name = row[name_col].strip() if len(row) > name_col else ""
        rakkar = row[rakkar_col].strip() if len(row) > rakkar_col else ""
        if name and not rakkar:
            targets.append((i, name))

    if not targets:
        print("\nラッカルURL空の行がありません。処理完了。")
        input("\nEnterキーで終了...")
        return

    print(f"\n処理対象: {len(targets)} 件\n")

    # ── Playwright でMaestro検索 ──────────────────────
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()

        ok = 0
        ng = 0
        for row_idx, name in targets:
            print(f"[{ok + ng + 1}/{len(targets)}] {name} (行{row_idx}) を検索中...", end=" ", flush=True)
            try:
                url = await search_rakkar_url(page, name)
                if url:
                    ws.update_cell(row_idx, rakkar_col + 1, url)
                    print(f"→ {url}")
                    ok += 1
                else:
                    print("→ 見つからず（スキップ）")
                    ng += 1
            except Exception as e:
                print(f"→ エラー: {e}")
                ng += 1

            time.sleep(DELAY_SEC)

        await browser.close()

    print(f"\n完了！  成功: {ok}件  スキップ: {ng}件")
    input("\nEnterキーで終了...")


if __name__ == "__main__":
    asyncio.run(main())
