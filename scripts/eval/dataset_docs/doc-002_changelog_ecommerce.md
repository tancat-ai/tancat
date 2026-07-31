# Change Log — E-Commerce Platform v4.2

**Release date:** 2026-07-20

## New: Product Recommendations Engine

A new ML-based product recommendations engine has been added to the product
detail page. It shows "Customers also bought" suggestions based on purchase
history. This is a new feature powered by a collaborative filtering model.

**Affected systems:** recommendation-service, product-api, analytics-pipeline

## Modified: Shopping Cart Tax Calculation

The tax calculation in the shopping cart has been updated to support
region-specific VAT rates. Previously, a flat 20% was applied to all orders.
Now, the rate is determined by the shipping address region.

**Affected systems:** cart-service, tax-engine

**Schema changes:**
- `tax_rates.region`: NEW field, VARCHAR(50)
- `tax_rates.rate`: MODIFIED — was DECIMAL(3,2), now DECIMAL(5,4)

## Modified: Order Confirmation Email

The order confirmation email template has been redesigned to include product
images and a link to track the shipment. The email service integration remains
unchanged.

**Affected systems:** email-service

## Unchanged: Payment Gateway Integration

The payment gateway integration (Stripe) remains unchanged. No modifications
to the payment flow, webhook handling, or refund processing.

**Affected systems:** none
