"""Browser smoke for CI/local Playwright. Prefer isolated run_local.py --browser.

This test creates synthetic data. No hosted target or local database tunnel allowed.
Manual CUA coverage is recorded in README; this automation is an additional gate.
"""
import os
import re
import json
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4
from playwright.sync_api import sync_playwright, expect

base = os.environ.get('APEX_E2E_BASE', 'http://127.0.0.1:15173').rstrip('/')
if urlparse(base).hostname not in {'127.0.0.1', 'localhost', '::1'}:
    raise RuntimeError('Browser writes require a disposable loopback workspace')
artifacts = Path(os.environ.get('APEX_E2E_ARTIFACTS', '/tmp/apex-browser-artifacts'))
artifacts.mkdir(parents=True, exist_ok=True)


def progress(message):
    print('BROWSER: '+message, flush=True)


@contextmanager
def fresh_page(browser, label, **options):
    context=browser.new_context(**options)
    context.tracing.start(screenshots=True, snapshots=True, sources=True)
    page=context.new_page()
    page.set_default_timeout(15000)
    pending=set(); events=[]
    def note(kind, message):
        events.append({'kind':kind,'message':str(message)})
        del events[:-100]
    page.on('request', lambda request: pending.add(request.url))
    page.on('requestfinished', lambda request: pending.discard(request.url))
    page.on('requestfailed', lambda request: (pending.discard(request.url),note('requestfailed',request.url+' '+str(request.failure))))
    page.on('pageerror', lambda error: note('pageerror',error))
    page.on('console', lambda message: note('console-'+message.type,message.text) if message.type in ('error','warning') else None)
    progress(label+' context created')
    try:
        yield page
    except BaseException as error:
        progress(label+' failed: '+str(error))
        state={'url':page.url,'error':str(error),'pending_requests':sorted(pending),'events':events}
        try:
            state['invalid_controls']=page.locator('input:invalid,select:invalid,textarea:invalid').evaluate_all("nodes => nodes.map(node => ({name:node.name,label:node.getAttribute('aria-label'),message:node.validationMessage}))")
            page.screenshot(path=str(artifacts/(label+'-failure.png')),timeout=10000)
            (artifacts/(label+'-failure.html')).write_text(page.content(),encoding='utf-8')
        except Exception as capture_error:
            state['capture_error']=str(capture_error)
        (artifacts/(label+'-failure.json')).write_text(json.dumps(state,indent=2),encoding='utf-8')
        print(json.dumps(state,indent=2),flush=True)
        raise
    finally:
        context.tracing.stop(path=str(artifacts/(label+'-trace.zip')))
        context.close()


def register_company(page):
    # Wait for the document and real controls, not unrelated network idleness.
    progress('opening isolated sign-in page')
    page.goto(base, wait_until='domcontentloaded', timeout=60000)
    progress('sign-in page document loaded')
    page.get_by_role('button', name='Create an account', exact=True).click()
    page.get_by_role('textbox', name='Email address', exact=True).fill(f'browser-{uuid4().hex}@example.invalid')
    page.get_by_label('Password', exact=True).fill('Synthetic-browser-only-42')
    page.get_by_role('button', name='Create account', exact=True).click()
    dialog = page.get_by_role('dialog', name='Add a company', exact=True)
    expect(dialog).to_be_visible()
    dialog.get_by_role('textbox', name='Company name', exact=True).fill('Synthetic browser company')
    dialog.get_by_role('button', name='Create company', exact=True).click()
    expect(dialog).to_be_hidden()
    # The desktop "Books loaded" badge is intentionally hidden on mobile.
    # Assert the responsive workspace status that both layouts expose instead.
    expect(page.get_by_role('status').filter(has_text='Company data loaded')).to_be_visible()
    progress('synthetic account and company ready')


