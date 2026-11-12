"""Real-browser nine-line quotation entry, PDF download and invoice conversion.

Uses newly created synthetic books through the loopback-only e2e runner.
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
    'state_code': '27', 'gstin': '27AAAAA0000A1Z2', 'address': 'Synthetic Mumbai test address',
})
root = '/api/companies/' + company['id']
day = datetime.now(timezone(timedelta(hours=5, minutes=30))).date().isoformat()


checks = []


def check(label, actual, expected):
    assert Decimal(str(actual)) == Decimal(str(expected)), f'{label}: {actual} != {expected}'
    checks.append(label)
    print('BUSINESS: ' + label, flush=True)


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

    try:
        fixture=json.loads((Path(__file__).resolve().parents[2]/'native/shared/fixtures/quotation-nine-lines.json').read_text())
        page.goto(BASE,wait_until='domcontentloaded')
        page.get_by_label('Email address',exact=True).fill(credentials['email'])
        page.get_by_label('Password',exact=True).fill(credentials['password'])
        page.get_by_role('button',name='Sign in',exact=True).click()
        expect(page.get_by_role('status').filter(has_text='Company data loaded')).to_be_visible()
        form=create('Estimate','New estimate')
        form.get_by_label('Customer / description',exact=True).fill(fixture['name'])
        for i,line in enumerate(fixture['data']['lines'],1):
            if i>1:form.get_by_role('button',name='Add item / service',exact=True).click()
            fill_line(form,i,line['description'],line['quantity'],line['rate'])
            form.get_by_label(f'Item {i} unit',exact=True).fill(line['unit'])
            row=form.locator('.document-item-row').nth(i-1)
            row.locator('details.line-more summary').click();row.get_by_label('HSN / SAC',exact=True).fill(line['hsn'])
        form.get_by_label('Round total to nearest rupee',exact=True).check()
        form.locator('details.document-notes summary').click()
        form.get_by_label('Notes',exact=True).fill(fixture['data']['notes'])
        form.get_by_label('Terms and conditions',exact=True).fill(fixture['data']['terms'])
        page.screenshot(path=str(artifacts/'quotation-nine-entry.png'),full_page=True)
        quote=save(form,'Save estimate','17,385.00')
        check('Nine-line quotation total',quote['amount'],fixture['expected']['amount'])
        assert api.request('GET',root+'/journals')==[]
        detail=page.locator('.transaction-detail');expect(detail).to_be_visible()
        with page.expect_download() as download:detail.get_by_role('button',name='Download PDF',exact=True).click()
        pdf=Path(download.value.path()).read_bytes();(artifacts/'quotation-nine-browser.pdf').write_bytes(pdf)
        text=' '.join(p.extract_text() for p in PdfReader(io.BytesIO(pdf)).pages)
        assert '17,385.00' in text and 'Warranty' in text and 'END09' in text
        detail.get_by_role('button',name='Convert to invoice',exact=True).click()
        form=page.get_by_role('dialog',name='New sales invoice',exact=True);expect(form).to_be_visible()
        expect(form.locator('.document-item-row')).to_have_count(9)
        invoice=save(form,'Save invoice','17,385.00')
        for record in (quote,invoice):
            for key in ('notes','terms','round_total'):assert record['data'][key]==fixture['data'][key],key
            for actual,wanted in zip(record['data']['lines'],fixture['data']['lines']):
                for key in ('description','quantity','rate','unit','hsn','gst_rate'):assert str(actual[key])==wanted[key],key
            for key in ('taxable','cgst','sgst','round_off'):check('Quotation/invoice '+key,record['data'][key],fixture['expected'][key])
        assert api.request('GET',root+'/records/'+quote['id'])['converted_to']==invoice['id']
        assert invoice['data']['source_document_id']==quote['id']
        page.screenshot(path=str(artifacts/'quotation-nine-converted.png'),full_page=True)
        assert not page_errors,page_errors
        (artifacts/'quotation-nine-result.json').write_text(json.dumps({'passed':True,'checks':checks,'quote_id':quote['id'],'invoice_id':invoice['id'],'expected':fixture['expected']},indent=2))
        print('Nine-line quotation browser acceptance passed.',flush=True)
    except BaseException:
        page.screenshot(path=str(artifacts/'quotation-nine-failure.png'),full_page=True)
        (artifacts/'quotation-nine-failure.html').write_text(page.content())
        raise
    finally:
        context.tracing.stop(path=str(artifacts/'quotation-nine-trace.zip'));context.close();browser.close()
