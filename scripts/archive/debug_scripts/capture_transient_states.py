
from playwright.sync_api import sync_playwright


def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False) # Headless=False to see if it's actually working
        context = browser.new_context()
        page = context.new_page()

        print("--- Navigating to Home ---")
        page.goto("https://automationexercise.com")

        # 1. Capture 'Added confirmation popup'
        print("--- Adding product to cart ---")
        # Select first product
        page.click('a[href="/product_details/38"]')
        page.click('button:has-text("Add to cart")')

        # Wait for the popup
        page.wait_for_selector(".modal-content", timeout=5000)
        popup_html = page.content()
        with open("debug_popup.html", "w", encoding="utf-8") as f:
            f.write(popup_html)
        print("Captured popup HTML to debug_popup.html")

        # 2. Capture 'Proceed to Checkout'
        print("--- Navigating to Cart ---")
        page.goto("https://automationexercise.com/view_cart")
        cart_html = page.content()
        with open("debug_cart.html", "w", encoding="utf-8") as f:
            f.write(cart_html)
        print("Captured cart HTML to debug_cart.html")

        browser.close()

if __name__ == "__main__":
    run()
