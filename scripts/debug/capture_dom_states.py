from playwright.sync_api import sync_playwright
import json

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        
        # 1. Handle Consent
        print("Navigating to Home...")
        page.goto("https://automationexercise.com")
        try:
            # Attempt to find and click a 'Accept' or 'Agree' button if it exists
            # based on the previous error logs showing "fc-consent-root"
            page.click('button:has-text("Accept")', timeout=5000)
            print("Consent accepted.")
        except:
            print("No consent button found or timeout.")

        # 2. Capture "Added confirmation popup"
        print("Adding product to cart...")
        # Navigate directly to a product to be safe
        page.goto("https://automationexercise.com/product_details/38")
        page.click('button:has-text("Add to cart")')
        
        # Wait for the popup to appear
        try:
            page.wait_for_selector(".modal-content", timeout=10000)
            with open("debug_popup_dom.html", "w", encoding="utf-8") as f:
                f.write(page.content())
            print("Captured popup DOM.")
        except Exception as e:
            print(f"Failed to capture popup: {e}")

        # 3. Capture "Proceed to Checkout" on Cart Page
        print("Navigating to Cart...")
        page.goto("https://automationexercise.com/view_cart")
        with open("debug_cart_dom.html", "w", encoding="utf-8") as f:
            f.write(page.content())
        print("Captured cart DOM.")
        
        browser.close()

if __name__ == "__main__":
    run()
