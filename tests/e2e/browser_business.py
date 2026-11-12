"""Real web trading journey; only masters are seeded through the local API.

Run with run_local.py --business. Independent expected paise amounts link the
visible form preview, saved document, stock, tax, settlements and final ledger.
"""
import io
import json
import os
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from playwright.sync_api import sync_playwright, expect
from pypdf import PdfReader
from browser_support import launch_browser, browser_engine
from test_http_workflow import LiveAccountingWorkflow, BASE

artifacts = Path(os.environ.get('APEX_E2E_ARTIFACTS', 'tmp/business-evidence'))
artifacts.mkdir(parents=True, exist_ok=True)
api = LiveAccountingWorkflow()
credentials = {'email': f'trading-{uuid4().hex}@example.invalid', 'password': 'Synthetic-trading-only-42'}
api.request('POST', '/api/auth/register', credentials)
api.token = api.request('POST', '/api/auth/login', credentials)['token']
company = api.request('POST', '/api/companies', {
    'name': 'Synthetic Harbour Electricals', 'tax_mode': 'regular',
    'state_code': '27', 'gstin': '27AAAAA0000A1Z5', 'address': 'Synthetic Mumbai test address',
})
root = '/api/companies/' + company['id']
day = datetime.now(timezone(timedelta(hours=5, minutes=30))).date().isoformat()


def seed(kind, name, data):
    return api.request('POST', root + '/records', {'kind': kind, 'name': name, 'date': day, 'data': data}, key=uuid4().hex)


seed('party', 'Harbour customer', {'party_type': 'customer', 'payment_terms_days': 14})
seed('party', 'Electrical supplier', {'party_type': 'supplier'})
goods = seed('item', 'Cable assemblies', {'track_stock': True, 'item_type': 'goods', 'unit': 'NOS', 'hsn': '8544', 'sale_rate': '236', 'purchase_rate': '100', 'gst_rate': '18'})
seed('item', 'Installation service', {'item_type': 'services', 'sale_rate': '125', 'gst_rate': '18', 'hsn': '9987'})
checks = []


def check(label, actual, expected):
    assert Decimal(str(actual)) == Decimal(str(expected)), f'{label}: {actual} != {expected}'
    checks.append(label)
    print('BUSINESS: ' + label, flush=True)


def record(record_id):
    return api.request('GET', root + '/records/' + record_id)


