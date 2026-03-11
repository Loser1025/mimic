"""
CSVのラッカルURLを全件処理して損害金を計算するスクリプト（V列対応版）

使い方: python rakkar_csv_v.py <入力CSVパス>

計算方法:
  契約内に複数施術がある場合 → 定価の比率で契約金額を按分
  残り損害金 = 按分後の施術単価 × 残り回数
"""
import asyncio
import csv
import re
import sys
import time
from pathlib import Path
from playwright.async_api import async_playwright

# ── 設定 ─────────────────────────────────────────────────────────────
RAKKAR_EMAIL    = "erusute@and-mg.com"
RAKKAR_PASSWORD = "Erusute1234$"

URL_COL  = 21   # V列（0始まり）
NAME_COL = 3    # D列
DELAY_SEC = 0.5
# ─────────────────────────────────────────────────────────────────────


def rakkar_to_treatment_url(url: str) -> str | None:
    m = re.match(r"(https://rakkar\.pro/clinic/\d+/patient/\d+)", url)
    return m.group(1) + "/treatment-menu/view" if m else None


async def auto_login(page, email: str, password: str) -> bool:
    try:
        await page.fill('input[type="email"], input[name="email"], input[name="user[email]"]', email)
        await page.fill('input[type="password"]', password)
        await page.click('button[type="submit"], input[type="submit"]')
        await page.wait_for_load_state("networkidle", timeout=15000)
        return True
    except Exception as e:
        print(f"  [自動ログイン失敗] {e}")
        return False


async def get_item_prices_from_edit(page, section) -> list[dict]:
    """
    編集iframeを開いて各施術の (menu_name, original_price) を取得する。
    取得できなければ空リストを返す。
    """
    edit_btn = await section.query_selector('a[href*="treatment-menu/edit"]')
    if not edit_btn:
        return []

    try:
        await edit_btn.click()
        await page.wait_for_selector(".modal-body iframe", timeout=8000)
        iframe_el = await page.query_selector(".modal-body iframe")
        frame = await iframe_el.content_frame()

        # menu-name が現れるまで待つ
        try:
            await frame.wait_for_selector(".menu-name", timeout=8000)
        except Exception:
            await frame.wait_for_timeout(2000)

        items = await frame.evaluate("""() => {
            const names  = Array.from(document.querySelectorAll('.menu-name'))
                               .map(el => el.value.trim());
            const prices = Array.from(document.querySelectorAll('.original-price'))
                               .map(el => parseInt(el.value.replace(/,/g, '')) || 0);
            const result = [];
            for (let i = 0; i < names.length; i++) {
                result.push({ name: names[i] || '', original_price: prices[i] || 0 });
            }
            return result;
        }""")
    except Exception:
        items = []
    finally:
        # モーダルを閉じる
        try:
            close_btn = await page.query_selector('.modal.show .btn-outline-secondary, .modal[style*="block"] .btn-outline-secondary')
            if close_btn:
                await close_btn.click()
                await page.wait_for_timeout(300)
        except Exception:
            pass

    return items


async def scrape_menus(page, url: str) -> list[dict]:
    """treatment-menu/view から全契約の残り損害金を計算して返す"""
    try:
        await page.goto(url, wait_until="networkidle", timeout=20000)
    except Exception:
        await page.wait_for_timeout(3000)

    if any(kw in page.url for kw in ["login", "sign_in", "sign-in"]):
        print("  → ログイン中...", end=" ", flush=True)
        ok = await auto_login(page, RAKKAR_EMAIL, RAKKAR_PASSWORD)
        if ok:
            print("完了")
            try:
                await page.goto(url, wait_until="networkidle", timeout=20000)
            except Exception:
                await page.wait_for_timeout(3000)
        else:
            return []

    try:
        await page.wait_for_selector("section.MenuInformation", timeout=10000)
    except Exception:
        return []

    sections = await page.query_selector_all("section.MenuInformation")
    results = []

    for section in sections:
        # ── 契約名 ──
        contract_name = await section.evaluate(
            "el => el.querySelector('.MenuInformation__title button')?.textContent?.trim() ?? ''"
        )

        # ── 契約金額合計（DataListから） ──
        amount_text = await section.evaluate("""
            el => {
                for (const dt of el.querySelectorAll('dt')) {
                    if (dt.textContent.includes('契約金額')) {
                        return dt.nextElementSibling?.textContent?.trim() ?? '';
                    }
                }
                return '';
            }
        """)
        contract_amount = 0
        clean = re.sub(r"[¥,\s]", "", amount_text)
        if clean.isdigit():
            contract_amount = int(clean)

        # ── 各施術の回数情報（TreatmentMenuManagement × N個） ──
        mgmt_list = await section.evaluate("""
            el => Array.from(el.querySelectorAll('.TreatmentMenuManagement__title')).map(h3 => h3.textContent.trim())
        """)

        management_items = []
        for mgmt_text in mgmt_list:
            remaining_m = re.search(r"残り回数(\d+)回", mgmt_text)
            remaining = int(remaining_m.group(1)) if remaining_m else 0
            clean_text = re.sub(r"残り回数\d+回", "", mgmt_text)
            total_m = re.search(r"(\d+)回", clean_text)
            total = int(total_m.group(1)) if total_m else 0
            base_name = re.sub(r"\s*\d+回.*", "", clean_text).strip()
            management_items.append({"base_name": base_name, "total": total, "remaining": remaining})

        # ── 編集iframeから各施術の定価を取得 ──
        edit_items = await get_item_prices_from_edit(page, section)

        # ── 施術ごとの残り損害金を計算 ──
        item_results = []

        if edit_items and management_items:
            total_original = sum(it["original_price"] for it in edit_items)

            for idx, mgmt in enumerate(management_items):
                if idx < len(edit_items):
                    orig = edit_items[idx]["original_price"]
                    item_contract = int(contract_amount * orig / total_original) if total_original > 0 else 0
                else:
                    item_contract = 0

                total_s = mgmt["total"]
                remaining_s = mgmt["remaining"]
                remaining_amount = int(item_contract / total_s * remaining_s) if total_s > 0 else 0
                item_results.append({
                    "name": mgmt["base_name"],
                    "item_contract": item_contract,
                    "total": total_s,
                    "remaining": remaining_s,
                    "remaining_amount": remaining_amount,
                })

        elif management_items:
            per_item = contract_amount // len(management_items) if management_items else 0
            for mgmt in management_items:
                total_s = mgmt["total"]
                remaining_s = mgmt["remaining"]
                remaining_amount = int(per_item / total_s * remaining_s) if total_s > 0 else 0
                item_results.append({
                    "name": mgmt["base_name"],
                    "item_contract": per_item,
                    "total": total_s,
                    "remaining": remaining_s,
                    "remaining_amount": remaining_amount,
                })

        contract_remaining = sum(it["remaining_amount"] for it in item_results)
        results.append({
            "contract_name": contract_name,
            "contract_amount": contract_amount,
            "contract_remaining": contract_remaining,
            "items": item_results,
        })

    return results


