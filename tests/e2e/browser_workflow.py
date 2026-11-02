"""Browser smoke for CI/local Playwright. Requires isolated serve-local.sh.

This test creates synthetic data. No hosted target or local database tunnel allowed.
Manual CUA coverage is recorded in README; this automation is an additional gate.
"""
import os
import re
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4
from playwright.sync_api import sync_playwright, expect

base = os.environ.get('APEX_E2E_BASE', 'http://127.0.0.1:15173').rstrip('/')
if urlparse(base).hostname not in {'127.0.0.1', 'localhost', '::1'}:
    raise RuntimeError('Browser writes require a disposable loopback workspace')
artifacts = Path(os.environ.get('APEX_E2E_ARTIFACTS', '/tmp/apex-browser-artifacts'))
artifacts.mkdir(parents=True, exist_ok=True)


def register_company(page):
    page.goto(base)
    page.get_by_role('button', name='Create an account', exact=True).click()
    page.get_by_role('textbox', name='Email address', exact=True).fill(f'browser-{uuid4().hex}@example.invalid')
    page.get_by_label('Password', exact=True).fill('Synthetic-browser-only-42')
    page.get_by_role('button', name='Create account', exact=True).click()
    dialog = page.get_by_role('dialog', name='Add a company', exact=True)
    expect(dialog).to_be_visible()
    dialog.get_by_role('textbox', name='Company name', exact=True).fill('Synthetic browser company')
    dialog.get_by_role('button', name='Create company', exact=True).click()
    expect(dialog).to_be_hidden()
    expect(page.get_by_text('Books loaded', exact=True)).to_be_visible()


with sync_playwright() as p:
    browser = p.chromium.launch()
    desktop = browser.new_context(viewport={'width': 1280, 'height': 900}, accept_downloads=True)
    page = desktop.new_page()
    page.set_default_timeout(15000)
    register_company(page)
    page.get_by_role('button', name='New invoice', exact=True).click()
    dialog = page.get_by_role('dialog', name='New sales invoice', exact=True)
    dialog.get_by_role('button', name='Cancel', exact=True).click()
    expect(dialog).to_be_hidden()
    page.get_by_role('button', name='Add sales invoice', exact=True).first.click()
    dialog.get_by_role('combobox', name='Customer / description', exact=True).fill('Synthetic customer')
    dialog.get_by_role('combobox', name='Item 1 description', exact=True).fill('Synthetic service')
    dialog.get_by_role('spinbutton', name='Item 1 quantity', exact=True).fill('2')
    dialog.get_by_role('spinbutton', name='Item 1 rate', exact=True).fill('125.50')
    dialog.get_by_role('button', name='Save invoice', exact=True).click()
    expect(dialog).to_be_hidden()
    invoice_button = page.get_by_role('button', name=re.compile(r'^INV/'))
    expect(invoice_button).to_be_visible()
    invoice_reference = invoice_button.inner_text()
    expect(page.get_by_role('row').filter(has_text='Synthetic customer')).to_have_count(1)
    invoice_button.click()
    detail = page.get_by_role('dialog', name=invoice_reference, exact=True)
    expect(detail).to_contain_text('Still outstanding')
    detail.get_by_role('button', name='Collect payment', exact=True).click()
    contextual_payment = page.get_by_role('dialog', name='New payment in', exact=True)
    contextual_payment.get_by_role('button', name='Cancel', exact=True).click()
    expect(detail).to_be_visible()
    detail.get_by_role('button', name='Edit details', exact=True).click()
    edit = page.get_by_role('dialog', name='Edit sales invoice', exact=True)
    edit.get_by_role('combobox', name='Customer / description', exact=True).fill('Unsaved browser change')
    page.go_back()
    discard = page.get_by_role('dialog', name='Discard unsaved changes?', exact=True)
    expect(discard).to_be_visible()
    discard.get_by_role('button', name='Keep editing', exact=True).click()
    expect(edit.get_by_role('combobox', name='Customer / description', exact=True)).to_have_value('Unsaved browser change')
    edit.get_by_role('button', name='Cancel', exact=True).click()
    discard.get_by_role('button', name='Discard draft', exact=True).click()
    expect(detail).to_contain_text('Synthetic customer')
    detail.get_by_role('button', name='Back to register', exact=True).click()
    page.get_by_role('button', name='Payment in', exact=True).click()
    page.get_by_role('button', name='Add payment in', exact=True).first.click()
    payment = page.get_by_role('dialog', name='New payment in', exact=True)
    payment.get_by_role('combobox', name='Invoice or bill', exact=True).select_option(index=1)
    payment.get_by_role('spinbutton', name='Payment amount (₹)', exact=True).fill('100')
    payment.get_by_role('spinbutton', name='Allocated amount (₹)', exact=True).fill('100')
    payment.get_by_role('button', name='Save receipt', exact=True).click()
    expect(payment).to_be_hidden()
    page.get_by_role('button', name='Sales invoices', exact=True).click()
    row = page.get_by_role('row').filter(has_text='Synthetic customer')
    expect(row).to_contain_text('₹151.00')
    expect(row).to_contain_text('Part settled')
    with page.expect_download() as download:
        page.get_by_role('button', name=f'Download {invoice_reference} PDF', exact=True).click()
    download.value.save_as(artifacts / 'synthetic-invoice.pdf')
    page.get_by_role('button', name='Reports', exact=True).click()
    page.get_by_role('button', name='Receivables & payables ageing Outstanding amounts by age', exact=True).click()
    expect(page.get_by_role('row').filter(has_text='Synthetic customer')).to_contain_text('₹151.00')
    with page.expect_download() as download:
        page.get_by_role('button', name='XLSX', exact=True).click()
    download.value.save_as(artifacts / 'synthetic-ageing.xlsx')
    page.screenshot(path=str(artifacts / 'desktop-ageing.png'), full_page=True)
    page.get_by_role('button', name='Sign out', exact=True).click()
    expect(page.get_by_role('button', name='Sign in', exact=True)).to_be_visible()
    desktop.close()

    mobile = browser.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True, has_touch=True)
    page = mobile.new_page()
    page.set_default_timeout(15000)
    register_company(page)
    page.get_by_role('button', name='New invoice', exact=True).click()
    dialog = page.get_by_role('dialog', name='New sales invoice', exact=True)
    expect(dialog).to_be_visible()
    expect(dialog.get_by_role('button', name='Save invoice', exact=True)).to_be_visible()
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 1'), 'Mobile viewport overflows horizontally'
    page.screenshot(path=str(artifacts / 'mobile-invoice.png'), full_page=True)
    dialog.get_by_role('button', name='Close', exact=True).click()
    expect(dialog).to_be_hidden()
    mobile.close()
    browser.close()
print('Browser smoke passed: desktop accounting flow and mobile document dismissal')