with sync_playwright() as p:
    # A fresh headless profile can use an installed browser on Windows. Never
    # attach to the user's browser, profile, or existing debug endpoint.
    channel = os.environ.get('APEX_BROWSER_CHANNEL')
    if channel not in {None, 'chrome', 'msedge'}:
        raise RuntimeError('Unsupported isolated browser channel')
    progress('launching '+(channel or 'Playwright Chromium')+' in a fresh headless profile')
    browser = p.chromium.launch(**({'channel': channel} if channel else {}))
    with fresh_page(browser,'desktop',viewport={'width':1280,'height':900},accept_downloads=True) as page:
        register_company(page)
        page.get_by_role('button', name='New invoice', exact=True).click()
        dialog = page.get_by_role('dialog', name='New sales invoice', exact=True)
        dialog.get_by_role('button', name='Cancel', exact=True).click()
        expect(dialog).to_be_hidden()
        page.get_by_role('button', name='Add sales invoice', exact=True).first.click()
        dialog.get_by_role('combobox', name='Customer / description', exact=True).fill('Synthetic customer')
        expect(dialog.get_by_role('combobox', name='Customer / description', exact=True)).to_have_value('Synthetic customer')
        dialog.get_by_role('combobox', name='Item 1 description', exact=True).fill('Synthetic service')
        dialog.get_by_role('spinbutton', name='Item 1 quantity', exact=True).fill('2')
        dialog.get_by_role('spinbutton', name='Item 1 rate', exact=True).fill('125.50')
        expect(dialog.get_by_role('combobox', name='Customer / description', exact=True)).to_have_value('Synthetic customer')
        progress('invoice inputs retained; posting through visible Save')
        dialog.get_by_role('button', name='Save invoice', exact=True).click()
        expect(dialog).to_be_hidden()
        invoice_button = page.get_by_role('button', name=re.compile(r'^INV\/'))
        expect(invoice_button).to_be_visible()
        invoice_reference = invoice_button.inner_text()
        progress('invoice posted and register reference visible')
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
        progress('partial receipt posted; register balance agrees')
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
        progress('ageing balance and PDF/XLSX downloads verified')

        # The first keystroke/paste must reach controlled state before dirty
        # tracking renders. Exercise both document and recurring-template forms.
        page.get_by_role('button', name='Estimates', exact=True).click()
        page.get_by_role('button', name='Add estimate', exact=True).first.click()
        estimate = page.get_by_role('dialog', name='New estimate', exact=True)
        estimate.get_by_role('combobox', name='Customer / description', exact=True).fill('Recurring synthetic customer')
        expect(estimate.get_by_role('combobox', name='Customer / description', exact=True)).to_have_value('Recurring synthetic customer')
        estimate.get_by_role('combobox', name='Item 1 description', exact=True).fill('Monthly service')
        estimate.get_by_role('spinbutton', name='Item 1 rate', exact=True).fill('75')
        estimate.get_by_role('button', name='Save estimate', exact=True).click()
        expect(estimate).to_be_hidden()
        page.get_by_role('button', name='Recurring drafts', exact=True).click()
        page.get_by_role('button', name='New template', exact=True).click()
        template = page.get_by_role('dialog', name='New recurring draft template', exact=True)
        template.get_by_role('textbox', name='Template name', exact=True).fill('Monthly synthetic service')
        expect(template.get_by_role('textbox', name='Template name', exact=True)).to_have_value('Monthly synthetic service')
        template.get_by_role('combobox', name=re.compile(r'^Reviewed source draft')).select_option(index=1)
        template.get_by_role('button', name='Save template', exact=True).click()
        expect(template).to_be_hidden()
        library_row = page.locator('.recurring-row').filter(has_text='Monthly synthetic service').filter(
            has=page.get_by_role('button', name='Review / edit', exact=True))
        expect(library_row).to_have_count(1)
        progress('recurring template first input retained and saved from reviewed estimate')
        page.get_by_role('button', name='Sign out', exact=True).click()
        expect(page.get_by_role('button', name='Sign in', exact=True)).to_be_visible()

    with fresh_page(browser,'mobile',viewport={'width':390,'height':844},is_mobile=True,has_touch=True) as page:
        register_company(page)
        page.get_by_role('button', name='New invoice', exact=True).click()
        dialog = page.get_by_role('dialog', name='New sales invoice', exact=True)
        expect(dialog).to_be_visible()
        expect(dialog.get_by_role('button', name='Save invoice', exact=True)).to_be_visible()
        assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 1'), 'Mobile viewport overflows horizontally'
        page.screenshot(path=str(artifacts / 'mobile-invoice.png'), full_page=True)
        dialog.get_by_role('button', name='Close', exact=True).click()
        expect(dialog).to_be_hidden()
        page.get_by_role('button', name='Add sales invoice', exact=True).first.click()
        dialog.get_by_role('combobox', name='Customer / description', exact=True).fill('Mobile synthetic customer')
        expect(dialog.get_by_role('combobox', name='Customer / description', exact=True)).to_have_value('Mobile synthetic customer')
        dialog.get_by_role('button', name='Close', exact=True).click()
        discard = page.get_by_role('dialog', name='Discard unsaved changes?', exact=True)
        expect(discard).to_be_visible()
        discard.get_by_role('button', name='Discard draft', exact=True).click()
        expect(dialog).to_be_hidden()
        progress('mobile first input retained; empty close and dirty discard verified')

    browser.close()
print('Browser smoke passed: desktop accounting flow and mobile document dismissal')