with sync_playwright() as playwright:
    browser = launch_browser(playwright)
    context = browser.new_context(viewport={'width': 1440, 'height': 1000}, accept_downloads=True)
    context.tracing.start(screenshots=True, snapshots=True, sources=True)
    page = context.new_page()
    page.set_default_timeout(15000)
    page_errors = []
    page.on('pageerror', lambda error: page_errors.append(str(error)))

    def close_detail():
        detail = page.locator('.transaction-detail')
        if detail.count():
            detail.get_by_role('button', name='Back to register', exact=True).click()
            expect(detail).to_be_hidden()

    def create(menu, title):
        close_detail()
        page.get_by_role('button', name='Create', exact=True).click()
        page.get_by_role('menuitem', name=menu, exact=True).click()
        form = page.get_by_role('dialog', name=title, exact=True)
        expect(form).to_be_visible()
        return form

    def fill_line(form, index, name, quantity, rate, tax='18'):
        form.get_by_label(f'Item {index} description', exact=True).fill(name)
        form.get_by_label(f'Item {index} quantity', exact=True).fill(str(quantity))
        form.get_by_label(f'Item {index} rate', exact=True).fill(str(rate))
        form.get_by_label(f'Item {index} GST rate', exact=True).fill(tax)

    def save(form, label, total=None):
        if total is not None:
            expect(form.locator('.document-grand-total')).to_contain_text(total)
        with page.expect_response(lambda response: response.request.method == 'POST' and response.url in {
            BASE + root + '/records', BASE + root + '/records/with-payment',
        }) as response_info:
            form.get_by_role('button', name=label, exact=True).click()
        response = response_info.value
        assert response.ok, response.text()
        saved = response.json()
        expect(form).to_be_hidden()
        return saved.get('document', saved)

    def navigate(name):
        close_detail()
        nav = page.locator('.sidebar')
        target = nav.get_by_role('button', name=name, exact=True)
        if not target.count():
            nav.get_by_role('button', name='Purchases' if name in {'Purchase bills', 'Debit notes'} else 'Sales', exact=True).click()
        target.click()

    def open_record(saved, section):
        navigate(section)
        page.get_by_role('button', name=saved['number'], exact=True).click()
        detail = page.locator('.transaction-detail')
        expect(detail).to_be_visible()
        return detail

    def cancel(detail):
        detail.get_by_role('button', name='Cancel document', exact=True).click()
        panel = page.get_by_role('alertdialog')
        panel.get_by_label('Reason (required)', exact=True).fill('Synthetic correction of duplicate entry')
        panel.get_by_role('button', name='Cancel document', exact=True).click()
        expect(detail.locator('.cancelled-note')).to_be_visible()

    try:
        page.goto(BASE, wait_until='domcontentloaded')
        page.get_by_label('Email address', exact=True).fill(credentials['email'])
        page.get_by_label('Password', exact=True).fill(credentials['password'])
        page.get_by_role('button', name='Sign in', exact=True).click()
        expect(page.get_by_role('status').filter(has_text='Company data loaded')).to_be_visible()

        form = create('Purchase bill', 'New purchase bill')
        form.get_by_label('Supplier / description', exact=True).fill('Electrical supplier')
        fill_line(form, 1, goods['name'], 10, 100)
        bill = save(form, 'Save bill', '1,180.00')
        check('Purchase total and GST preview match saved bill', bill['amount'], '1180')

        form = create('Sales invoice', 'New sales invoice')
        form.get_by_label('Customer / description', exact=True).fill('Harbour customer')
        fill_line(form, 1, goods['name'], 3, 236)
        form.locator('.line-more summary').first.click()
        form.get_by_label('Rate includes GST', exact=True).first.check()
        form.get_by_label('Item 1 discount percent', exact=True).fill('10')
        form.get_by_role('button', name='Add item / service', exact=True).click()
        fill_line(form, 2, 'Installation service', 2, 125)
        form.get_by_label('Item 2 discount mode', exact=True).select_option('amount')
        form.get_by_label('Item 2 discount amount', exact=True).fill('25')
        form.get_by_label('Document discount (%)', exact=True).fill('5')
        form.get_by_role('button', name='Apply payment terms', exact=True).click()
        expected_due = (datetime.fromisoformat(day) + timedelta(days=14)).date().isoformat()
        expect(form.get_by_label('Due date', exact=True)).to_have_value(expected_due)
        form.get_by_role('checkbox', name=re.compile('^Received now')).check()
        form.locator('.pay-now').get_by_label('Amount', exact=True).fill('200')
        invoice = save(form, 'Save invoice', '857.57')
        check('Mixed inclusive/exclusive GST and both discount modes total', invoice['amount'], '857.57')
        check('Same-step receipt reduces outstanding exactly', record(invoice['id'])['outstanding'], '657.57')
        detail = page.locator('.transaction-detail')
        expect(detail).to_be_visible()
        with page.expect_download() as download:
            detail.get_by_role('button', name='Download PDF', exact=True).click()
        raw_pdf = Path(download.value.path()).read_bytes()
        text = ' '.join(sheet.extract_text() for sheet in PdfReader(io.BytesIO(raw_pdf)).pages)
        assert '857.57' in text and company['name'] in text and 'Harbour customer' in text
        checks.append('Visible invoice PDF retains party, company and exact total')

        form = create('Sales invoice', 'New sales invoice')
        form.get_by_label('Customer / description', exact=True).fill('Harbour customer')
        fill_line(form, 1, goods['name'], 1, 100)
        second = save(form, 'Save invoice', '118.00')
        form = create('Payment in', 'New payment in')
        form.get_by_label('Payment amount (₹)', exact=True).fill('300')
        form.get_by_role('combobox', name='Invoice or bill', exact=True).select_option(invoice['id'])
        form.get_by_label('Allocated amount (₹)', exact=True).fill('200')
        form.get_by_role('button', name='Add another document', exact=True).click()
        form.get_by_role('combobox', name='Invoice or bill', exact=True).nth(1).select_option(second['id'])
        form.get_by_label('Allocated amount (₹)', exact=True).nth(1).fill('100')
        save(form, 'Save receipt')
        check('Split receipt preserves first invoice remainder', record(invoice['id'])['outstanding'], '457.57')
        check('Split receipt preserves second invoice remainder', record(second['id'])['outstanding'], '18')

        detail = open_record(invoice, 'Sales invoices')
        detail.get_by_role('button', name='Sales return', exact=True).click()
        form = page.get_by_role('dialog', name='New credit note', exact=True)
        form.get_by_role('button', name='Remove item 2', exact=True).click()
        form.get_by_label('Item 1 quantity', exact=True).fill('1')
        credit = save(form, 'Save credit note', '201.78')
        check('Returned quantity uses source price/tax/discount', credit['amount'], '201.78')
        check('Sales return reduces remaining invoice balance', record(invoice['id'])['outstanding'], '255.79')
        detail = open_record(credit, 'Credit notes')
        cancel(detail)
        check('Cancelling return restores invoice balance', record(invoice['id'])['outstanding'], '457.57')

        detail = open_record(bill, 'Purchase bills')
        detail.get_by_role('button', name='Pay bill', exact=True).click()
        form = page.get_by_role('dialog', name='New payment out', exact=True)
        form.get_by_label('Payment amount (₹)', exact=True).fill('300')
        form.get_by_label('Allocated amount (₹)', exact=True).fill('300')
        save(form, 'Save payment')
        detail = open_record(bill, 'Purchase bills')
        detail.get_by_role('button', name='Purchase return', exact=True).click()
        form = page.get_by_role('dialog', name='New debit note', exact=True)
        form.get_by_label('Item 1 quantity', exact=True).fill('1')
        save(form, 'Save debit note', '118.00')
        check('Supplier return and partial payment reconcile', record(bill['id'])['outstanding'], '762')

        form = create('Expense', 'New expense')
        form.get_by_label('Supplier / description', exact=True).fill('Local delivery')
        fill_line(form, 1, 'Delivery fee', 1, 20, tax='0')
        save(form, 'Save expense', '20.00')

        # A cancelled document must disappear from available return/payment targets.
        form = create('Sales invoice', 'New sales invoice')
        form.get_by_label('Customer / description', exact=True).fill('Duplicate customer')
        fill_line(form, 1, 'Duplicate service', 1, 100)
        duplicate = save(form, 'Save invoice', '118.00')
        detail = page.locator('.transaction-detail')
        expect(detail).to_be_visible()
        cancel(detail)
        form = create('Credit note', 'New credit note')
        expect(form.get_by_role('combobox', name='Original posted document', exact=True).locator(f'option[value="{duplicate["id"]}"]')).to_have_count(0)
        form.get_by_role('button', name='Cancel', exact=True).click()
        checks.append('Cancelled invoice cannot be selected as a return source')

        query = f'?from_date={day}&to_date={day}'
        summary = api.request('GET', root + '/reports/summary' + query)
        financial = api.request('GET', root + '/reports/financial' + query)
        statements = api.request('GET', root + '/reports/statements' + query)
        stock = api.request('GET', root + '/reports/stock' + query)
        check('Final net sales including GST', summary['sales'], '975.57')
        check('Final net purchases including GST', summary['purchases'], '1062')
        check('Final receivables across both invoices', summary['receivables'], '475.57')
        check('Final supplier payable', summary['payables'], '762')
        check('Final net profit excludes recoverable GST and stock assets', financial['net_profit'], '406.75')
        check('Balance sheet reconciles exactly', statements['balance_sheet']['difference'], '0')
        item_stock = next(row for row in stock['rows'] if row['item_id'] == goods['id'])
        check('Stock after sales, cancelled return and supplier return', item_stock['closing_quantity'], '5')
        check('Stock carrying value after the full journey', item_stock['closing_value'], '500')
        cash = next(row for row in financial['accounts'] if row['code'] == 'SYS-CASH')
        check('Cash reconciles receipts, supplier payment and expense', cash['closing_balance'], '180')
        navigate('Dashboard')
        expect(page.locator('.overview-metric').nth(0)).to_contain_text('975.57')
        expect(page.locator('.overview-metric').nth(1)).to_contain_text('406.75')
        expect(page.locator('.overview-metric').nth(2)).to_contain_text('475.57')
        expect(page.locator('.overview-metric').nth(3)).to_contain_text('762.00')
        assert not page_errors, page_errors
        page.screenshot(path=str(artifacts/'business-reconciled.png'), full_page=True)
        (artifacts/'business-result.json').write_text(json.dumps({'passed': True, 'engine': browser_engine(), 'checks': checks, 'summary': summary, 'net_profit': financial['net_profit']}, indent=2), encoding='utf-8')
        print(f'Business acceptance passed: {len(checks)} reconciled checks.', flush=True)
    except BaseException:
        page.screenshot(path=str(artifacts/'business-failure.png'), full_page=True)
        (artifacts/'business-failure.html').write_text(page.content(), encoding='utf-8')
        raise
    finally:
        context.tracing.stop(path=str(artifacts/'business-trace.zip'))
        context.close()
        browser.close()
