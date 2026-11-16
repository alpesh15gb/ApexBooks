"""Verify the compiled Flutter web client against a fresh disposable API."""

import argparse
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import tempfile
import threading
import time
from urllib.request import Request, urlopen

from playwright.sync_api import expect, sync_playwright

from serve_preview import preview_server


ROOT = Path(__file__).resolve().parents[3]
WEB = ROOT / "native" / "flutter" / "build" / "web"
CREDENTIALS = {
    "email": "flutter-clerk@example.invalid",
    "password": "Synthetic store password 42",
}


def api(base, path, body=None, token=None, key=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if key:
        headers["Idempotency-Key"] = key
    request = Request(
        base + path,
        json.dumps(body).encode() if body is not None else None,
        headers,
    )
    with urlopen(request, timeout=15) as reply:
        return json.load(reply)


@contextmanager
def disposable_api(artifacts):
    backend = ROOT / "backend"
    with tempfile.TemporaryDirectory(prefix="apex-flutter-web-") as scratch:
        db = Path(scratch, "books.db")
        env = {
            key: value for key, value in os.environ.items()
            if key.upper() not in {
                "OPENAI_API_KEY", "OMNIROUTE_API_KEY", "OMNIROUTE",
                "OCR_BASE_URL", "COMMERCE_ENCRYPTION_KEY",
                "COMMERCE_ALLOWED_HOSTS", "CRON_SECRET",
            }
        }
        env.update(
            DATABASE_URL=f"sqlite:///{db.as_posix()}",
            JWT_SECRET="synthetic-local-flutter-build-smoke-test-secret",
        )
        subprocess.run([sys.executable, "migrate.py"], cwd=backend, env=env, check=True)
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        base = f"http://127.0.0.1:{port}"
        with (artifacts / "api.log").open("w", encoding="utf-8") as log:
            process = subprocess.Popen(
                [sys.executable, "-m", "uvicorn", "main:app",
                 "--host", "127.0.0.1", "--port", str(port)],
                cwd=backend, env=env, stdout=log, stderr=subprocess.STDOUT,
            )
            try:
                for _ in range(100):
                    try:
                        api(base, "/api/ready")
                        break
                    except OSError:
                        if process.poll() is not None:
                            raise RuntimeError("The disposable API stopped. Check api.log.") from None
                        time.sleep(.15)
                else:
                    raise RuntimeError("The disposable API did not become ready.")
                yield base, port
            finally:
                if process.poll() is None:
                    if os.name == "nt":
                        # Windows venv launchers can have a real Python child.
                        subprocess.run(
                            ["taskkill", "/pid", str(process.pid), "/t", "/f"],
                            capture_output=True, check=False,
                        )
                    else:
                        process.terminate()
                    process.wait(timeout=15)


@contextmanager
def web_origin(port):
    with preview_server(WEB, port) as web:
        thread = threading.Thread(target=web.serve_forever, daemon=True)
        thread.start()
        try:
            yield f"http://127.0.0.1:{web.server_port}"
        finally:
            web.shutdown()
            thread.join(timeout=10)


def seed(base):
    api(base, "/api/auth/register", CREDENTIALS)
    token = api(base, "/api/auth/login", CREDENTIALS)["token"]
    company = api(base, "/api/companies", {
        "name": "Apex Corner Store", "state_code": "27", "tax_mode": "unregistered",
    }, token=token)
    prefix = "/api/companies/" + company["id"]
    day = datetime.now(timezone(timedelta(hours=5, minutes=30))).date().isoformat()
    item = api(base, prefix + "/records", {
        "kind": "item", "name": "Counter cable", "date": day,
        "data": {
            "barcode": "00123456", "track_stock": True, "unit": "pcs",
            "sale_rate": "120", "purchase_rate": "50",
        },
    }, token=token, key="flutter-qa-item")
    api(base, prefix + "/records", {
        "kind": "party", "name": "Store Opening Customer", "date": day,
        "data": {"party_type": "customer"},
    }, token=token, key="flutter-qa-party")
    api(base, prefix + "/stock/opening", {
        "date": day, "item_id": item["id"], "quantity": "8", "unit_cost": "50",
    }, token=token, key="flutter-qa-stock")
    for name, barcode, rate, quantity in (
        ("Packing tape", "00482190", "48", "24"),
        ("Receipt roll 80 mm", "00981008", "72", "18"),
        ("Counter label pack", "00245817", "95", "12"),
    ):
        product = api(base, prefix + "/records", {
            "kind": "item", "name": name, "date": day,
            "data": {"barcode": barcode, "track_stock": True,
                     "unit": "pcs", "sale_rate": rate, "purchase_rate": "20"},
        }, token=token, key=f"flutter-layout-{barcode}")
        api(base, prefix + "/stock/opening", {
            "date": day, "item_id": product["id"], "quantity": quantity, "unit_cost": "20",
        }, token=token, key=f"flutter-layout-stock-{barcode}")
    api(base, prefix + "/records", {
        "kind": "purchase_order", "name": "Harbor Supply", "date": day,
        "data": {"lines": [{"description": "Counter cable", "item_id": item["id"],
                            "quantity": "5", "unit": "pcs", "rate": "50"}]},
    }, token=token, key="flutter-layout-order")
    return prefix, token


def cashier(page, web, base, prefix, token, artifacts):
    page.goto(web)

    def enable_semantics():
        marker = page.locator("flt-semantics-placeholder")
        email = page.get_by_role("textbox", name="Email address", exact=True)
        marker.or_(email).first.wait_for(state="attached", timeout=35000)
        if marker.count():
            marker.evaluate(
                "(el) => el.dispatchEvent(new MouseEvent('click', { bubbles: true, detail: 1 }))"
            )
        expect(email).to_be_visible()

    def click(name):
        page.get_by_role("button", name=name, exact=True).click()

    def enter(name, text, *, replace=False, exact=True):
        page.get_by_role("textbox", name=name, exact=exact).click()
        page.wait_for_timeout(120)
        if replace:
            page.keyboard.press("Control+A")
        page.keyboard.type(text, delay=10)

    def choose(name):
        label = re.compile(rf"^{re.escape(name)}$")
        candidates = page.get_by_label(label).or_(page.get_by_text(label))
        candidates.first.click(timeout=4500)

    def sign_in():
        enter("Email address", CREDENTIALS["email"])
        # The visibility control exercises the same password controller while
        # allowing browser typing to synchronize with Flutter's editing host.
        click("Show password")
        enter("Password", CREDENTIALS["password"])
        click("Sign in")
        expect(page.get_by_role("button", name="Open checkout")).to_be_visible(timeout=15000)

    enable_semantics()
    page.screenshot(path=artifacts / "flutter-sign-in.png")
    sign_in()
    page.screenshot(path=artifacts / "flutter-home-wide.png")
    page.keyboard.press("Control+k")
    workspace_search = page.get_by_role("textbox", name="Find a workspace", exact=True)
    expect(workspace_search).to_be_focused()
    page.keyboard.type("inventory", delay=10)
    page.keyboard.press("Enter")
    expect(page.get_by_text("Packing tape", exact=False).first).to_be_visible()
    page.screenshot(path=artifacts / "flutter-stock-wide.png", animations="disabled")
    page.set_viewport_size({"width": 390, "height": 844})
    expect(page.get_by_role("tab", name="Stock", exact=True)).to_be_visible()
    expect(page.get_by_text("Packing tape", exact=False).first).to_be_visible()
    page.screenshot(path=artifacts / "flutter-stock-mobile.png", animations="disabled")
    page.set_viewport_size({"width": 1280, "height": 900})
    page.get_by_role("tab", name="Purchase orders", exact=True).click()
    orders = api(base, prefix + "/records?kind=purchase_order", token=token)
    assert len(orders) == 1, orders
    page.get_by_role("button", name=orders[0]["number"], exact=False).click()
    click("Receive items")
    expect(page.get_by_role("button", name="Review supplier bill", exact=True)).to_be_visible()
    page.screenshot(path=artifacts / "flutter-receiving-wide.png", animations="disabled")
    page.set_viewport_size({"width": 390, "height": 844})
    expect(page.get_by_text(orders[0]["number"], exact=False).first).to_be_visible()
    expect(page.get_by_role("button", name="Review supplier bill", exact=True)).to_be_visible()
    page.screenshot(path=artifacts / "flutter-receiving-mobile.png", animations="disabled")
    page.set_viewport_size({"width": 1280, "height": 900})
    click("Back")
    page.get_by_role("tab", name="POS", exact=True).click()
    click("Register")
    enter("Opening cash (₹)", "50")
    click("Open register")
    expect(page.get_by_role("button", name="Count & close register")).to_be_visible()
    click("Checkout")
    enter("Scan barcode or search", "00123456")
    page.keyboard.press("Enter")
    enter("Cash received (₹)", "150")
    pay = page.get_by_role("button", name="Complete sale", exact=True)
    expect(pay).to_be_enabled()
    # Flutter paints this enabled-state transition on the canvas.
    page.wait_for_timeout(240)
    page.screenshot(path=artifacts / "flutter-checkout-wide.png", animations="disabled")
    page.set_viewport_size({"width": 390, "height": 844})
    expect(page.get_by_role("tab", name="POS", exact=True)).to_be_visible()
    expect(page.get_by_role("textbox", name="Scan barcode or search", exact=True)).to_be_visible()
    expect(page.get_by_role("button", name="Go to payment", exact=True)).to_be_visible()
    page.screenshot(path=artifacts / "flutter-checkout-mobile.png", animations="disabled")
    click("Go to payment")
    expect(pay).to_be_in_viewport(ratio=1)
    expect(pay).to_be_enabled()
    page.screenshot(path=artifacts / "flutter-checkout-payment-mobile.png", animations="disabled")
    page.set_viewport_size({"width": 1280, "height": 900})
    expect(pay).to_be_enabled()

    def lose_reply(route):
        if route.request.method == "POST":
            assert route.fetch().ok, "The sale did not reach the disposable API."
            route.abort("failed")
        else:
            route.continue_()

    sale_url = f"**{prefix}/records"
    page.route(sale_url, lose_reply)
    pay.click()
    retry = page.get_by_role("button", name="Retry original sale", exact=True)
    expect(retry).to_be_visible(timeout=15000)
    page.unroute(sale_url)
    page.reload()
    enable_semantics()
    sign_in()
    click("Open checkout")
    retry.click()
    receipt = page.get_by_role("button", name="View receipt", exact=True)
    expect(receipt).to_be_visible(timeout=15000)
    receipt.click()
    rows = api(base, prefix + "/records?kind=pos", token=token)
    assert len(rows) == 1 and Decimal(rows[0]["amount"]) == 120, rows
    assert Decimal(rows[0]["data"]["change_amount"]) == 30, rows
    page.screenshot(path=artifacts / "flutter-posted-receipt.png")
    page.set_viewport_size({"width": 390, "height": 844})
    expect(page.get_by_text(rows[0]["number"], exact=False).first).to_be_visible()
    page.screenshot(path=artifacts / "flutter-receipt-mobile.png")
    page.set_viewport_size({"width": 1280, "height": 900})
    for width, pdf_width in ((58, b"164.409"), (80, b"226.771")):
        page.get_by_role("button", name=re.compile(r"^Save receipt PDF")).click()
        with page.expect_download() as saved:
            choose(f"Save {width} mm PDF")
        path = artifacts / f"flutter-thermal-{width}mm.pdf"
        saved.value.save_as(path)
        pdf = path.read_bytes()
        assert pdf.startswith(b"%PDF-") and b"/MediaBox" in pdf and pdf_width in pdf
    click("Register")
    click("Count & close register")
    enter("Counted cash (₹)", "168")
    enter("Reason (required)", "Confirmed two rupees short")
    click("Post closing count")
    expect(page.get_by_role("button", name="Open register")).to_be_visible()
    reconciliation = api(base, prefix + "/pos-register", token=token)
    assert reconciliation["active"] is None, reconciliation
    closed = reconciliation["closed"][0]["data"]
    assert Decimal(closed["closed_totals"]["expected_cash"]) == 170, closed
    assert Decimal(closed["counted_cash"]) == 168 and Decimal(closed["variance"]) == -2, closed
    page.screenshot(path=artifacts / "flutter-register-close.png")

    enter("Opening cash (₹)", "200")
    click("Open register")
    expect(page.get_by_role("button", name="Count & close register")).to_be_visible()
    click("Receipts")
    page.get_by_text(rows[0]["number"], exact=False).first.click()
    click("Return items")
    enter("Return quantity for Counter cable (line 1)", "1")
    click("Settlement Keep as customer credit")
    choose("Cash refund")
    expect(page.get_by_text("Return total ₹120.00", exact=True).first).to_be_visible()
    page.get_by_role("checkbox", name="I handed this cash refund to the customer.").click()
    click("Post return")
    expect(page.get_by_text("Return posted", exact=True).first).to_be_visible()
    returns = api(base, prefix + "/records?kind=credit_note", token=token)
    assert len(returns) == 1 and Decimal(returns[0]["amount"]) == 120, returns
    refunds = api(base, prefix + "/records?kind=customer_refund", token=token)
    assert len(refunds) == 1 and Decimal(refunds[0]["amount"]) == 120, refunds
    assert refunds[0]["data"]["credit_note_id"] == returns[0]["id"], refunds
    page.screenshot(path=artifacts / "flutter-return-posted.png")

    click("New transaction")
    choose("Sales invoice")
    expect(page.get_by_role("textbox", name="Customer name", exact=True)).to_be_visible()
    page.screenshot(path=artifacts / "flutter-invoice-editor-wide.png", animations="disabled")
    page.set_viewport_size({"width": 390, "height": 844})
    expect(page.get_by_role("tab", name="Books", exact=True)).to_be_visible()
    expect(page.get_by_role("textbox", name="Customer name", exact=True)).to_be_visible()
    page.screenshot(path=artifacts / "flutter-invoice-editor-mobile.png", animations="disabled")
    page.set_viewport_size({"width": 1280, "height": 900})
    enter("Customer name", "Taylor Corner")
    enter("Description", "Counter installation")
    enter("Unit rate (₹)", "78.25", replace=True)
    click("Review entry")
    expect(page.get_by_role("button", name="Post entry", exact=True)).to_be_enabled()
    page.screenshot(path=artifacts / "flutter-invoice-review.png")
    with page.expect_response(lambda reply: reply.url.endswith(prefix + "/records") and reply.request.method == "POST") as posted:
        click("Post entry")
    assert posted.value.ok, posted.value.status
    expect(page.get_by_role("button", name="Record receipt", exact=True)).to_be_visible()
    expect(page.get_by_text("Taylor Corner", exact=False).first).to_be_visible()
    invoices = api(base, prefix + "/records?kind=sales_invoice", token=token)
    assert len(invoices) == 1 and Decimal(invoices[0]["amount"]) == Decimal("78.25"), invoices
    page.screenshot(path=artifacts / "flutter-invoice-posted.png")
    page.set_viewport_size({"width": 390, "height": 844})
    expect(page.get_by_role("tab", name="Books", exact=True)).to_be_visible()
    expect(page.get_by_role("button", name="Record receipt", exact=True)).to_be_visible()
    page.screenshot(path=artifacts / "flutter-invoice-detail-mobile.png", animations="disabled")
    page.set_viewport_size({"width": 1280, "height": 900})

    page.get_by_role("tab", name="Reports", exact=True).click()
    enter("Find a report", "Sales register")
    page.get_by_text("Sales register", exact=False).filter(visible=True).last.click()
    expect(page.get_by_text(invoices[0]["number"], exact=False).first).to_be_visible()
    page.screenshot(path=artifacts / "flutter-sales-report.png")
    print("Flutter web passed: register, barcode, exact sale replay, 58 mm and 80 mm PDFs, cash reconciliation, cash return, reviewed invoice posting and sales reporting.")

    page.get_by_role("tab", name="Settings", exact=True).click()
    page.get_by_text("Opening party balances", exact=False).first.click()
    click("Choose a party")
    page.get_by_text("Store Opening Customer", exact=False).last.click()
    enter("Opening amount (₹)", "49.25")
    click("Post opening balance")
    confirmation = page.get_by_role("group", name=re.compile(r"^Opening balance posted to the ledger\."))
    expect(confirmation).to_be_visible()
    openings = api(base, prefix + "/records?kind=opening_receivable", token=token)
    assert len(openings) == 1 and Decimal(openings[0]["amount"]) == Decimal("49.25"), openings

    click("All settings")
    page.get_by_text("Backup & data", exact=False).first.click()
    page.get_by_role("checkbox", name="I am saving an unencrypted file containing company data.").click()
    with page.expect_download() as saved:
        click("Save complete ZIP")
    backup = artifacts / "flutter-company-backup.zip"
    saved.value.save_as(backup)
    assert backup.read_bytes().startswith(b"PK\x03\x04")
    enter("New company name", "Apex Restored Corner Store", exact=False)
    with page.expect_file_chooser() as picked:
        click("Choose backup")
    picked.value.set_files(backup)
    click("Validate backup")
    restore = page.get_by_role("button", name="Restore this backup", exact=True)
    expect(restore).to_be_enabled()
    page.screenshot(path=artifacts / "flutter-restore-preview.png")
    with page.expect_response(lambda reply: "/api/backups/uploads/" in reply.url and reply.url.endswith("/commit")) as committed:
        restore.click()
    assert committed.value.ok, committed.value.status
    expect(page.get_by_role("button", name="Company and account Apex Restored Corner Store")).to_be_visible()
    companies = api(base, "/api/companies", token=token)
    restored = next(company for company in companies if company["name"] == "Apex Restored Corner Store")
    restored_book = f"/api/companies/{restored['id']}"
    assert len(api(base, restored_book + "/records?kind=sales_invoice", token=token)) == 1
    assert len(api(base, restored_book + "/records?kind=opening_receivable", token=token)) == 1
    page.screenshot(path=artifacts / "flutter-restored-company.png")
    print("Flutter web passed: opening party balance and verified complete ZIP export and restore into a separate company.")

    page.set_viewport_size({"width": 320, "height": 740})
    expect(page.get_by_role("tab", name="Home", exact=True)).to_be_visible()
    brand = page.get_by_text("Apex Books", exact=True).or_(page.get_by_label("Apex Books", exact=True))
    expect(brand.first).to_be_in_viewport(ratio=1)
    expect(page.get_by_role("button", name="Company and account Apex Restored Corner Store")).to_be_visible()
    page.screenshot(path=artifacts / "flutter-brand-320.png", animations="disabled")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--browser-executable", type=Path)
    parser.add_argument("--artifacts", type=Path, required=True)
    args = parser.parse_args()
    if not (WEB / "index.html").exists():
        parser.error("Build the Flutter web client first.")
    artifacts = args.artifacts.resolve()
    artifacts.mkdir(parents=True, exist_ok=True)
    with disposable_api(artifacts) as (base, port), web_origin(port) as web:
        prefix, token = seed(base)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                executable_path=args.browser_executable,
                args=["--enable-unsafe-swiftshader"],
            )
            try:
                page = browser.new_page(viewport={"width": 1280, "height": 900})
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                console_errors = []
                page.on("console", lambda message: console_errors.append(message.text)
                        if message.type == "error" else None)
                try:
                    cashier(page, web, base, prefix, token, artifacts)
                except Exception:
                    page.screenshot(path=artifacts / "flutter-smoke-failure.png")
                    (artifacts / "flutter-smoke-failure.aria").write_text(
                        page.locator("body").aria_snapshot(), encoding="utf-8"
                    )
                    (artifacts / "flutter-smoke-failure-console.log").write_text(
                        "\n".join([*errors, *console_errors]), encoding="utf-8"
                    )
                    raise
                assert not errors, errors
            finally:
                browser.close()


if __name__ == "__main__":
    main()
