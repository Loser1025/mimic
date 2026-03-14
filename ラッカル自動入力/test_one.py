"""
1件だけ損害金を計算して表示するテスト用スクリプト
Google Sheets不要・シートへの書き込みなし
"""
import asyncio
import re
import sys
from playwright.async_api import async_playwright

URL = "https://rakkar.pro/clinic/139/patient/830972/treatment-menu/view"


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()

        print(f"アクセス中: {URL}")
        try:
            await page.goto(URL, wait_until="networkidle", timeout=20000)
        except Exception:
            await page.wait_for_timeout(4000)

        # ログインが必要な場合は手動でログインしてもらう
        current = page.url
        if "login" in current or "sign" in current or URL not in page.url:
            print("\nログインが必要です。ブラウザでログインしてください。")
            print("ログイン完了後、Enterキーを押してください...")
            input()
            await page.goto(URL, wait_until="networkidle", timeout=20000)

        # 治療メニューのセクションが出るまで最大10秒待つ
        try:
            await page.wait_for_selector("section.MenuInformation", timeout=10000)
        except Exception:
            print("[DEBUG] section.MenuInformation が見つかりません")
            print(f"[DEBUG] 現在のURL: {page.url}")
            # ページのHTMLの一部を表示してデバッグ
            body = await page.inner_text("body")
            print(f"[DEBUG] ページテキスト(先頭500文字):\n{body[:500]}")
            input("\nEnterキーで終了...")
            await browser.close()
            return

        sections = await page.query_selector_all("section.MenuInformation")
        print(f"\n契約メニュー数: {len(sections)} 件\n")

        total_remaining = 0

        for i, section in enumerate(sections, 1):
            status = await section.evaluate(
                "el => el.querySelector('.MenuInformation__status .badge')?.textContent?.trim() ?? ''"
            )
            name = await section.evaluate(
                "el => el.querySelector('.MenuInformation__title button')?.textContent?.trim() ?? ''"
            )
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
            mgmt_text = await section.evaluate(
                "el => el.querySelector('.TreatmentMenuManagement__title')?.textContent?.trim() ?? ''"
            )

            # 金額パース
            contract_amount = 0
            clean = re.sub(r"[¥,\s]", "", amount_text)
            if clean.isdigit():
                contract_amount = int(clean)

            # 回数パース
            remaining_m = re.search(r"残り回数(\d+)回", mgmt_text)
            remaining = int(remaining_m.group(1)) if remaining_m else 0

            mgmt_no_remaining = re.sub(r"残り回数\d+回", "", mgmt_text)
            total_m = re.search(r"(\d+)回", mgmt_no_remaining)
            total = int(total_m.group(1)) if total_m else 0

            # 計算
            if total > 0 and contract_amount > 0:
                remaining_amount = int(contract_amount / total * remaining)
            else:
                remaining_amount = 0

            skip = "解約" in status and "契約" not in status

            print(f"--- メニュー {i} ---")
            print(f"  施術名:     {name}")
            print(f"  ステータス: {status}{'  ← スキップ' if skip else ''}")
            print(f"  契約金額:   ¥{contract_amount:,}  ({amount_text})")
            print(f"  総回数:     {total}回")
            print(f"  残り回数:   {remaining}回")
            print(f"  残り損害金: ¥{remaining_amount:,}")
            print(f"  (元テキスト: {mgmt_text[:60]})")
            print()

            if not skip:
                total_remaining += remaining_amount

        print(f"{'='*40}")
        print(f"  合計 残り損害金: ¥{total_remaining:,}")
        print(f"{'='*40}")

        await browser.close()
        input("\nEnterキーで終了...")


asyncio.run(main())
