# Storefront POS and inventory

The web counter supports one store inventory pool. It records cash and externally confirmed bank, UPI and card payments, including a mixed cash and bank payment. Use a named receiving account so settlement can be matched to the corresponding statement. The payment terminal and the bank remain responsible for moving funds.

Web and Windows keep the catalogue and current sale together on wider screens. Android offers separate Products and Cart views with a payable total near the primary action. All three confirm electronic tender before recording it. Use the web Register view to manage the shared drawer. Native checkouts enter the active session automatically when it is open.

**Start at Home.** POS is a top-level destination on web, Windows and Android. The workspace shortcuts put checkout and stock work within reach before going into the accounting registers. Use **Receive stock** on the web dashboard to find the supplier's purchase order. Web receipt lookup searches all dates by default; use **Show today** for the current shift, or choose a sale date.

## Store workflow

| Task | ApexBooks workflow |
| --- | --- |
| Set up the catalogue | Create items with unique barcodes, sale prices, tax treatment and stock tracking. Enter opening stock at cost for existing goods. |
| Receive supplier stock | Open a purchase order and choose **Receiving** or **Receive items**. Enter the delivery quantities, review the bill rate and total, and post the supplier bill. Web also exposes supplier tax and discount overrides. Each bill preserves the unreceived order balance for the next delivery. |
| Open the counter | Start the shared register session and record the opening float. Record cash additions and drops as they happen. |
| Scan and sell | Scan an exact barcode into POS, review quantities and total, record tender and change, then print or download the confirmed receipt. Hold a cart to serve another customer. Held carts are kept in the current browser tab while navigating and do not reserve stock. |
| Recover a checkout | If the result is uncertain, retry from the same tab. POS retains the original request and key across a tab reload. The pending request can contain the billing details entered for that sale. Use the same company and cashier sign-in and complete recovery before initiating another payment. |
| Return an item | In the web receipt history, find the original sale, select quantities, review the return total, choose whether to restock, and retain credit or record a refund. Keep the credit note and refund voucher with the original receipt reference. Reverse a mistaken recorded refund from its detail while the linked register is open and the accounting period is unlocked. |
| Close the drawer | Compare expected and counted cash, record the variance, and close the shared register. Use daily reconciliation to review company-wide sales and linked refunds by tender and export a cash count. |
| Count stock | From Items, select **Count or adjust stock** on web or **Count stock** on Windows or Android. Scan or select tracked goods, enter the physical quantity and review the adjustment. If a sale or receipt changed the item after its count started, refresh and recount. Drill into an item’s stock movements in the web Tracked stock report. |

## Product research

- Zoho POS documents register sessions, cash in/out, expected-versus-counted cash, and branch warehouse assignment. ApexBooks uses a company-wide register and a single inventory pool. [Zoho POS sessions](https://www.zoho.com/en-in/pos/retail/resources/help/sessions.html) · [Zoho POS branches](https://www.zoho.com/en-in/pos/retail/resources/help/branches.html)
- Shopify POS documents receipt-linked partial refunds and restocking, with separate permissions for POS staff. ApexBooks links returns to the receipt and enforces remaining quantities, using its existing owner/editor roles. [Shopify POS refunds](https://help.shopify.com/en/manual/sell-in-person/shopify-pos/order-management/complete-refund-orders) · [Shopify POS permissions](https://help.shopify.com/en/manual/your-account/users/roles/permissions/pos-permissions)
- Square for Retail documents partial PO receipts, stock counts and staged transfers. ApexBooks tracks received and remaining order quantities against posted bills, plus physical stock counts and item movement history. [Square purchase orders](https://squareup.com/help/us/en/article/8258-create-purchase-orders-with-square-for-retail) · [Square inventory counts](https://squareup.com/help/us/en/article/8249-conduct-full-inventory-counts-with-square-for-retail) · [Square transfer orders](https://squareup.com/help/us/en/article/8300-create-transfer-orders-with-square-for-retail)
- Lightspeed documents opening floats, cash drops and register close. Odoo documents barcode scanner, receipt printer and cash-drawer integrations. Browser printing and keyboard-wedge scanner input still need to be tested with the store’s devices. [Lightspeed register guide](https://retail-support.lightspeedhq.com/hc/en-us/articles/1260800790810-Opening-and-closing-a-register) · [Odoo POS hardware](https://www.odoo.com/documentation/19.0/applications/sales/point_of_sale/pos_hardware.html)
- Shopify puts frequent cashier actions on its POS smart grid and supports order search and filtering from the counter. QuickBooks keeps workspace shortcuts and financial performance visible on the dashboard. These informed the placement of checkout and warehouse shortcuts and the separation of financial controls. [Shopify smart grid](https://help.shopify.com/en/manual/sell-in-person/getting-started/smart-grid) · [Shopify order search](https://help.shopify.com/en/manual/sell-in-person/shopify-pos/order-management/search-orders) · [QuickBooks navigation and dashboard](https://quickbooks.intuit.com/learn-support/en-us/help-article/product-setup/navigate-quickbooks-online-menus-transactions-set/L5eM9dp7W_US_en_US)

## Customer-site acceptance

Before opening, reconcile imported SKUs and opening quantities, confirm the tax profile and receipt numbering, and exercise a sale, partial return, receiving bill and close using the actual scanner, thermal printer, cash drawer and merchant terminal. Check a network interruption after recording payment and keep the till out of service until the prior request is resolved.

The update uses the existing database schema. Rehearse backup and restore with the new register and purchase receipt links before deployment. The production recovery plan needs to account for the validation rules introduced with those records.

Independent till sessions, separate warehouse and bin balances, transfer-in-transit, batches and expiry, integrated terminal settlement, offline final posting and cashier-specific approvals require additional support.

Run the browser storefront journey against disposable books with `python tests/e2e/run_local.py --browser-only --storefront`. The suite creates its own API and database and exercises scanning, held sales, stock checks, split payment, interrupted checkout recovery, a return, reconciliation, a physical count and two deliveries against a purchase order.
