import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        # ブラウザを起動（ユーザーが操作できるよう headless=False）
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()
        
        print("🚀 ブラウザを起動しました。")
        await page.goto("https://manager.linestep.net/")
        
        print("\n--------------------------------------------------")
        print("⏳ 【操作依頼】ブラウザでログイン操作（CAPTCHA解決）を完了させてください。")
        print("ログインが完了し、メイン画面が表示された状態で待機してください。")
        print("60秒後に現在のURLとページソースを自動的に保存します...")
        print("--------------------------------------------------\n")
        
        # ユーザーがログインを完了させるための十分な待機時間を設ける
        await asyncio.sleep(60)
        
        # 現在のURLとページソースを取得
        current_url = page.url
        content = await page.content()
        
        # ファイルに保存
        with open("current_url.txt", "w", encoding="utf-8") as f:
            f.write(current_url)
        with open("page_source.html", "w", encoding="utf-8") as f:
            f.write(content)
            
        print(f"\n✅ 保存完了しました。")
        print(f"保存されたURL: {current_url}")
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
