# Web keyboard, accessibility-tree and zoom review

This focused review supplements the broad screen/axe scans and accounting journeys. It uses disposable local accounts and companies through `tests/e2e/run_local.py`; it does not modify the desktop preview's records or a user's browser profile.

## Defects corrected

- Search no longer activates a hidden suggestion after Escape or opens behind a modal with Ctrl+K. Suggestions preserve combobox focus and do not create extra Tab stops.
- The Create menu records its actual trigger for Arrow-key opening and restores it when dismissed or after an editor closes.
- Nested dialogs restore the editor field that opened the confirmation, with disabled controls excluded from the focus loop. The foreground dialog's background is inert in Chromium's actual accessibility tree.
- Adding/removing invoice items and payment allocations leaves focus on a relevant surviving field. Allocation groups and remove controls identify their document number.
- Invoice validation, payment-term loading failures, and report failures are announced as alerts.
- Party/item dialogs identify their task. Dirty-close focuses Keep editing, which restores the previous field; Escape cancels the inline discard prompt.
- Settings tabs always reference an existing panel, while unvisited content remains deferred. Section jumps move keyboard focus and respect reduced motion. No-match search results are announced.
- Mobile ageing and other report card layouts preserve accessible column headers.
- At real 400% browser zoom, the scrollbar reduced the usable width below 320 CSS pixels. Removing the hard page minimum width prevents horizontal overflow. At short viewport heights, invoice headings/actions scroll with the form so focused fields remain visible.
- Cancelled documents are excluded from original-document choices for returns and payments.

## Reproducible focused check

```powershell
$env:APEX_ZOOM_BROWSER_CHANNEL = 'chrome'
& .venv/Scripts/python.exe tests/e2e/run_local.py --browser-only --accessibility --artifacts tmp/accessibility-review
```

`--browser-engine webkit` or `--browser-engine firefox` selects the shared browser harness for the keyboard/reflow checks. The optional actual-zoom pass uses a locally installed Chrome or Edge channel with a fresh temporary profile. It measures `devicePixelRatio` and the resulting CSS viewport; it does not substitute CSS transforms for browser zoom or change host display settings.

The suite checks skip navigation; combobox behavior; Create menu arrows/Home/End/Escape; modal isolation and nested restoration; invoice and allocation row focus; validation errors; master-entry dirty close; settings keyboard navigation and section focus; reduced motion; report errors; mobile table relations; and short-height 640/320 CSS-pixel invoice reflow. Every captured state is checked for horizontal page overflow and WCAG 2 A/AA and 2.1 AA axe violations.

## Evidence and scope

- `tmp/accessibility-accepted-final/accessibility-deep/result.json`: 22 focused checks, 18 captures, no uncaught JavaScript errors; all captures have zero axe violations. The subsequent master discard-focus refinement is covered separately by `tmp/accessibility-focus-final/accessibility-deep/result.json`.
- Actual Chrome 200%: 631 × 432 CSS pixels, DPR 2. Actual 400%: 315 × 216 CSS pixels, DPR 4. Dashboard, reports, settings and invoice captured at both zooms. The customer and item-rate inputs are asserted fully inside the viewport and unobscured by overlays after focus.
- Each captured state includes a screenshot and Playwright role snapshot. Chromium also records `Accessibility.getFullAXTree` with ignored nodes excluded, and asserts modal background search is absent. A DOM role snapshot alone is not treated as proof of browser accessibility-tree isolation.
- A Playwright trace is retained for the keyboard sequence. Browser test databases, owned servers, and temporary zoom profiles are removed by the runner.

These results establish the exercised keyboard, semantic and zoom behavior. They are not a claim that every assistive technology/browser combination has been tested. This suite does not perform spoken screen-reader acceptance; the separate NVDA review records that coverage. The parent review records final cross-engine and business-journey results.
