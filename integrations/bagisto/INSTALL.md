# Apex Books / Bagisto integration handoff

Public Bagisto and storefront hosting is deferred. The tested local setup uses Bagisto 2.5.0, the pinned `bagisto/bagisto-api` v2.4.4 source, PHP 8.4/Laravel 13, PostgreSQL, ApexBridge and the included Next.js storefront.

## Per-company setup

1. Create a draft Ecommerce connection inside the intended Apex company. Choose one unique Bagisto channel and one exclusive active inventory source. Use a strong connection secret; keep it on the servers. Each company has its own connection identity and secret.
2. Copy `ApexBridge` into `packages/ApexBridge` in the tested Bagisto base. Register its PSR-4 namespace and `ApexBooks\Bridge\BridgeServiceProvider`. The public `runtime/composer.json` and `runtime/composer.lock` snapshots capture the tested dependency/security refinements; review their differences when applying them to a store with other extensions.
3. Configure `APEX_BRIDGE_CONNECTIONS` server-side. Key its JSON object by the Apex connection UUID. Each value supplies `secret`, `apex_url`, `channel`, `inventory_source_id`, `company_state_code`, reviewed `shipping_line` GST/HSN details and the eventual `storefront_url`. Do not place this JSON in web assets or native clients.
4. Use INR globally and for the channel. Configure GST-exclusive product and shipping prices. The bridge rejects incompatible pricing, shared inventory sources, overlapping company/channel identities and shared global-price products.
5. Run the versioned bridge/API compatibility migrations, then activate/test the connection. Review SKU mappings and opening quantity/cost before publishing. Apex owns accounting, available stock, base prices and GST; website copy, media and categories remain website-owned. Price/GST publication is an explicit owner action; stock projections and source transaction events are queued.
6. Run `php artisan apex:deliver --once` on a regular schedule or as its supervised delivery loop. Run the Apex commerce worker (Docker `commerce` profile) or the configured protected Vercel drain cron. Preserve retry/review queues and source identities; never reset them to force a posting.

One Next.js deployment serves one selected connection/channel. Use separate deployment configuration for another company's store. Accounting authorization, connection identity, channel and inventory ownership are all checked server-side.

## Next.js configuration

Copy `.env.example` to a private local/server environment file and configure the public Bagisto HTTPS origin, server-only storefront API key, `BAGISTO_CHANNEL`, locale and the matching `APEX_CONNECTION_ID`. Never expose API credentials through `NEXT_PUBLIC_` variables.

`APEX_STOREFRONT_WEBHOOK_SECRET` must equal the bridge's derived HMAC key, rather than an unrelated random value:

```php
hash_hmac('sha256', 'apex-storefront-invalidation:'.$connectionId, $connectionSecret)
```

The derived key differs from the connection secret. Signed invalidations check timestamp, exact body, connection and channel; callers cannot supply cache paths or tags. Configure a public HTTPS `storefront_url` when hosting is enabled. Local HTTP origins are limited to the isolated local/testing profile.

Run `npm ci`, `npm run build`, then `npm start`. The tested security-refined lock resolves Next.js 16.4.3 and sharp 0.35.5. Guest checkout supports an optional validated GSTIN, keeps it after address reload/edit, normalizes India to IN, uses INR shipping labels and shows authoritative GST and discounts separately.

Run `node --test tests/guest-cart-session.cjs` for the cart-capability regression checks. When upstream replaces an inactive guest cart during add-to-cart, the client adopts its returned token before checkout requests. A completed guest order clears the old identity synchronously before navigation; signed-in customer identities are preserved.

Before public launch, replace the upstream seeded CMS policies and marketing badges with the store's actual delivery, payment, support and return terms. Checkout and confirmation pages omit those promotional badges and show the actual order charges instead.

## Financial operation

Orders and reservations precede financial invoices. Apex is the accounting invoice authority. Captures, cash refunds, credit notes, physical stock returns and settlement bank/fee entries are distinct events. Manual verified-source actions require a source reference and confirmation; they do not themselves move money through a payment provider. Live payment-provider credentials and external payment delivery have not been exercised in QA.

Review unsupported product/valuation cases instead of guessing. Use concrete supported stock SKUs for variants. Exports, bundles/grouped/booking products, complex multi-invoice refund allocation and supplier GST on gateway fees need separate review. Company-only portable backups omit live commerce credentials/queues; use full database and encryption-key recovery for operational connections.

## Security and evidence

The patched Bagisto Composer audit reports zero advisories. The SVG sanitizer moved to the upstream patched 1.0 series; see [the upstream advisory](https://github.com/advisories/GHSA-9rjx-3jch-6vjf). Accounting web production dependencies and the API requirement resolution also audit clean.

Next.js production audit has zero critical/high advisories. One remaining low-severity `deepmerge` advisory appears through 53 HeroUI dependency paths; a broad HeroUI 3 migration is not included in this adapter update. Review that dependency before the deferred public-storefront launch. Current source uses application-defined theme configuration.

See `RELEASE_1_3_ACCEPTANCE.md`, the financial reconciliation reports, source delivery summaries and the checkout UI evidence under `tmp/release-1.3`. Those QA files are not public deployment inputs. Environment files, signing identities and private test state are excluded from the handoff packages.
