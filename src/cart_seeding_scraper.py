"""Cart-seeding scraper — ensures the cart has items before scraping cart/checkout pages.

Extracted from ``journey_scraper.py``. Extends ``JourneyScraper`` for the
common "seed cart then scrape" workflow.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urljoin

from src.form_detector import (
    ADD_TO_CART_SELECTORS,
    CONTINUE_SHOPPING_SELECTORS,
    PRODUCT_SELECTORS,
)
from src.journey_models import JourneyStep
from src.journey_scraper import JourneyScraper


class CartSeedingScraper(JourneyScraper):
    """Journey scraper specialized for cart-dependent pages.

    This scraper follows a specific journey to ensure the cart has items
    before scraping cart/checkout pages:
    1. Navigate to products page
    2. Select a product
    3. Add to cart
    4. Dismiss confirmation modal
    5. Navigate to cart page (now has checkout button)

    This is a convenience wrapper around JourneyScraper for the common
    "scrape cart with items" use case.
    """

    # Class-level selector constants (re-exported from form_detector for compatibility)
    PRODUCT_SELECTORS: list[str] = PRODUCT_SELECTORS
    ADD_TO_CART_SELECTORS: list[str] = ADD_TO_CART_SELECTORS
    CONTINUE_SHOPPING_SELECTORS: list[str] = CONTINUE_SHOPPING_SELECTORS

    def __init__(
        self,
        starting_url: str,
        products_url: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize the cart seeding scraper.

        Args:
            starting_url: The home page URL (used to establish session).
            products_url: Optional explicit products page URL. If not provided,
                          derived from starting_url by appending "/products".
            **kwargs: Additional arguments passed to JourneyScraper.
        """
        super().__init__(starting_url, **kwargs)
        self.products_url = products_url or self._derive_products_url(starting_url)

    @staticmethod
    def _derive_products_url(home_url: str) -> str:
        """Derive the products page URL from the home page URL.

        Example: https://automationexercise.com/ → https://automationexercise.com/products
        """
        return urljoin(home_url, "/products")

    async def scrape_cart_pages(
        self,
        cart_urls: list[str],
    ) -> dict[str, list[dict[str, Any]]]:
        """Scrape cart/checkout pages with items already in the cart.

        This method:
        1. Seeds the cart by adding an item (via the products page)
        2. Captures the confirmation popup state (for resolver to find)
        3. Then scrapes each target URL (cart, checkout, etc.)

        Args:
            cart_urls: URLs to scrape (e.g., [/view_cart, /checkout]).

        Returns:
            Dictionary mapping URL → list of scraped elements.
        """
        steps: list[JourneyStep] = []

        # Step 1: Navigate to products page
        steps.append(
            JourneyStep(
                action="navigate",
                url=self.products_url,
                description="navigate to products page",
            )
        )

        # Step 2: Click on a product
        steps.append(
            JourneyStep(
                action="click",
                selector=PRODUCT_SELECTORS[0],  # Use first matching selector
                description="select a product",
            )
        )

        # Step 3: Click "Add to cart"
        steps.append(
            JourneyStep(
                action="click",
                selector=ADD_TO_CART_SELECTORS[0],
                description="add product to cart",
            )
        )

        # Step 3b: CAPTURE confirmation popup state BEFORE dismissing it.
        # This allows the resolver to find elements like "Added confirmation popup"
        steps.append(
            JourneyStep(
                action="capture",
                description="capture confirmation popup state",
            )
        )

        # Step 4: Dismiss confirmation modal
        steps.append(
            JourneyStep(
                action="click",
                selector=CONTINUE_SHOPPING_SELECTORS[0],
                description="dismiss confirmation modal",
            )
        )

        # Step 5: Wait for modal to disappear
        steps.append(
            JourneyStep(
                action="wait",
                description="1.0",
            )
        )

        # Step 6+: Navigate to and scrape each target URL
        for cart_url in cart_urls:
            full_url = self._ensure_full_url(cart_url)
            steps.append(
                JourneyStep(
                    action="navigate",
                    url=full_url,
                    description=f"navigate to {full_url}",
                )
            )

        return await self.scrape_journey(steps)

    @staticmethod
    def _ensure_full_url(url: str) -> str:
        """Ensure the URL is absolute.

        If the URL is relative, it will be made absolute during navigation
        by the JourneyScraper.
        """
        if url.startswith(("http://", "https://")):
            return url
        return url  # Relative URLs are handled by _navigate_to


__all__ = ["CartSeedingScraper"]
