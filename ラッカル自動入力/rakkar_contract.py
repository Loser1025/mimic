"""
ラッカル 残り損害金 自動計算スクリプト

処理内容:
  1. ATOMスプレッドシートの「★新★Lステ連携」シートを読む
  2. ラッカルURL あり・損害金見込み空 の行を対象
  3. treatment-menu/view を開いて契約情報をスクレイピング
  4. 残り損害金 = 契約金額 ÷ 総回数 × 残り回数 を計算
  5. 「損害金見込み」列に書き込む

実行: 「実行_損害金計算.bat」をダブルクリック
"""

import asyncio
import re
import sys
import time

import gspread
from playwright.async_api import async_playwright

# ── 設定 ─────────────────────────────────────────────────────────────
SPREADSHEET_ID = "12fjFyhZ9vkYV_-KDMHH4O3mBRN8e6HZ9FXBLMREVSkQ"
SHEET_NAME = "★新★Lステ連携"
HEADER_ROWS = 3
DELAY_SEC = 1.0
# ─────────────────────────────────────────────────────────────────────


def find_col(header_rows: list, keywords: list) -> int | None:
    for row in header_rows:
        for i, cell in enumerate(row):
            if any(kw in str(cell) for kw in keywords):
                return i
    return None


def rakkar_to_treatment_url(rakkar_url: str) -> str | None:
    """ラッカルURL → treatment-menu/view URL に変換"""
    m = re.match(r"(https://rakkar\.pro/clinic/\d+/patient/\d+)", rakkar_url)
    if m:
        return m.group(1) + "/treatment-menu/view"
    return None


async def scrape_treatment_menus(page, url: str) -> list[dict]:
    """treatment-menu/view から全契約メニューの情報を取得"""
    try:
        await page.goto(url, wait_until="networkidle", timeout=20000)
    except Exception:
        await page.wait_for_timeout(4000)

    sections = await page.query_selector_all("section.MenuInformation")
    results = []

    for section in sections:
        status = await section.evaluate(
            "el => el.querySelector('.MenuInformation__status .badge')?.textContent?.trim() ?? ''"
        )

        # 施術名
        name = await section.evaluate(
            "el => el.querySelector('.MenuInformation__title button')?.textContent?.trim() ?? ''"
        )

        # 契約金額（税込）
        amount_text = await section.evaluate("""
            el => {
                const dts = el.querySelectorAll('dt');
                for (const dt of dts) {
                    if (dt.textContent.includes('契約金額')) {
                        return dt.nextElementSibling?.textContent?.trim() ?? '';
                    }
                }
                return '';
            }
        """)
        contract_amount = 0
        clean_amount = re.sub(r"[¥,\s]", "", amount_text)
        if clean_amount.isdigit():
            contract_amount = int(clean_amount)

        # 総回数・残り回数（.TreatmentMenuManagement__title のテキストから取得）
        mgmt_text = await section.evaluate(
            "el => el.querySelector('.TreatmentMenuManagement__title')?.textContent?.trim() ?? ''"
        )
        total_sessions = 0
        remaining_sessions = 0

        # 「残り回数X回」を先に取得（これが残り）
        remaining_m = re.search(r"残り回数(\d+)回", mgmt_text)
        if remaining_m:
            remaining_sessions = int(remaining_m.group(1))

        # 「X回（残り...」の X が総回数
        # 例: "基本包茎術 3回（残り回数2回）" → 3
        # ただし「残り回数」の前にある最初の「X回」を使う
        mgmt_no_remaining = re.sub(r"残り回数\d+回", "", mgmt_text)
        total_m = re.search(r"(\d+)回", mgmt_no_remaining)
        if total_m:
            total_sessions = int(total_m.group(1))

        # 残り損害金を計算
        if total_sessions > 0 and contract_amount > 0:
            per_session = contract_amount / total_sessions
            remaining_amount = int(per_session * remaining_sessions)
        else:
            remaining_amount = 0

        results.append({
            "name": name,
            "contract_amount": contract_amount,
            "total_sessions": total_sessions,
            "remaining_sessions": remaining_sessions,
            "remaining_amount": remaining_amount,
            "status": status,
        })

    return results


async def main():
    print("Google Sheetsに接続中...")
    try:
        gc = gspread.oauth(
            credentials_filename="credentials.json",
            authorized_user_filename="token.json",
        )
    except Exception as e:
        print(f"\n[ERROR] Google認証失敗: {e}")
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

    headers = data[:HEADER_ROWS]
    name_col     = find_col(headers, ["名前", "顧客名"])
    rakkar_col   = find_col(headers, ["ラッカル", "rakkar", "RaKKaR", "RAKKAR"])
    refund_col   = find_col(headers, ["損害金見込み", "損害金"])

    missing = []
    if name_col   is None: missing.append("名前")
    if rakkar_col is None: missing.append("ラッカル")
    if refund_col is None: missing.append("損害金見込み")
    if missing:
        print(f"[ERROR] 列が見つかりません: {', '.join(missing)}")
        input("\nEnterキーで終了...")
        sys.exit(1)

    print(f"  名前列:      {name_col + 1}列目")
    print(f"  ラッカル列:  {rakkar_col + 1}列目")
    print(f"  損害金列:    {refund_col + 1}列目")

    # 対象行：ラッカルURLあり・損害金見込み空
    targets = []
    for i, row in enumerate(data[HEADER_ROWS:], start=HEADER_ROWS + 1):
        name    = row[name_col].strip()    if len(row) > name_col    else ""
        rakkar  = row[rakkar_col].strip()  if len(row) > rakkar_col  else ""
        refund  = row[refund_col].strip()  if len(row) > refund_col  else ""
        if rakkar and not refund:
            targets.append((i, name, rakkar))

    if not targets:
        print("\n処理対象なし（ラッカルURLあり・損害金見込み空の行がありません）")
        input("\nEnterキーで終了...")
        return

    print(f"\n処理対象: {len(targets)} 件\n")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()

        ok = 0
        ng = 0
        for row_idx, name, rakkar_url in targets:
            treatment_url = rakkar_to_treatment_url(rakkar_url)
            if not treatment_url:
                print(f"[{ok+ng+1}/{len(targets)}] {name} → URLパース失敗: {rakkar_url}")
                ng += 1
                continue

            print(f"[{ok+ng+1}/{len(targets)}] {name} (行{row_idx})", end=" ", flush=True)

            try:
                menus = await scrape_treatment_menus(page, treatment_url)
            except Exception as e:
                print(f"→ エラー: {e}")
                ng += 1
                continue

            if not menus:
                print("→ 契約メニューなし（スキップ）")
                ng += 1
                continue

            # 全メニューの残り損害金を合計
            total_remaining = sum(m["remaining_amount"] for m in menus)

            # 内訳を表示
            for m in menus:
                print(
                    f"\n    [{m['status']}] {m['name']} "
                    f"契約¥{m['contract_amount']:,} "
                    f"{m['total_sessions']}回中{m['remaining_sessions']}回残 "
                    f"→ ¥{m['remaining_amount']:,}"
                )
            print(f"    合計残り損害金: ¥{total_remaining:,}")

            ws.update_cell(row_idx, refund_col + 1, total_remaining)
            ok += 1

            time.sleep(DELAY_SEC)

        await browser.close()

    print(f"\n完了！  成功: {ok}件  スキップ/エラー: {ng}件")
    input("\nEnterキーで終了...")


if __name__ == "__main__":
    asyncio.run(main())
