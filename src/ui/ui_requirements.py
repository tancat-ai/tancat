"""Requirements input panel."""

from __future__ import annotations

import streamlit as st


class RequirementsInput:
    """Renders the requirements input section."""

    # Baseline preset for reproducible debugging runs.
    BASELINE_STARTING_URL = "https://automationexercise.com/"
    BASELINE_ADDITIONAL_URLS = ""
    BASELINE_REQUIREMENTS: str = """## User Story
As a shopper on automationexercise.com, I want to browse products by category, add items to my cart, review the cart contents, and proceed to checkout so that I can complete a purchase.

## Acceptance Criteria
1. Navigate to the home page and verify the page loads successfully with product categories visible
2. Click on the "Dress" category link and verify the category products page displays a list of products
3. On the category page, click "Add to cart" on a product and verify an "Add to cart confirmation popup" appears
4. Close the confirmation popup by clicking "Continue Shopping" and verify I remain on the category page
5. Click the "View Cart" link in the header navigation and verify the cart page loads showing a table of added items
6. On the cart page, verify the product name, price, and quantity are displayed correctly in the cart table
7. Click the "Proceed to checkout" button on the cart page and verify the checkout page loads with order summary visible
8. On the checkout page, verify I am logged in automatically or prompted to login if not already authenticated

(Total: 8 criteria)
"""

    @staticmethod
    def render(base_url: str, urls_input: str) -> tuple[str, str, str, str]:
        """Render requirements input and return (input_mode, raw_text, base_url, urls_input)."""
        col1, col2 = st.columns([2, 1])

        with col1:
            input_mode = st.radio("Requirements Input", ["Paste Text", "Upload File"], horizontal=True)
            raw_requirements = ""

            if input_mode == "Upload File":
                uploaded_file = st.file_uploader("Upload user story or markdown", type=["md", "txt"])
                if uploaded_file is not None:
                    raw_requirements = uploaded_file.read().decode("utf-8")
                    st.text_area("Uploaded Requirements", value=raw_requirements, height=220, disabled=True)
                else:
                    st.info("Upload a `.md` or `.txt` file containing your user story and acceptance criteria.")
            else:
                raw_requirements = st.text_area(
                    "Requirements",
                    placeholder="## User Story\\nAs a customer I want to add items to cart\\n\\n## Acceptance Criteria\\n1. Add item to cart\\n2. Go to cart\\n3. Check out",
                    height=260,
                    key="requirements_text",
                )

        with col2:
            st.info(
                "Primary workflow:\\n"
                "1. Generate a placeholder-based skeleton.\\n"
                "2. Scrape the required pages.\\n"
                "3. Resolve placeholders into real locators.\\n"
                "4. Save the final Python test file."
            )
            st.caption("The intelligent pipeline is now the only generation path in this UI.")

        return input_mode, raw_requirements, base_url, urls_input
