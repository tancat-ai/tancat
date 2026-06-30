#====================================================================
# Skeleton Variability Report — 5 valid runs
#====================================================================

## Run 1
Skeletons: 6, Tokens: 0
PAGES_NEEDED: {'home'}

Test functions:
  - test_01_navigate_to_homepage (3 steps)
  - test_02_login_with_valid_credentials (6 steps)
  - test_03_add_product_to_cart (7 steps)
  - test_04_click_cart_link_to_view_cart (8 steps)
  - test_05_click_continue_shopping_to_return_to_products (9 steps)
  - test_06_proceed_through_checkout_and_verify_confirmation (13 steps)

Tokens:

Raw skeleton:
from playwright.sync_api import Page, expect

@pytest.mark.evidence(condition_ref="TC-01", story_ref="S01")
def test_01_navigate_to_homepage(page, evidence_tracker):
    {GOTO:home}
    {ASSERT:saucedemo homepage visible}

@pytest.mark.evidence(condition_ref="TC-02", story_ref="S01")
def test_02_login_with_valid_credentials(page, evidence_tracker):
    {GOTO:home}
    {FILL:username:standard_user}
    {FILL:password:secret_sauce}
    {CLICK:login button}
    {ASSERT:products inventory page visible}

@pytest.mark.evidence(condition_ref="TC-03", story_ref="S01")
def test_03_add_product_to_cart(page, evidence_tracker):
    {GOTO:home}
    {FILL:username:standard_user}
    {FILL:password:secret_sauce}
    {CLICK:login button}
    {CLICK:add to cart button for sauce lab backpack}
    {ASSERT:cart badge shows 1 item}

@pytest.mark.evidence(condition_ref="TC-04", story_ref="S01")
def test_04_click_cart_link_to_view_cart(page, evidence_tracker):
    {GOTO:home}
    {FILL:username:standard_user}
    {FILL:password:secret_sauce}
    {CLICK:login button}
    {CLICK:add to cart button for sauce lab backpack}
    {CLICK:shopping cart link}
    {ASSERT:cart page displays added item}

@pytest.mark.evidence(condition_ref="TC-05", story_ref="S01")
def test_05_click_continue_shopping_to_return_to_products(page, evidence_tracker):
    {GOTO:home}
    {FILL:username:standard_user}
    {FILL:password:secret_sauce}
    {CLICK:login button}
    {CLICK:add to cart button for sauce lab backpack}
    {CLICK:shopping cart link}
    {CLICK:continue shopping button}
    {ASSERT:products inventory page visible}

@pytest.mark.evidence(condition_ref="TC-06", story_ref="S01")
def test_06_proceed_through_checkout_and_verify_confirmation(page, evidence_tracker):
    {GOTO:home}
    {FILL:username:standard_user}
    {FILL:password:secret_sauce}
    {CLICK:login button}
    {CLICK:add to cart button for sauce lab backpack}
    {CLICK:shopping cart link}
    {CLICK:checkout button}
    {FILL:first name:John}
    {FILL:last name:Doe}
    {FILL:zip code:12345}
    {CLICK:continue button}
    {CLICK:finish button}
    {ASSERT:order confirmation message}

# PAGES_NEEDED:
# - home (homepage)

## Run 2
Skeletons: 6, Tokens: 0
PAGES_NEEDED: {'home'}

Test functions:
  - test_01_navigate_to_homepage (3 steps)
  - test_02_login_with_valid_credentials (6 steps)
  - test_03_add_product_to_cart (7 steps)
  - test_04_click_cart_link_to_view_cart (8 steps)
  - test_05_continue_shopping_returns_to_products (9 steps)
  - test_06_proceed_through_checkout_and_verify_confirmation (13 steps)

Tokens:

Raw skeleton:
from playwright.sync_api import Page, expect

@pytest.mark.evidence(condition_ref="TC-01", story_ref="S01")
def test_01_navigate_to_homepage(page, evidence_tracker):
    {GOTO:home}
    {ASSERT:homepage loaded}

@pytest.mark.evidence(condition_ref="TC-02", story_ref="S01")
def test_02_login_with_valid_credentials(page, evidence_tracker):
    {GOTO:home}
    {FILL:username:standard_user}
    {FILL:password:secret_sauce}
    {CLICK:login button}
    {ASSERT:products page loaded}

@pytest.mark.evidence(condition_ref="TC-03", story_ref="S01")
def test_03_add_product_to_cart(page, evidence_tracker):
    {GOTO:home}
    {FILL:username:standard_user}
    {FILL:password:secret_sauce}
    {CLICK:login button}
    {CLICK:add to cart button}
    {ASSERT:cart badge updated}

@pytest.mark.evidence(condition_ref="TC-04", story_ref="S01")
def test_04_click_cart_link_to_view_cart(page, evidence_tracker):
    {GOTO:home}
    {FILL:username:standard_user}
    {FILL:password:secret_sauce}
    {CLICK:login button}
    {CLICK:add to cart button}
    {CLICK:cart link}
    {ASSERT:cart page loaded}

