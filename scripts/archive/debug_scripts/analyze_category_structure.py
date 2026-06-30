from playwright.sync_api import sync_playwright

from src.browser_utils import dismiss_consent_overlays

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context()
    page = context.new_page()

    page.goto("https://automationexercise.com")
    dismiss_consent_overlays(page)

    # Click on "Dress" category
    page.click('a[href="/category_products/1"]', timeout=5000)
    page.wait_for_load_state("networkidle")

    print("--- All links on Category Page ---")
    links = page.locator("a").all()
    for link in links:
        try:
            text = link.text_content().strip()
            href = link.get_attribute("href")
            if href and "product_details" in href:
                print(f"  Product link: {text[:30]} -> {href}")
        except:
            pass

    print(f"\nTotal links: {len(links)}")

    # Check for product items
    products = page.locator('.grid-products .col-md-3').all()
    print(f"Product items found: {len(products)}")

    # Try to click first product
    if products:
        print("\n--- Clicking first product item ---")
        products[0].locator('a').first.click()
        page.wait_for_load_state("networkidle")
        print(f"Current URL: {page.url}")

        # Click Add to Cart
        print("\n--- Clicking Add to Cart ---")
        page.click('button:has-text("Add to cart")', timeout=5000)
        page.wait_for_timeout(1000)

        # Check for modal
        print("\n--- Checking for modal ---")
        modal = page.locator('.modal-content').first
        if modal.count() > 0:
            print(f"Modal found! Text: {modal.inner_text()[:200]}")
        else:
            print("No modal found!")

    browser.close()
