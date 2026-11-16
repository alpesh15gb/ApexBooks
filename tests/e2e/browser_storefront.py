"""Storefront acceptance against the disposable API owned by run_local.py."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
import os
from uuid import uuid4

from playwright.sync_api import expect, sync_playwright

from browser_support import launch_browser
from test_http_workflow import BASE, LiveAccountingWorkflow


api = LiveAccountingWorkflow()
credentials = {'email': f'counter-{uuid4().hex}@example.invalid', 'password': 'Synthetic-counter-only-42'}
api.request('POST', '/api/auth/register', credentials)
api.token = api.request('POST', '/api/auth/login', credentials)['token']
company = api.request('POST', '/api/companies', {'name': 'Synthetic Counter', 'tax_mode': 'unregistered', 'state_code': '27'})
root = '/api/companies/' + company['id']
day = datetime.now(timezone(timedelta(hours=5, minutes=30))).date().isoformat()
item = api.request('POST', root + '/records', {
    'kind': 'item', 'name': 'Counter cable', 'date': day,
    'data': {'barcode': '00123456', 'track_stock': True, 'unit': 'pcs', 'sale_rate': '100', 'purchase_rate': '50'},
}, key=uuid4().hex)
bank = api.request('POST', root + '/bank-accounts', {'name': 'Counter merchant clearing'}, status=201)
api.request('POST', root + '/stock/opening', {
    'date': day, 'item_id': item['id'], 'quantity': '3', 'unit_cost': '50',
}, status=201, key=uuid4().hex)

artifacts = os.environ.get('APEX_E2E_ARTIFACTS')


def capture(page, name):
    if artifacts:
        # Start at the top so fixed navigation is rendered in its normal position.
        page.evaluate('window.scrollTo({top: 0, behavior: "instant"})')
        page.screenshot(path=Path(artifacts) / name, full_page=True, caret='hide')


with sync_playwright() as playwright:
    browser = launch_browser(playwright)
    context = browser.new_context(viewport={'width': 1280, 'height': 900}, accept_downloads=True)
    page = context.new_page()
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.on('console', lambda message: errors.append(message.text) if 'workspace could not render' in message.text else None)
    page.set_default_timeout(15000)
    page.goto(BASE, wait_until='domcontentloaded')
    page.get_by_label('Email address', exact=True).fill(credentials['email'])
    page.get_by_label('Password', exact=True).fill(credentials['password'])
    page.get_by_role('button', name='Sign in', exact=True).click()
    expect(page.get_by_role('status').filter(has_text='Company data loaded')).to_be_visible()
    nav = page.locator('.sidebar')
    page.get_by_role('button', name='Manage stock', exact=False).click()
    expect(page.get_by_role('heading', name='Items', exact=True)).to_be_visible()
    nav.get_by_role('button', name='Dashboard', exact=True).click()
    page.get_by_role('button', name='Open checkout', exact=True).click()
    expect(page.get_by_role('heading', name='Point of sale', exact=True)).to_be_visible()
    nav.get_by_role('button', name='POS', exact=True).click()
    page.get_by_role('button', name='Register', exact=True).click()
    drawer = page.get_by_role('region', name='POS register session', exact=True)
    drawer.get_by_label('Opening float (₹)', exact=True).fill('50')
    drawer.get_by_role('button', name='Open register', exact=True).click()
    expect(drawer.locator('.pos-register-status')).to_have_text('Open')
    drawer.get_by_label('Movement', exact=True).select_option('out')
    drawer.get_by_label('Amount (₹)', exact=True).fill('2.50')
    drawer.get_by_label('Reason', exact=True).fill('Safe drop')
    drawer.get_by_role('button', name='Record cash movement', exact=True).click()
    expect(drawer.get_by_text('₹47.50', exact=True)).to_be_visible()
    page.get_by_role('button', name='Checkout', exact=True).click()
    scanner = page.get_by_label('Search POS items or scan barcode')
    expect(scanner).to_be_enabled()
    scanner.fill('123456')
    scanner.press('Enter')
    expect(page.get_by_text('No exact barcode or name match.', exact=False)).to_be_visible()
    expect(page.locator('.line-card')).to_have_count(0)
    scanner.fill('00123456')
    scanner.press('Enter')
    scanner.fill('00123456')
    scanner.press('Enter')
    expect(page.get_by_label('Quantity for Counter cable')).to_have_value('2')
    page.get_by_role('button', name='Hold sale', exact=True).click()
    expect(page.locator('.line-card')).to_have_count(0)
    page.get_by_role('button', name='Resume', exact=True).click()
    expect(page.get_by_label('Quantity for Counter cable')).to_have_value('2')
    checkout = page.get_by_role('button', name='Complete sale', exact=True)
    page.get_by_label('Quantity for Counter cable').fill('4')
    expect(checkout).to_be_disabled()
    expect(page.get_by_role('button', name='Refresh total', exact=True)).to_be_visible()
    page.get_by_label('Quantity for Counter cable').fill('2')
    expect(checkout).to_be_enabled()
    page.get_by_label('Payment method').select_option('split')
    page.get_by_label('Receiving bank').select_option(bank['id'])
    page.get_by_label('Bank / UPI / card amount (₹)').fill('80')
    page.get_by_label('Cash tendered (₹)').fill('150')
    expect(page.get_by_text('Change ₹30.00', exact=False)).to_be_visible()
    page.get_by_label('Bank, UPI or card payment received', exact=True).check()
    capture(page, 'storefront-split-checkout.png')
    page.set_viewport_size({'width': 390, 'height': 844})
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
    capture(page, 'storefront-split-mobile.png')
    page.set_viewport_size({'width': 1280, 'height': 900})

    def lose_checkout_response(route):
        assert route.fetch().ok
        route.abort()

    page.route('**/api/companies/*/records', lose_checkout_response, times=1)
    checkout.click()
    expect(page.get_by_text('The previous response was not confirmed.', exact=False)).to_be_visible()
    page.once('dialog', lambda dialog: dialog.accept())
    page.reload(wait_until='domcontentloaded')
    expect(page.get_by_text('The previous response was not confirmed.', exact=False)).to_be_visible(timeout=15000)
    page.get_by_role('button', name='Retry sale', exact=True).click()
    expect(page.locator('.pos-receipt')).to_contain_text('Sale completed')
    sales = api.request('GET', root + '/records?kind=pos')
    assert len(sales) == 1, sales
    assert Decimal(sales[0]['data']['cash_amount']) == 120
    assert Decimal(sales[0]['data']['bank_amount']) == 80
    assert Decimal(sales[0]['data']['change_amount']) == 30
    expect(page.get_by_text('Book stock: 1.000', exact=True)).to_be_visible()
    with page.expect_download() as download:
        page.get_by_role('button', name='Download receipt', exact=True).click()
    assert download.value.path().read_bytes().startswith(b'%PDF-')
    page.get_by_role('button', name='Receipts', exact=True).click()
    receipt = page.locator('.pos-history-list li').filter(has_text=sales[0]['number'])
    expect(page.get_by_label('Sale date', exact=True)).to_have_value('')
    page.get_by_label('Sale date', exact=True).fill('2000-01-01')
    expect(receipt).to_have_count(0)
    page.get_by_role('button', name='Show all dates', exact=True).click()
    page.get_by_label('Receipt number or customer', exact=True).fill(sales[0]['number'])
    expect(receipt).to_be_visible()
    receipt.get_by_role('button', name='Start return', exact=True).click()
    dialog = page.get_by_role('dialog', name='Return ' + sales[0]['number'], exact=True)
    dialog.get_by_label('Return quantity for Counter cable (line 1)', exact=True).fill('1')
    dialog.get_by_label('Reason', exact=True).fill('Customer returned a sealed item')
    dialog.get_by_label('Settlement', exact=True).select_option('cash')
    expect(dialog.get_by_text('Return total ₹100.00', exact=True)).to_be_visible()
    dialog.get_by_label('I am recording the cash paid out for this return.', exact=True).check()
    dialog.get_by_role('button', name='Post return', exact=True).click()
    expect(page.get_by_text('Return posted', exact=True)).to_be_visible()
    page.get_by_role('button', name='Register', exact=True).click()
    expect(drawer.get_by_text('₹67.50', exact=True)).to_be_visible()
    drawer.get_by_label('Counted cash (₹)', exact=True).fill('67.00')
    expect(drawer.get_by_text('Cash short by ₹0.50.', exact=True)).to_be_visible()
    close_register = drawer.get_by_role('button', name='Close register', exact=True)
    expect(close_register).to_be_disabled()
    drawer.get_by_label('Reason for any difference', exact=True).fill('Recount confirmed shortage')
    capture(page, 'storefront-register-open.png')
    page.set_viewport_size({'width': 390, 'height': 844})
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
    capture(page, 'storefront-register-mobile.png')
    page.set_viewport_size({'width': 1280, 'height': 900})
    close_register.click()
    expect(drawer.locator('.pos-register-status')).to_have_text('Closed')
    drawer.locator('.pos-register-closed summary').click()
    drawer.get_by_role('button', name='View cash activity', exact=True).click()
    expect(drawer.get_by_text('Removed ₹2.50', exact=True)).to_be_visible()
    register = api.request('GET', root + '/pos-register')
    assert register['active'] is None
    assert Decimal(register['closed'][0]['data']['variance']) == Decimal('-0.50')
    page.get_by_text('Daily totals and CSV export', exact=True).click()
    reconciliation = page.get_by_role('region', name='Daily POS reconciliation', exact=True)
    reconciliation.get_by_label('Opening float (₹)', exact=True).fill('50')
    reconciliation.get_by_label('Other cash removed (₹)', exact=True).fill('2.50')
    reconciliation.get_by_label('Cash counted (₹)', exact=True).fill('67.00')
    expect(reconciliation.get_by_text('₹67.50', exact=True)).to_be_visible()
    with page.expect_download() as download:
        reconciliation.get_by_role('button', name='Export count CSV', exact=True).click()
    assert 'Cash over / short,-0.50' in download.value.path().read_text(encoding='utf-8-sig')
    capture(page, 'storefront-register-closed.png')
    assert not errors, errors
    page.get_by_role('button', name='Checkout', exact=True).click()
    expect(page.get_by_text('Book stock: 2.000', exact=True)).to_be_visible()
    capture(page, 'storefront-checkout.png')
    page.set_viewport_size({'width': 390, 'height': 844})
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
    capture(page, 'storefront-mobile.png')
    page.set_viewport_size({'width': 1280, 'height': 900})
    nav.get_by_role('button', name='Items', exact=True).click()
    page.get_by_role('button', name='Count or adjust stock', exact=True).click()
    count = page.get_by_role('dialog', name='Stock adjustment', exact=True)
    count.get_by_label('Entry method', exact=True).select_option('count')
    count = page.get_by_role('dialog', name='Physical stock count', exact=True)
    expect(count.get_by_text('On hand 2.000', exact=False)).to_be_visible()
    count.get_by_label('Counted quantity', exact=True).fill('1')
    count.get_by_label('Reason', exact=True).fill('Shelf count after return')
    expect(count.get_by_text('Stock will decrease by 1.', exact=True)).to_be_visible()
    with page.expect_response(lambda response: response.url.endswith('/stock/counts') and response.request.method == 'POST') as posted_count:
        count.get_by_role('button', name='Post adjustment', exact=True).click()
    assert posted_count.value.ok, posted_count.value.text()
    expect(count.get_by_text('Count posted for Counter cable', exact=False)).to_be_visible()
    stock = api.request('GET', root + f'/reports/stock?from_date={day}&to_date={day}')
    assert Decimal(stock['rows'][0]['closing_quantity']) == 1, stock
    count.get_by_role('button', name='Close', exact=True).click()

    order = api.request('POST', root + '/records', {
        'kind': 'purchase_order', 'name': 'Synthetic supplier', 'date': day,
        'data': {'lines': [{'item_id': item['id'], 'description': 'Counter cable', 'quantity': '5', 'rate': '50', 'gst_rate': '0'}]},
    }, key=uuid4().hex)
    nav.get_by_role('button', name='Purchases', exact=True).click()
    nav.get_by_role('button', name='Purchase orders', exact=True).click()
    page.locator('.workspace-sync-line').get_by_role('button', name='Refresh', exact=True).click()
    page.get_by_role('button', name=order['number'], exact=True).click()
    receiving = page.get_by_role('region', name='Purchase order receiving', exact=True)
    expect(receiving.get_by_text('Awaiting delivery', exact=True)).to_be_visible()
    receiving.get_by_role('button', name='Receive items', exact=True).click()
    received = receiving.get_by_label('Received quantity for Counter cable (line 1)', exact=True)
    received.fill('2')
    receiving.get_by_label('Supplier bill number', exact=True).fill('CABLE-01')
    expect(receiving.get_by_text('Bill total ₹100.00', exact=True)).to_be_visible()
    capture(page, 'storefront-receiving.png')
    page.set_viewport_size({'width': 390, 'height': 844})
    post_bill = receiving.get_by_role('button', name='Post purchase bill', exact=True)
    post_bill.scroll_into_view_if_needed()
    expect(post_bill).to_be_in_viewport()
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
    capture(page, 'storefront-receiving-mobile.png')
    page.set_viewport_size({'width': 1280, 'height': 900})
    page.route('**/api/companies/*/purchase-orders/*/receipts', lose_checkout_response, times=1)
    receiving.get_by_role('button', name='Post purchase bill', exact=True).click()
    expect(receiving.get_by_text('The previous response was not confirmed.', exact=False)).to_be_visible()
    page.once('dialog', lambda dialog: dialog.accept())
    page.reload(wait_until='domcontentloaded')
    expect(receiving.get_by_text('The previous response was not confirmed.', exact=False)).to_be_visible()
    receiving.get_by_role('button', name='Retry bill', exact=True).click()
    expect(receiving.get_by_text('Partially received', exact=True)).to_be_visible()
    expect(receiving.get_by_text('Stock received on bill CABLE-01', exact=True)).to_be_visible()
    receiving.get_by_role('button', name='View purchase bill', exact=True).click()
    page.get_by_role('button', name='View source order', exact=True).click()
    expect(receiving.get_by_text('Partially received', exact=True)).to_be_visible()
    receiving.get_by_role('button', name='Receive items', exact=True).click()
    received.fill('3')
    receiving.get_by_label('Supplier bill number', exact=True).fill('CABLE-02')
    receiving.get_by_label('Unit price for Counter cable (line 1)', exact=True).fill('48')
    receiving.get_by_text('Supplier tax and discount', exact=True).click()
    receiving.get_by_label('Discount on received line (₹)', exact=True).fill('2')
    expect(receiving.get_by_text('Bill total ₹142.00', exact=True)).to_be_visible()
    receiving.get_by_role('button', name='Post purchase bill', exact=True).click()
    expect(receiving.get_by_text('Fully received', exact=True)).to_be_visible()
    order_state = api.request('GET', root + f'/purchase-orders/{order["id"]}/receiving')
    assert len(order_state['receipts']) == 2, order_state
    stock = api.request('GET', root + f'/reports/stock?from_date={day}&to_date={day}')
    assert Decimal(stock['rows'][0]['closing_quantity']) == 6, stock
    assert not errors, errors
    browser.close()
    print('STOREFRONT: exact scan, held cart, stock cap, split payment, reload recovery, PDF, return, register close, stock count and partial supplier receiving passed.', flush=True)