@pytest.mark.evidence(condition_ref="TC-05", story_ref="S01")
def test_05_continue_shopping_returns_to_products(page, evidence_tracker):
    {GOTO:home}
    {FILL:username:standard_user}
    {FILL:password:secret_sauce}
    {CLICK:login button}
    {CLICK:add to cart button}
    {CLICK:cart link}
    {CLICK:continue shopping button}
    {ASSERT:products page loaded}

@pytest.mark.evidence(condition_ref="TC-06", story_ref="S01")
def test_06_proceed_through_checkout_and_verify_confirmation(page, evidence_tracker):
    {GOTO:home}
    {FILL:username:standard_user}
    {FILL:password:secret_sauce}
    {CLICK:login button}
    {CLICK:add to cart button}
    {CLICK:cart link}
    {CLICK:checkout button}
    {FILL:first name:John}
    {FILL:last name:Doe}
    {FILL:zip code:12345}
    {CLICK:continue button}
    {CLICK:finish button}
    {ASSERT:order confirmation message}

# PAGES_NEEDED:
# - home (homepage)

## Run 3
Skeletons: 6, Tokens: 0
PAGES_NEEDED: {'home'}

Test functions:
  - test_01_navigate_to_homepage (3 steps)
  - test_02_log_in_with_valid_credentials (6 steps)
  - test_03_add_product_to_cart (7 steps)
  - test_04_click_cart_link_to_view_cart (8 steps)
  - test_05_continue_shopping_returns_to_products (9 steps)
  - test_06_proceed_through_checkout_and_verify_confirmation (13 steps)

Tokens:

Raw skeleton:
from playwright.sync_api import Page, expect

@pytest.mark.evidence(condition_ref="TC-01", story_ref="S01")
def test_01_navigate_to_homepage(page, evidence_tracker):
    {GOTO:home}
    {ASSERT:homepage title}

@pytest.mark.evidence(condition_ref="TC-02", story_ref="S01")
def test_02_log_in_with_valid_credentials(page, evidence_tracker):
    {GOTO:home}
    {FILL:username:standard_user}
    {FILL:password:secret_sauce}
    {CLICK:login button}
    {ASSERT:products page title}

@pytest.mark.evidence(condition_ref="TC-03", story_ref="S01")
def test_03_add_product_to_cart(page, evidence_tracker):
    {GOTO:home}
    {FILL:username:standard_user}
    {FILL:password:secret_sauce}
    {CLICK:login button}
    {CLICK:add to cart button}
    {ASSERT:cart badge updated}

@pytest.mark.evidence(condition_ref="TC-04", story_ref="S01")
def test_04_click_cart_link_to_view_cart(page, evidence_tracker):
    {GOTO:home}
    {FILL:username:standard_user}
    {FILL:password:secret_sauce}
    {CLICK:login button}
    {CLICK:add to cart button}
    {CLICK:cart link}
    {ASSERT:cart page title}

@pytest.mark.evidence(condition_ref="TC-05", story_ref="S01")
def test_05_continue_shopping_returns_to_products(page, evidence_tracker):
    {GOTO:home}
    {FILL:username:standard_user}
    {FILL:password:secret_sauce}
    {CLICK:login button}
    {CLICK:add to cart button}
    {CLICK:cart link}
    {CLICK:continue shopping button}
    {ASSERT:products page title}

@pytest.mark.evidence(condition_ref="TC-06", story_ref="S01")
def test_06_proceed_through_checkout_and_verify_confirmation(page, evidence_tracker):
    {GOTO:home}
    {FILL:username:standard_user}
    {FILL:password:secret_sauce}
    {CLICK:login button}
    {CLICK:add to cart button}
    {CLICK:cart link}
    {CLICK:checkout button}
    {FILL:first name:John}
    {FILL:last name:Doe}
    {FILL:zip code:12345}
    {CLICK:continue button}
    {CLICK:finish button}
    {ASSERT:order confirmation message}

# PAGES_NEEDED:
# - home (homepage)

## Run 4
Skeletons: 6, Tokens: 0
PAGES_NEEDED: {'checkout', 'cart', 'products', 'home'}

Test functions:
  - test_01_navigate_to_homepage (3 steps)
  - test_02_log_in_with_valid_credentials (6 steps)
  - test_03_add_product_to_cart (7 steps)
  - test_04_click_cart_link_to_view_cart (8 steps)
  - test_05_click_continue_shopping_to_return_to_products (9 steps)
  - test_06_proceed_through_checkout_and_verify_confirmation (13 steps)

Tokens:

Raw skeleton:
from playwright.sync_api import Page, expect

@pytest.mark.evidence(condition_ref="TC-01", story_ref="S01")
def test_01_navigate_to_homepage(page, evidence_tracker):
    {GOTO:home}
    {ASSERT:homepage loaded}

@pytest.mark.evidence(condition_ref="TC-02", story_ref="S01")
def test_02_log_in_with_valid_credentials(page, evidence_tracker):
    {GOTO:home}
    {FILL:username input:standard_user}
    {FILL:password input:secret_sauce}
    {CLICK:login button}
    {ASSERT:products page loaded}

