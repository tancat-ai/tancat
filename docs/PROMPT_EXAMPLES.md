# Playwright Test Generator - Prompt Examples

Based on my system prompt, the LLM expects clear, specific scenarios. Here are good and bad examples:

---

## ❌ BAD PROMPTS

### Example 1: Too vague
```
"Write a test for login"
```
**Problems:**
- No details about what to test (successful login? failed login? edge cases?)
- No mention of selectors or UI elements
- LLM has to guess page structure

### Example 2: Missing critical details
```
"Test the checkout process"
```
**Problems:**
- Which checkout? (guest, logged-in, with coupon?)
- What payment methods?
- What validation steps?
- No information about page elements

### Example 3: Contradictory requirements
```
"Use XPath only and make selectors very specific"
```
**Problems:**
- LLM is instructed to be specific but XPath is generally less robust than data-testid
- System prompt asks for "meaningful selector strategies" with data-testid preferred

### Example 4: No context for dynamic content
```
"Test the search results page"
```
**Problems:**
- What happens when there are no results?
- What if the search takes time to load?
- Any filters or sorting involved?

---

## ✅ GOOD PROMPTS

### Example 1: Clear and specific
```
"Create a test for successful user login with valid credentials (username: testuser, password: Test123!).
After login, verify the user is redirected to the dashboard and see the welcome message.
Include validation for error message when password is wrong.
Use data-testid attributes where available."
```
**Why it's good:**
- ✅ Specifies exact test data
- ✅ Defines success criteria
- ✅ Includes negative test case
- ✅ Mentions selector strategy preference

### Example 2: With page context
```
"Test the car insurance policy update vehicle flow:
1. Navigate to policy details page
2. Click 'Change Vehicle' button
3. Enter registration number: AB12CDE
4. Verify vehicle lookup populates vehicle details
5. Update owner name field
6. Update vehicle age field
7. Save and verify success message
Include validation for invalid registration format and empty required fields."
```
**Why it's good:**
- ✅ Step-by-step flow
- ✅ Specific UI elements mentioned
- ✅ Includes validation scenarios
- ✅ Clear success criteria

### Example 3: Edge cases included
```
"Create a test for form submission with validation:
- Valid form submission with all required fields
- Empty required field validation (show error on submit)
- Email format validation
- Character length limits on text fields
- Network error handling (simulate API failure)
Wait for loading indicators and use implicit waits where appropriate."
```
**Why it's good:**
- ✅ Multiple test scenarios in one
- ✅ Explicit validation requirements
- ✅ Error handling specified
- ✅ Timing/waiting requirements clear

### Example 4: With additional context
```
"Test the cart update functionality.
Additional context:
- Page URL: /cart
- Key selectors: data-testid='cart-item-quantity', data-testid='cart-total', data-testid='update-btn'
- Items in cart: 2-3 products with varying quantities
- Cart total should update after quantity change
- Show error if quantity exceeds available stock"
```
**Why it's good:**
- ✅ Page context provided
- ✅ Specific selectors given
- ✅ Business rules included
- ✅ Edge cases mentioned

---

## 📋 CHECKLIST FOR GOOD PROMPTS

Before writing your prompt, ensure you include:

| Element | Why it matters |
|---------|----------------|
| **Clear objective** | What specific behavior should be tested? |
| **Test data** | What inputs should be used (valid/invalid)? |
| **Expected outcomes** | What should happen (success, error, redirect)? |
| **UI elements** | Key buttons, inputs, or pages involved |
| **Edge cases** | Validation, error states, loading states |
| **Selector preference** | data-testid, aria-label, or specific strategy |

---

## 🔄 EXAMPLE PROMPT STRUCTURE

```
"[ACTION] on [TARGET] with [DATA] to achieve [EXPECTED OUTCOME].
Include [ADDITIONAL CONCERNS like validation, loading, errors]."

Examples:
- "Click submit on checkout form with valid shipping details to complete purchase.
  Include validation for missing postal code and network failure handling."

- "Enter search term 'laptop' on search page to display results.
  Include empty results handling and loading spinner verification."

- "Update user profile with valid information to save changes.
  Include password strength validation and email duplicate detection."