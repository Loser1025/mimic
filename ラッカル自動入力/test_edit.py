"""
編集モーダルを実際に開いて金額を読み取るテスト
"""
import asyncio
import re
from playwright.async_api import async_playwright

URL = "https://rakkar.pro/clinic/180/patient/843008/treatment-menu/view"
RAKKAR_EMAIL    = "erusute@and-mg.com"
RAKKAR_PASSWORD = "Erusute1234$"


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()

        print(f"アクセス中: {URL}")
        await page.goto(URL, wait_until="networkidle", timeout=20000)

        if any(kw in page.url for kw in ["login", "sign_in", "sign-in"]):
            print("ログイン中...")
            await page.fill('input[type="email"], input[name="email"]', RAKKAR_EMAIL)
            await page.fill('input[type="password"]', RAKKAR_PASSWORD)
            await page.click('button[type="submit"], input[type="submit"]')
            await page.wait_for_load_state("networkidle", timeout=15000)
            await page.goto(URL, wait_until="networkidle", timeout=20000)

        await page.wait_for_selector("section.MenuInformation", timeout=10000)
        sections = await page.query_selector_all("section.MenuInformation")
        print(f"\n契約メニュー数: {len(sections)} 件\n")

        # セクション1だけテスト
        section = sections[0]
        contract_name = await section.evaluate(
            "el => el.querySelector('.MenuInformation__title button')?.textContent?.trim() ?? ''"
        )
        edit_btn = await section.query_selector('a[href*="treatment-menu/edit"]')
        edit_href = await section.evaluate(
            "el => el.querySelector('a[href*=\"treatment-menu/edit\"]')?.getAttribute('href') ?? ''"
        )
        print(f"=== {contract_name} ===")
        print(f"  編集URL: {edit_href}")

        await edit_btn.click()
        print("  モーダルを開きました。iframeを待機中...")

        # iframeが出るまで待つ
        await page.wait_for_selector(".modal-body iframe", timeout=10000)

        # iframe要素を取得してcontentFrameを開く
        iframe_el = await page.query_selector(".modal-body iframe")
        frame = await iframe_el.content_frame()
        print(f"  iframe取得完了: {frame.url}")

        # iframe内のフォームが読み込まれるまで待つ
        print("  iframe内フォーム読み込み待機中...")
        try:
            await frame.wait_for_selector("input", timeout=10000)
        except Exception:
            pass
        await frame.wait_for_timeout(3000)  # JSの値セットを待つ

        # iframe内の全inputを読み取る
        data = await frame.evaluate("""() => {
            const allInputs = Array.from(document.querySelectorAll('input, textarea, select'))
                .filter(el => el.value && el.value.trim() !== '' && el.value !== '0')
                .map(el => ({
                    name: el.name || '',
                    cls: el.className || '',
                    value: el.value.trim(),
                    type: el.type || ''
                }));

            const originalPrices = Array.from(document.querySelectorAll('.original-price'))
                .map(el => el.value);
            const contractPrices = Array.from(document.querySelectorAll('.contract-price'))
                .map(el => el.value);

            // テキスト表示で金額が見える箇所
            const allText = document.body.innerText.substring(0, 3000);

            return { allInputs, originalPrices, contractPrices, allText };
        }""")

        print(f"\n  定価: {data['originalPrices']}")
        print(f"  契約金額: {data['contractPrices']}")
        print(f"\n  全input値:")
        for inp in data['allInputs'][:40]:
            print(f"    name={inp['name']} cls={inp['cls'][:40]} val={inp['value']}")
        print(f"\n  ページテキスト:\n{data['allText'][:1000]}")

        await browser.close()
        input("\nEnterキーで終了...")


asyncio.run(main())