@pytest.mark.evidence(condition_ref="TC-03", story_ref="S01")
def test_03_add_product_to_cart(page, evidence_tracker):
    {GOTO:home}
    {FILL:username input:standard_user}
    {FILL:password input:secret_sauce}
    {CLICK:login button}
    {CLICK:add to cart button for first product}
    {ASSERT:cart badge displays one item}

@pytest.mark.evidence(condition_ref="TC-04", story_ref="S01")
def test_04_click_cart_link_to_view_cart(page, evidence_tracker):
    {GOTO:home}
    {FILL:username input:standard_user}
    {FILL:password input:secret_sauce}
    {CLICK:login button}
    {CLICK:add to cart button for first product}
    {CLICK:cart link}
    {ASSERT:cart page displays items}

@pytest.mark.evidence(condition_ref="TC-05", story_ref="S01")
def test_05_click_continue_shopping_to_return_to_products(page, evidence_tracker):
    {GOTO:home}
    {FILL:username input:standard_user}
    {FILL:password input:secret_sauce}
    {CLICK:login button}
    {CLICK:add to cart button for first product}
    {CLICK:cart link}
    {CLICK:continue shopping button}
    {ASSERT:products page loaded}

@pytest.mark.evidence(condition_ref="TC-06", story_ref="S01")
def test_06_proceed_through_checkout_and_verify_confirmation(page, evidence_tracker):
    {GOTO:home}
    {FILL:username input:standard_user}
    {FILL:password input:secret_sauce}
    {CLICK:login button}
    {CLICK:add to cart button for first product}
    {CLICK:cart link}
    {CLICK:checkout button}
    {FILL:firstname input:John}
    {FILL:lastname input:Doe}
    {FILL:zip input:12345}
    {CLICK:continue button}
    {CLICK:finish button}
    {ASSERT:order confirmation message visible}

# PAGES_NEEDED:
# - home (homepage)
# - products (inventory page)
# - cart (shopping cart page)
# - checkout (checkout page)

## Run 5
Skeletons: 6, Tokens: 0
PAGES_NEEDED: {'checkout', 'cart', 'home'}

Test functions:
  - test_01_navigate_to_homepage (3 steps)
  - test_02_login_with_valid_credentials (6 steps)
  - test_03_add_product_to_cart (7 steps)
  - test_04_click_cart_link_to_view_cart (8 steps)
  - test_05_continue_shopping_to_return_to_products (9 steps)
  - test_06_proceed_through_checkout_and_verify_confirmation (13 steps)

Tokens:

Raw skeleton:
from playwright.sync_api import Page, expect

@pytest.mark.evidence(condition_ref="TC-01", story_ref="S01")
def test_01_navigate_to_homepage(page, evidence_tracker):
    {GOTO:home}
    {ASSERT:sauce demo homepage}

@pytest.mark.evidence(condition_ref="TC-02", story_ref="S01")
def test_02_login_with_valid_credentials(page, evidence_tracker):
    {GOTO:home}
    {FILL:username:standard_user}
    {FILL:password:secret_sauce}
    {CLICK:login button}
    {ASSERT:products inventory page}

@pytest.mark.evidence(condition_ref="TC-03", story_ref="S01")
def test_03_add_product_to_cart(page, evidence_tracker):
    {GOTO:home}
    {FILL:username:standard_user}
    {FILL:password:secret_sauce}
    {CLICK:login button}
    {CLICK:add to cart button}
    {ASSERT:cart badge updated}

@pytest.mark.evidence(condition_ref="TC-04", story_ref="S01")
def test_04_click_cart_link_to_view_cart(page, evidence_tracker):
    {GOTO:home}
    {FILL:username:standard_user}
    {FILL:password:secret_sauce}
    {CLICK:login button}
    {CLICK:add to cart button}
    {CLICK:cart link}
    {ASSERT:cart page visible}

@pytest.mark.evidence(condition_ref="TC-05", story_ref="S01")
def test_05_continue_shopping_to_return_to_products(page, evidence_tracker):
    {GOTO:home}
    {FILL:username:standard_user}
    {FILL:password:secret_sauce}
    {CLICK:login button}
    {CLICK:add to cart button}
    {CLICK:cart link}
    {CLICK:continue shopping button}
    {ASSERT:products inventory page}

@pytest.mark.evidence(condition_ref="TC-06", story_ref="S01")
def test_06_proceed_through_checkout_and_verify_confirmation(page, evidence_tracker):
    {GOTO:home}
    {FILL:username:standard_user}
    {FILL:password:secret_sauce}
    {CLICK:login button}
    {CLICK:add to cart button}
    {CLICK:cart link}
    {CLICK:checkout button}
    {FILL:first name:John}
    {FILL:last name:Doe}
    {FILL:postal code:12345}
    {CLICK:continue button}
    {CLICK:finish button}
    {ASSERT:order confirmation message}

# PAGES_NEEDED:
# - home (homepage)
# - cart (shopping cart page)
# - checkout (checkout page)
