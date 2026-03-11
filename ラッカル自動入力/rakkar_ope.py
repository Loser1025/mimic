"""
CSVのラッカルURLを全件処理してオペ消化金額合計を計算するスクリプト

使い方:
  python rakkar_ope.py <入力CSVパス> <URL列番号>
  例) python rakkar_ope.py "C:/Users/.../抽出.csv" 22   # W列
  例) python rakkar_ope.py "C:/Users/.../抽出.csv" 21   # V列
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

NAME_COL  = 3    # D列
DELAY_SEC = 0.5
# ─────────────────────────────────────────────────────────────────────


def rakkar_to_record_url(url: str) -> str | None:
    m = re.match(r"(https://rakkar\.pro/clinic/\d+/patient/\d+)", url)
    return m.group(1) + "/treatment-record/view" if m else None


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


async def scrape_ope_total(page, url: str) -> tuple[int, list[int]]:
    """
    treatment-record/view から全施術のオペ消化金額を取得して合計を返す。
    戻り値: (合計金額, [各施術の金額リスト])
    """
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
            return 0, []

    # ページ読み込み待機（カルテがない場合もある）
    await page.wait_for_timeout(2000)

    amounts = await page.evaluate("""() => {
        const results = [];
        for (const dt of document.querySelectorAll('dt')) {
            if (dt.textContent.trim() === 'オペ消化金額') {
                const dd = dt.nextElementSibling;
                if (dd) {
                    const text = dd.textContent.trim();
                    // "20,502円" → 20502
                    const num = parseInt(text.replace(/[^0-9]/g, ''), 10);
                    if (!isNaN(num) && num > 0) {
                        results.push(num);
                    }
                }
            }
        }
        return results;
    }""")

    total = sum(amounts)
    return total, amounts


async def main(csv_in: str, url_col: int):
    csv_out = str(Path(csv_in).parent / (Path(csv_in).stem + "_オペ消化計算結果.csv"))

    print(f"入力: {csv_in}")
    print(f"URL列: {url_col + 1}列目（0始まり: {url_col}）")
    print(f"出力: {csv_out}\n")

    with open(csv_in, encoding="utf-8", errors="replace") as f:
        rows = list(csv.reader(f))

    targets = []
    for i, row in enumerate(rows[1:], start=2):
        url  = row[url_col].strip()  if len(row) > url_col  else ""
        name = row[NAME_COL].strip() if len(row) > NAME_COL else ""
        if url.startswith("http"):
            targets.append((i, name, url))

    print(f"処理対象: {len(targets)} 件\n")

    if not targets:
        print("URLが見つかりません。列番号が正しいか確認してください。")
        input("\nEnterキーで終了...")
        return

    results = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()

        # ログイン確立
        first_record_url = rakkar_to_record_url(targets[0][2])
        if first_record_url:
            try:
                await page.goto(first_record_url, wait_until="networkidle", timeout=20000)
            except Exception:
                await page.wait_for_timeout(3000)
            if any(kw in page.url for kw in ["login", "sign_in", "sign-in"]):
                print("ログイン中...", end=" ", flush=True)
                await auto_login(page, RAKKAR_EMAIL, RAKKAR_PASSWORD)
                print("完了\n")

        for idx, (row_num, name, rakkar_url) in enumerate(targets, 1):
            record_url = rakkar_to_record_url(rakkar_url)
            if not record_url:
                print(f"[{idx}/{len(targets)}] {name} → URLパース失敗")
                results.append({"row": row_num, "name": name, "url": rakkar_url,
                                 "ope_total": "", "detail": "URLパース失敗"})
                continue

            print(f"[{idx}/{len(targets)}] {name}", end=" ", flush=True)

            try:
                total, amounts = await scrape_ope_total(page, record_url)
            except Exception as e:
                print(f"→ エラー: {e}")
                results.append({"row": row_num, "name": name, "url": rakkar_url,
                                 "ope_total": "", "detail": f"エラー: {e}"})
                continue

            if not amounts:
                print("→ オペ消化金額なし")
                results.append({"row": row_num, "name": name, "url": rakkar_url,
                                 "ope_total": 0, "detail": "オペ消化金額なし"})
                continue

            detail = " + ".join(f"¥{a:,}" for a in amounts) + f" = ¥{total:,}"
            print(f"→ ¥{total:,}（{len(amounts)}件）")

            results.append({
                "row": row_num,
                "name": name,
                "url": rakkar_url,
                "ope_total": total,
                "detail": detail,
            })

            time.sleep(DELAY_SEC)

        await browser.close()

    with open(csv_out, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["row", "name", "url", "ope_total", "detail"])
        writer.writeheader()
        writer.writerows(results)

    print(f"\n結果を保存しました: {csv_out}")
    print(f"合計 {len(results)} 件処理")
    input("\nEnterキーで終了...")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("使い方: python rakkar_ope.py <入力CSVパス> <URL列番号(0始まり)>")
        print("  W列(23列目) → 22")
        print("  V列(22列目) → 21")
        input("\nEnterキーで終了...")
        sys.exit(1)
    asyncio.run(main(sys.argv[1], int(sys.argv[2])))
