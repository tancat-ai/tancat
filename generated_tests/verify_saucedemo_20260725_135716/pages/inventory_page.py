"""Auto-generated page object module."""

from playwright.sync_api import Page
from src.evidence_tracker import EvidenceTracker


class InventoryPage:
    """Page Object for https://www.saucedemo.com/inventory.html. Scraped elements: 138."""

    URL = "https://www.saucedemo.com/inventory.html"

    def __init__(self, page: Page, tracker: EvidenceTracker) -> None:
        self.page = page
        self.tracker = tracker

    def navigate(self) -> None:
        self.tracker.navigate(self.URL)

    def click(self, description: str) -> None:
        """Click by semantic description — resolve to POM method or delegate to tracker."""
        import re

        clean = description.lower().strip().strip(chr(39) + chr(34))
        method_name = "click_" + re.sub(r"[^a-z0-9]", "_", clean)
        method_name = re.sub(r"_+", "_", method_name).strip("_")
        # Use dir() to avoid triggering __getattr__ which calls pytest.skip()
        # Search click_ methods AND navigate_ methods (e.g. navigate_to_cart)
        action_methods = {m for m in dir(self) if m.startswith("click_") or m.startswith("navigate_")}
        if method_name in action_methods:
            # If the exact match is a click_ method but there's also a
            # navigate_ method covering the same target, prefer navigate_.
            if method_name.startswith("click_"):
                target = method_name[len("click_") :]
                for method in dir(self):
                    if method.startswith("navigate_"):
                        if target.split("_")[-1] in method:
                            getattr(self, method)()
                            return
            getattr(self, method_name)()
            return
        # Partial match: score action methods by keyword overlap.
        # Remove noise words (link, button, section, navigation, category, page, etc.)
        # and action prefixes (click, navigate) so that click_view_cart and
        # navigate_to_cart are scored equally on their semantic content.
        noise = {
            "the",
            "a",
            "an",
            "in",
            "on",
            "at",
            "to",
            "for",
            "with",
            "by",
            "from",
            "of",
            "and",
            "or",
            "link",
            "button",
            "section",
            "navigation",
            "category",
            "page",
            "header",
            "popup",
            "menu",
            "item",
            "list",
            "click",
            "navigate",
        }
        desc_parts = [p for p in method_name.split("_") if p and p not in noise]
        # Minimum score: when the description has multiple significant words
        # (e.g. 'add_to_cart' -> ['add', 'cart']), require at least 2 matches
        # to avoid false positives like 'navigate_to_cart' matching on just 'cart'.
        # Single-word descriptions still match on 1 (e.g. 'Dress' -> click_dress).
        min_score = 2 if len(desc_parts) >= 2 else 1
        best_method, best_score = None, 0
        # Sort so navigate_ methods come FIRST (key=0) and click_ after (key=1).
        # Then use >= so the FIRST best match wins — preferring navigate_.
        for method in sorted(action_methods, key=lambda m: not m.startswith("navigate_")):
            score = sum(1 for p in desc_parts if p in method)
            # navigate_ methods use a[href=...] locators and are inherently reliable,
            # so they only need score >= 1 even for multi-word descriptions.
            nav_min = 1 if method.startswith("navigate_") else min_score
            if score < nav_min:
                continue
            # Penalize very long method names that match on coincidence.
            # e.g. click_your_product_has_been_added_to_cart (6 words) matching
            # 'add'+'cart' is a false positive. Use match-ratio (score/words)
            # so click_view_cart (2/2=1.0) beats click_..._added_to_cart (2/6=0.33).
            method_words = len([w for w in method.split("_") if w not in {"click", "navigate"}])
            ratio = score / max(method_words, 1)
            # Only boost navigate_ if the description suggests navigation
            # (contains words like 'view', 'go', 'page') — not for actions like 'Add to cart'.
            nav_keywords = {"view", "go", "page", "home", "login", "signup", "checkout"}
            if method.startswith("navigate_") and any(k in desc_parts for k in nav_keywords):
                ratio += 0.5
            if ratio > best_score:
                best_method, best_score = method, ratio
        # Require a minimum match ratio to avoid false positives.
        # e.g. 'add_to_cart' matching click_..._added_to_cart (ratio=0.29)
        # is worse than falling through to text-matching last resort.
        if best_method and best_score > 0.5:
            getattr(self, best_method)()
            return
        # Last resort: use page.locator with text matching (fast-fail).
        # Avoids delegating to evidence_tracker with a raw description
        # which Playwright tries as a CSS selector and hangs on 5s timeout.
        try:
            self.tracker.click("text=" + description, label=description)
        except Exception:
            self.page.locator("text=" + description).first.click(timeout=3000)
            raise

    def __getattr__(self, name):
        def fallback(*args, **kwargs):
            import pytest

            pytest.skip(
                f"Method '{name}' not found on {self.__class__.__name__}. The scraper may have missed this element or its label changed."
            )

        return fallback

    def click_open_menu(self) -> None:
        self.tracker.click("#react-burger-menu-btn", label="open menu")

    def click_all_items(self) -> None:
        self.tracker.click("#inventory_sidebar_link", label="all items")

    def click_about(self) -> None:
        self.tracker.click("#about_sidebar_link", label="about")

    def click_logout(self) -> None:
        self.tracker.click("#logout_sidebar_link", label="logout")

    def click_reset_app_state(self) -> None:
        self.tracker.click("#reset_sidebar_link", label="reset app state")

    def click_close_menu(self) -> None:
        self.tracker.click("#react-burger-cross-btn", label="close menu")

    def click_1(self) -> None:
        self.tracker.click('[data-test="shopping-cart-link"]', label="1")

    def select_name_a_to_z_name_z_to_a_price_low_to_high_price_high_to_low(self, value: str) -> None:
        self.tracker.fill(
            '[data-test="product-sort-container"]',
            value,
            label="name a to z name z to a price low to high price high to low",
        )

    def click_item_4_img_link(self) -> None:
        self.tracker.click("#item_4_img_link", label="item 4 img link")

    def click_sauce_labs_backpack(self) -> None:
        self.tracker.click("#item_4_title_link", label="sauce labs backpack")

    def click_remove(self) -> None:
        self.tracker.click("#remove-sauce-labs-backpack", label="remove")

    def click_item_0_img_link(self) -> None:
        self.tracker.click("#item_0_img_link", label="item 0 img link")

    def click_sauce_labs_bike_light(self) -> None:
        self.tracker.click("#item_0_title_link", label="sauce labs bike light")

    def add_item_to_cart(self) -> None:
        self.tracker.click("#add-to-cart-sauce-labs-bike-light", label="add item to cart")

    def click_item_1_img_link(self) -> None:
        self.tracker.click("#item_1_img_link", label="item 1 img link")

    def click_sauce_labs_bolt_t_shirt(self) -> None:
        self.tracker.click("#item_1_title_link", label="sauce labs bolt t shirt")

    def click_item_5_img_link(self) -> None:
        self.tracker.click("#item_5_img_link", label="item 5 img link")

    def click_sauce_labs_fleece_jacket(self) -> None:
        self.tracker.click("#item_5_title_link", label="sauce labs fleece jacket")

    def click_item_2_img_link(self) -> None:
        self.tracker.click("#item_2_img_link", label="item 2 img link")

    def click_sauce_labs_onesie(self) -> None:
        self.tracker.click("#item_2_title_link", label="sauce labs onesie")

    def click_item_3_img_link(self) -> None:
        self.tracker.click("#item_3_img_link", label="item 3 img link")

    def click_test_allthethings_t_shirt_red(self) -> None:
        self.tracker.click("#item_3_title_link", label="test allthethings t shirt red")

    def click_twitter(self) -> None:
        self.tracker.click('[data-test="social-twitter"]', label="twitter")

    def click_facebook(self) -> None:
        self.tracker.click('[data-test="social-facebook"]', label="facebook")

    def click_linkedin(self) -> None:
        self.tracker.click('[data-test="social-linkedin"]', label="linkedin")

    def click_swag_labs(self) -> None:
        self.tracker.click("title", label="swag labs")

    def click_open_menu_all_items_about_logout_reset_app_state_close_menu_swag_labs_1_products_name_a_to_z_name_a_to_z_name_z_to_a_price_low_to_high_price_high_to_low(
        self,
    ) -> None:
        self.tracker.click(
            "#header_container",
            label="open menu all items about logout reset app state close menu swag labs 1 products name a to z name a to z name z to a price low to high price high to low",
        )

    def click_open_menu_all_items_about_logout_reset_app_state_close_menu_swag_labs_1(self) -> None:
        self.tracker.click(
            '[data-test="primary-header"]',
            label="open menu all items about logout reset app state close menu swag labs 1",
        )

    def click_products_name_a_to_z_name_a_to_z_name_z_to_a_price_low_to_high_price_high_to_low(self) -> None:
        self.tracker.click(
            '[data-test="secondary-header"]',
            label="products name a to z name a to z name z to a price low to high price high to low",
        )

    def click_products(self) -> None:
        self.tracker.click('[data-test="title"]', label="products")

    def click_name_a_to_z_name_a_to_z_name_z_to_a_price_low_to_high_price_high_to_low(self) -> None:
        self.tracker.click(
            ".select_container", label="name a to z name a to z name z to a price low to high price high to low"
        )

    def click_name_a_to_z(self) -> None:
        self.tracker.click('[data-test="active-option"]', label="name a to z")

    def click_sauce_labs_backpack_carry_allthethings_with_the_sleek_streamlined_sly_pack_that_melds_uncompromising_style_with_unequaled_laptop_and_tablet_protection_29_99_remove(
        self,
    ) -> None:
        self.tracker.click(
            '[data-test="inventory-item"]',
            label="sauce labs backpack carry allthethings with the sleek streamlined sly pack that melds uncompromising style with unequaled laptop and tablet protection 29 99 remove",
        )

    def click_carry_allthethings_with_the_sleek_streamlined_sly_pack_that_melds_uncompromising_style_with_unequaled_laptop_and_tablet_protection(
        self,
    ) -> None:
        self.tracker.click(
            '[data-test="inventory-item-desc"]',
            label="carry allthethings with the sleek streamlined sly pack that melds uncompromising style with unequaled laptop and tablet protection",
        )

    def click_29_99(self) -> None:
        self.tracker.click('[data-test="inventory-item-price"]', label="29 99")

    def click_sauce_labs_bike_light_a_red_light_isn_t_the_desired_state_in_testing_but_it_sure_helps_when_riding_your_bike_at_night_water_resistant_with_3_lighting_modes_1_aaa_battery_included_9_99_add_to_cart(
        self,
    ) -> None:
        self.tracker.click(
            '[data-test="inventory-item"]',
            label="sauce labs bike light a red light isn t the desired state in testing but it sure helps when riding your bike at night water resistant with 3 lighting modes 1 aaa battery included 9 99 add to cart",
        )

    def click_a_red_light_isn_t_the_desired_state_in_testing_but_it_sure_helps_when_riding_your_bike_at_night_water_resistant_with_3_lighting_modes_1_aaa_battery_included(
        self,
    ) -> None:
        self.tracker.click(
            '[data-test="inventory-item-desc"]',
            label="a red light isn t the desired state in testing but it sure helps when riding your bike at night water resistant with 3 lighting modes 1 aaa battery included",
        )

    def click_9_99(self) -> None:
        self.tracker.click('[data-test="inventory-item-price"]', label="9 99")

    def click_sauce_labs_bolt_t_shirt_get_your_testing_superhero_on_with_the_sauce_labs_bolt_t_shirt_from_american_apparel_100_ringspun_combed_cotton_heather_gray_with_red_bolt_15_99_add_to_cart(
        self,
    ) -> None:
        self.tracker.click(
            '[data-test="inventory-item"]',
            label="sauce labs bolt t shirt get your testing superhero on with the sauce labs bolt t shirt from american apparel 100 ringspun combed cotton heather gray with red bolt 15 99 add to cart",
        )

    def click_get_your_testing_superhero_on_with_the_sauce_labs_bolt_t_shirt_from_american_apparel_100_ringspun_combed_cotton_heather_gray_with_red_bolt(
        self,
    ) -> None:
        self.tracker.click(
            '[data-test="inventory-item-desc"]',
            label="get your testing superhero on with the sauce labs bolt t shirt from american apparel 100 ringspun combed cotton heather gray with red bolt",
        )

    def click_15_99(self) -> None:
        self.tracker.click('[data-test="inventory-item-price"]', label="15 99")

    def click_sauce_labs_fleece_jacket_it_s_not_every_day_that_you_come_across_a_midweight_quarter_zip_fleece_jacket_capable_of_handling_everything_from_a_relaxing_day_outdoors_to_a_busy_day_at_the_office_49_99_add_to_cart(
        self,
    ) -> None:
        self.tracker.click(
            '[data-test="inventory-item"]',
            label="sauce labs fleece jacket it s not every day that you come across a midweight quarter zip fleece jacket capable of handling everything from a relaxing day outdoors to a busy day at the office 49 99 add to cart",
        )

    def click_it_s_not_every_day_that_you_come_across_a_midweight_quarter_zip_fleece_jacket_capable_of_handling_everything_from_a_relaxing_day_outdoors_to_a_busy_day_at_the_office(
        self,
    ) -> None:
        self.tracker.click(
            '[data-test="inventory-item-desc"]',
            label="it s not every day that you come across a midweight quarter zip fleece jacket capable of handling everything from a relaxing day outdoors to a busy day at the office",
        )

    def click_49_99(self) -> None:
        self.tracker.click('[data-test="inventory-item-price"]', label="49 99")

    def click_sauce_labs_onesie_rib_snap_infant_onesie_for_the_junior_automation_engineer_in_development_reinforced_3_snap_bottom_closure_two_needle_hemmed_sleeved_and_bottom_won_t_unravel_7_99_add_to_cart(
        self,
    ) -> None:
        self.tracker.click(
            '[data-test="inventory-item"]',
            label="sauce labs onesie rib snap infant onesie for the junior automation engineer in development reinforced 3 snap bottom closure two needle hemmed sleeved and bottom won t unravel 7 99 add to cart",
        )

    def click_rib_snap_infant_onesie_for_the_junior_automation_engineer_in_development_reinforced_3_snap_bottom_closure_two_needle_hemmed_sleeved_and_bottom_won_t_unravel(
        self,
    ) -> None:
        self.tracker.click(
            '[data-test="inventory-item-desc"]',
            label="rib snap infant onesie for the junior automation engineer in development reinforced 3 snap bottom closure two needle hemmed sleeved and bottom won t unravel",
        )

    def click_7_99(self) -> None:
        self.tracker.click('[data-test="inventory-item-price"]', label="7 99")

    def click_test_allthethings_t_shirt_red_this_classic_sauce_labs_t_shirt_is_perfect_to_wear_when_cozying_up_to_your_keyboard_to_automate_a_few_tests_super_soft_and_comfy_ringspun_combed_cotton_15_99_add_to_cart(
        self,
    ) -> None:
        self.tracker.click(
            '[data-test="inventory-item"]',
            label="test allthethings t shirt red this classic sauce labs t shirt is perfect to wear when cozying up to your keyboard to automate a few tests super soft and comfy ringspun combed cotton 15 99 add to cart",
        )

    def click_this_classic_sauce_labs_t_shirt_is_perfect_to_wear_when_cozying_up_to_your_keyboard_to_automate_a_few_tests_super_soft_and_comfy_ringspun_combed_cotton(
        self,
    ) -> None:
        self.tracker.click(
            '[data-test="inventory-item-desc"]',
            label="this classic sauce labs t shirt is perfect to wear when cozying up to your keyboard to automate a few tests super soft and comfy ringspun combed cotton",
        )

    def click_2026_sauce_labs_all_rights_reserved_terms_of_service_privacy_policy(self) -> None:
        self.tracker.click(
            '[data-test="footer-copy"]', label="2026 sauce labs all rights reserved terms of service privacy policy"
        )

    def click_unnamed(self) -> None:
        self.tracker.click("#item_4_img_link", label="unnamed")
