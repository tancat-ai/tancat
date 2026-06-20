from playwright.sync_api import sync_playwright
from src.browser_utils import dismiss_consent_overlays

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context()
    page = context.new_page()

    # Navigate and dismiss consent
    page.goto("https://automationexercise.com")
    dismiss_consent_overlays(page)

    # Click on "Dress" category
    page.click('a[href="/category_products/1"]', timeout=5000)
    page.wait_for_load_state("networkidle")
    
    # List available clickable elements
    print("--- Links on Category Page ---")
    links = page.locator("a").all()
    for link in links[:10]:
        try:
            text = link.text_content().strip()
            href = link.get_attribute("href")
            if text:
                print(f"  {text} -> {href}")
        except:
            pass

    # Click first product
    print("\n--- Clicking first product ---")
    page.click('.products a:has(img)').first
    page.wait_for_load_state("networkidle")
    print(f"Current URL: {page.url}")

    # Now click "Add to Cart"
    print("\n--- Clicking Add to Cart ---")
    page.click('button:has-text("Add to cart")', timeout=5000)
    page.wait_for_timeout(1000)
    
    # Capture the popup
    print("\n--- Popup Elements ---")
    modal = page.locator('.modal-content')
    if modal.count() > 0:
        print(f"Modal content: {modal.inner_text()[:200]}")
        # List buttons in modal
        buttons = modal.locator('button').all()
        for btn in buttons:
            print(f"  Modal button: {btn.text_content().strip()}")
    else:
        print("No .modal-content found!")

    browser.close()
