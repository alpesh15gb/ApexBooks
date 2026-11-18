"""Drive the Keystone correction and party PDF export through the normal web UI."""
import io
from decimal import Decimal

import httpx
from playwright.sync_api import expect, sync_playwright
from pypdf import PdfReader

from browser_support import launch_browser
from keystone_receipt_fixture import BASE, NOV, OCT, seed


with httpx.Client(base_url=BASE, timeout=30, trust_env=False) as client, sync_playwright() as playwright:
    fixture = seed(client)
    browser = launch_browser(playwright)
    page = browser.new_page(viewport={'width': 1280, 'height': 900}, accept_downloads=True)
    page.set_default_timeout(12000)
    page.goto(BASE)
    page.get_by_label('Email address', exact=True).fill(fixture['credentials']['email'])
    page.get_by_label('Password', exact=True).fill(fixture['credentials']['password'])
    page.get_by_role('button', name='Sign in', exact=True).click()
    expect(page.get_by_role('status').filter(has_text='Company data loaded')).to_be_visible()
    page.get_by_role('button', name='Sales', exact=True).click()
    page.get_by_role('button', name='Payment in', exact=True).click()
    page.get_by_label('Advance payment', exact=True).select_option(fixture['hosting']['id'])
    page.get_by_role('button', name='View receipt', exact=True).click()
    receipt = page.get_by_role('dialog', name=fixture['hosting']['number'], exact=True)
    expect(receipt.get_by_role('button', name='Correct allocation', exact=True)).to_be_enabled()
    receipt.get_by_role('button', name='Back to register').click()
    application = fixture['application']['number']
    page.get_by_role('button', name=application, exact=True).click()
    detail = page.get_by_role('dialog', name=application, exact=True)
    detail.get_by_role('button', name='Correct allocation', exact=True).click()
    dialog = page.get_by_role('dialog', name='Correct allocation', exact=True)
    expect(dialog.get_by_text('Currently unallocated ₹30,799.00', exact=False)).to_be_visible()
    expect(dialog.get_by_role('checkbox', name=f'Unlink {application}', exact=False)).to_be_checked()
    for receipt in ('hosting', 'unknown'):
        dialog.get_by_role('checkbox', name='Reclassify ' + fixture[receipt]['number'], exact=True).check()
    dialog.get_by_label('Another bank credit or receipt').select_option(fixture['plan']['credits'][1]['credit_id'])
    dialog.get_by_role('button', name='Add credit', exact=True).click()
    november = dialog.get_by_role('region', name='UTR QA-DCB-NOV', exact=False)
    expect(november.get_by_text('RAM under PO 1178')).to_be_visible()
    november.get_by_role('button', name='Add allocation', exact=True).click()
    november.get_by_label('Allocation amount', exact=True).fill('17700')
    november.get_by_label('Invoice', exact=True).select_option(fixture['invoice']['id'])
    dialog.get_by_label('Correction reason').fill(fixture['plan']['reason'])
    dialog.get_by_role('button', name='Preview correction', exact=True).click()
    preview = dialog.get_by_role('region', name='Correction preview')
    expect(preview.get_by_role('row').filter(has_text='QA-DCB-OCT')).to_contain_text('Unallocated ₹48,499.00')
    expect(preview.get_by_role('row').filter(has_text='QA-DCB-NOV')).to_contain_text('Booked ₹43,542.00')
    expect(preview.get_by_role('row').filter(has_text='2026-27/34').last).to_contain_text('₹0.00')
    # Lose the initial HTTP response after the server has posted, then use the UI's retry.
    post_url = '**' + fixture['path'] + '/post'
    def lose_confirmation(route):
        assert route.fetch().ok
        route.abort()
    page.route(post_url, lose_confirmation, times=1)
    dialog.get_by_role('button', name='Post correction', exact=True).click()
    dialog.get_by_role('button', name='Retry correction', exact=True).click()
    expect(dialog.get_by_role('status').filter(has_text='Receipt allocation corrected.')).to_be_visible()
    dialog.get_by_role('button', name='Close correction', exact=True).click()
    page.get_by_role('button', name='Sales invoices', exact=True).click()
    expect(page.get_by_role('row').filter(has_text='2026-27/34')).to_contain_text('Settled')
    page.get_by_role('button', name='Parties', exact=True).click()
    page.get_by_role('button', name='Keystone', exact=True).click()
    statement = page.get_by_role('dialog', name='Keystone', exact=True)
    statement.get_by_label('From date').fill(OCT)
    statement.get_by_label('To date').fill(NOV)
    expect(statement.get_by_text('Customer receipts received ₹92,041.00')).to_be_visible()
    expect(statement.get_by_text(application, exact=False)).to_have_count(0)
    for history in (False, True):
        if history:
            statement.get_by_label('Include correction history').check()
            expect(statement.get_by_role('region', name='Correction history')).to_contain_text(application)
        with page.expect_download() as downloaded:
            statement.get_by_role('button', name='Export PDF', exact=True).click()
        content = downloaded.value.path().read_bytes()
        text = ' '.join(' '.join(p.extract_text().split()) for p in PdfReader(io.BytesIO(content)).pages)
        assert (application in text) == history
        assert all(value in text for value in ('48,499.00', '25,842.00', '92,041.00', '2026-27/34'))
    result = client.get(fixture['root'] + '/bank-reconciliation',
                        params={'bank_account_id': fixture['bank']['id']}).raise_for_status().json()
    assert (Decimal(result['ledger_movement']), Decimal(result['difference']), result['matched']) == (92041, 0, 2)
    browser.close()
    print('Keystone browser correction, uncertain-response replay, statement PDFs and DCB BANK reconciliation passed.')
