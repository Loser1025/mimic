import re
from playwright.sync_api import Playwright, sync_playwright, expect


def run(playwright: Playwright) -> None:
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context()
    page = context.new_page()
    page.goto("https://manager.linestep.net/account/login")
    page.get_by_role("textbox", name="ユーザーID").click()
    page.get_by_role("textbox", name="ユーザーID").fill("kogawa_flka")
    page.get_by_role("textbox", name="パスワード").click()
    page.get_by_role("textbox", name="パスワード").click()
    page.get_by_role("textbox", name="パスワード").fill("kogawa0930")
    page.locator("iframe[name=\"a-ypcxwj89bg3n\"]").content_frame.get_by_role("checkbox", name="私はロボットではありません").click()
    page.get_by_role("button", name="ログイン").click()
    page.get_by_role("link", name="クロス分析").click()
    page.goto("https://manager.linestep.net/line/board")
    page.get_by_role("link", name="反響数？").click()
    page.get_by_role("textbox", name="日付選択(終点)").click()
    page.get_by_text("5").nth(5).click()
    page.get_by_text("分析登録", exact=True).click()
    with page.expect_popup() as page1_info:
        page.get_by_role("link", name="分析を表示する").click()
    page1 = page1_info.value
    page1.get_by_role("button", name=" 再計算").click()
    with page1.expect_download() as download_info:
        page1.get_by_role("link", name="CSVエクスポート").click()
    download = download_info.value

    # ---------------------
    context.close()
    browser.close()


with sync_playwright() as playwright:
    run(playwright)
