from playwright.sync_api import sync_playwright


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto("https://www.saucedemo.com")
        page.wait_for_timeout(2000)
        loc = page.locator("#user-name")
        print("Count:", loc.count())
        if loc.count() > 0:
            print("Visible:", loc.first.is_visible())
            print("HTML:", loc.first.evaluate("el => el.outerHTML"))
        browser.close()

if __name__ == "__main__":
    main()