async def main(csv_in: str):
    csv_out = str(Path(csv_in).parent / (Path(csv_in).stem + "_損害金計算結果.csv"))

    print(f"入力: {csv_in}")
    print(f"出力: {csv_out}\n")

    with open(csv_in, encoding="utf-8", errors="replace") as f:
        rows = list(csv.reader(f))

    targets = []
    for i, row in enumerate(rows[1:], start=2):
        url  = row[URL_COL].strip()  if len(row) > URL_COL  else ""
        name = row[NAME_COL].strip() if len(row) > NAME_COL else ""
        if url.startswith("http"):
            targets.append((i, name, url))

    print(f"処理対象: {len(targets)} 件\n")

    if not targets:
        print("URLが見つかりません。V列（22列目）にURLが入っているか確認してください。")
        input("\nEnterキーで終了...")
        return

    results = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()

        # ログイン確立
        first_url = rakkar_to_treatment_url(targets[0][2])
        if first_url:
            try:
                await page.goto(first_url, wait_until="networkidle", timeout=20000)
            except Exception:
                await page.wait_for_timeout(3000)
            if any(kw in page.url for kw in ["login", "sign_in", "sign-in"]):
                print("ログイン中...", end=" ", flush=True)
                await auto_login(page, RAKKAR_EMAIL, RAKKAR_PASSWORD)
                print("完了\n")

        for idx, (row_num, name, rakkar_url) in enumerate(targets, 1):
            treatment_url = rakkar_to_treatment_url(rakkar_url)
            if not treatment_url:
                print(f"[{idx}/{len(targets)}] {name} → URLパース失敗")
                results.append({"row": row_num, "name": name, "url": rakkar_url,
                                 "total_remaining": "", "detail": "URLパース失敗"})
                continue

            print(f"[{idx}/{len(targets)}] {name}", end=" ", flush=True)

            try:
                contracts = await scrape_menus(page, treatment_url)
            except Exception as e:
                print(f"→ エラー: {e}")
                results.append({"row": row_num, "name": name, "url": rakkar_url,
                                 "total_remaining": "", "detail": f"エラー: {e}"})
                continue

            if not contracts:
                print("→ 契約メニューなし")
                results.append({"row": row_num, "name": name, "url": rakkar_url,
                                 "total_remaining": 0, "detail": "契約メニューなし"})
                continue

            total_remaining = sum(c["contract_remaining"] for c in contracts)

            detail_parts = []
            for c in contracts:
                item_strs = [
                    f"{it['name']} {it['total']}回中{it['remaining']}回残→¥{it['remaining_amount']:,}"
                    for it in c["items"]
                ]
                detail_parts.append(
                    f"[{c['contract_name']} ¥{c['contract_amount']:,}] " + " / ".join(item_strs)
                )
            detail = " | ".join(detail_parts)

            print(f"→ ¥{total_remaining:,}")
            for c in contracts:
                for it in c["items"]:
                    print(f"    {it['name']} {it['total']}回中{it['remaining']}回残 ¥{it['item_contract']:,}→¥{it['remaining_amount']:,}")

            results.append({
                "row": row_num,
                "name": name,
                "url": rakkar_url,
                "total_remaining": total_remaining,
                "detail": detail,
            })

            time.sleep(DELAY_SEC)

        await browser.close()

    with open(csv_out, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["row", "name", "url", "total_remaining", "detail"])
        writer.writeheader()
        writer.writerows(results)

    print(f"\n結果を保存しました: {csv_out}")
    print(f"合計 {len(results)} 件処理")
    input("\nEnterキーで終了...")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("使い方: python rakkar_csv_v.py <入力CSVパス>")
        input("\nEnterキーで終了...")
        sys.exit(1)
    asyncio.run(main(sys.argv[1]))
