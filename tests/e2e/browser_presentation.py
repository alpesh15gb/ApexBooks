"""Visual, accessibility and keyboard acceptance on disposable local books.

Run through run_local.py --browser --presentation, never against hosted books.
Screenshots and the axe report are saved alongside the accounting evidence.
"""
import json
import os
from pathlib import Path
from uuid import uuid4
from playwright.sync_api import sync_playwright, expect
from test_http_workflow import LiveAccountingWorkflow, BASE

ARTIFACTS = Path(os.environ.get('APEX_E2E_ARTIFACTS', '/tmp/apex-presentation'))
ARTIFACTS.mkdir(parents=True, exist_ok=True)
AXE = Path(__file__).resolve().parents[2] / 'frontend/node_modules/axe-core/axe.min.js'
client = LiveAccountingWorkflow()
credentials = {'email': f'presentation-{uuid4().hex}@example.invalid', 'password': 'Synthetic-visual-only-42'}
client.request('POST', '/api/auth/register', credentials)
client.token = client.request('POST', '/api/auth/login', credentials)['token']
company = client.request('POST', '/api/companies', {
    'name': 'Apex Studio & Supply Company with a deliberately long business name',
    'tax_mode': 'unregistered', 'state_code': '27', 'address': 'Synthetic local test address',
})
root = '/api/companies/' + company['id']

def post(kind, name, data, **extra):
    return client.request('POST', root+'/records', {
        'kind': kind, 'name': name, 'date': '2026-11-01', 'data': data, **extra,
    }, key=uuid4().hex)

party = post('party', 'A long customer name for presentation and keyboard acceptance', {'phone': '9999999999'})
post('item', 'Synthetic studio service', {'item_type': 'services', 'sale_rate': '1250', 'unit': 'Service'})
invoice = post('sales_invoice', party['name'], {'party_id': party['id'], 'lines': [
    {'description': 'Synthetic consulting service', 'quantity': 1, 'rate': '98765432.10', 'gst_rate': 0},
]})
post('purchase_bill', 'Synthetic supplier', {'lines': [
    {'description': 'Synthetic supplies', 'quantity': 1, 'rate': 800, 'gst_rate': 0},
]})
post('payment_in', party['name'], {'applied_to': invoice['id'], 'payment_account': 'cash'}, amount='10000000')

reports, errors = [], []
with sync_playwright() as p:
    browser = p.chromium.launch()
    context = browser.new_context(viewport={'width': 1440, 'height': 1000}, reduced_motion='reduce')
    context.tracing.start(screenshots=True, snapshots=True, sources=True)
    page = context.new_page()
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.set_default_timeout(15000)
    def capture(label, audit=True):
        # Fonts, data responses and two painted frames precede geometry/captures.
        page.evaluate('''async () => { await document.fonts.ready; await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r))); }''')
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1'), f'{label}: horizontal page overflow'
        page.screenshot(path=str(ARTIFACTS/f'{label}.png'), full_page=not page.locator('[aria-modal="true"]').count())
        if audit:
            if not page.evaluate('!!window.axe'):
                page.add_script_tag(path=str(AXE))
            violations = page.evaluate('''async () => {
                const result = await axe.run(document, {runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21aa']}});
                return result.violations.map(v => ({id:v.id,impact:v.impact,nodes:v.nodes.map(n => ({target:n.target,summary:n.failureSummary}))}));
            }''')
            reports.append({'screen': label, 'violations': violations})
            (ARTIFACTS/'accessibility.json').write_text(json.dumps(reports, indent=2))
        print('PRESENTATION: '+label, flush=True)

    def navigate(name):
        if page.get_by_role('button', name='Open menu', exact=True).is_visible():
            page.get_by_role('button', name='Open menu', exact=True).click()
        nav = page.locator('.sidebar')
        button = nav.get_by_role('button', name=name, exact=True)
        if not button.count():
            nav.get_by_role('button', name='Sales', exact=True).click()
        nav.get_by_role('button', name=name, exact=True).click()
        page.locator('#workspace-content').wait_for()
        page.evaluate('scrollTo(0,0)')

    try:
        page.goto(BASE, wait_until='domcontentloaded')
        capture('sign-in-desktop')
        page.get_by_label('Email address', exact=True).fill(credentials['email'])
        password = page.get_by_label('Password', exact=True)
        password.fill(credentials['password'])
        page.get_by_role('button', name='Show password', exact=True).click()
        expect(password).to_have_attribute('type', 'text')
        page.get_by_role('button', name='Hide password', exact=True).click()
        expect(password).to_have_attribute('type', 'password')
        page.get_by_role('button', name='Sign in', exact=True).click()
        expect(page.get_by_role('status').filter(has_text='Company data loaded')).to_be_visible()
        expect(page.locator('.overview-metric').first).to_contain_text('9,87,65,432.10')
        for width in (320, 390, 768, 1024, 1440, 1920):
            page.set_viewport_size({'width': width, 'height': 1000})
            page.evaluate('scrollTo(0,0)')
            capture(f'dashboard-{width}')
            assert page.locator('.overview-metric > strong').evaluate_all('''nodes => nodes.every(n =>
                n.getBoundingClientRect().height <= parseFloat(getComputedStyle(n).lineHeight) * 1.2)'''), f'Amount wraps at {width}px'

        page.set_viewport_size({'width': 390, 'height': 844})
        trigger = page.get_by_role('button', name='Open menu', exact=True)
        trigger.click()
        drawer = page.get_by_role('dialog', name='Workspace navigation', exact=True)
        expect(drawer).to_be_visible()
        expect(drawer.get_by_role('button', name='Close', exact=True)).to_be_focused()
        assert page.locator('.main').get_attribute('inert') is not None
        assert page.evaluate('getComputedStyle(document.documentElement).overflow') == 'hidden'
        drawer.get_by_role('button', name='Close', exact=True).press('Shift+Tab')
        assert page.locator('.sidebar').evaluate('n => n.contains(document.activeElement)')
        capture('navigation-mobile')
        page.keyboard.press('Escape')
        expect(trigger).to_be_focused()
        trigger.click()
        page.locator('.mobile-backdrop').click(position={'x': 360, 'y': 300})
        expect(drawer).to_have_count(0)
        page.get_by_role('button', name='New invoice', exact=True).click()
        dialog = page.get_by_role('dialog', name='New sales invoice', exact=True)
        expect(dialog).to_be_visible()
        assert page.evaluate('getComputedStyle(document.documentElement).overflow') == 'hidden'
        before = page.evaluate('scrollY')
        page.mouse.move(2, 500); page.mouse.wheel(0, 700)
        assert page.evaluate('scrollY') == before, 'A dialog allowed background scrolling'
        for width in (320, 390, 768, 1440):
            page.set_viewport_size({'width': width, 'height': 844})
            dialog.locator('.document-form').evaluate('n => n.scrollTop = 0')
            capture(f'invoice-{width}')
            footer = dialog.locator('.modal-actions').bounding_box()
            assert footer and footer['y'] + footer['height'] <= 845, 'Save actions are outside the viewport'
        dialog.get_by_role('button', name='Close', exact=True).click()
        assert page.evaluate('getComputedStyle(document.documentElement).overflow') != 'hidden'

        for width in (390, 1440):
            page.set_viewport_size({'width': width, 'height': 1000})
            for name in ('Parties', 'Items', 'Sales invoices', 'Cash & bank', 'Day book', 'Ledger', 'Reports', 'Settings'):
                navigate(name)
                capture(f'{name.lower().replace(" & ", "-").replace(" ", "-")}-{width}')
                if name == 'Sales invoices':
                    more = page.get_by_role('button', name='More actions for '+invoice['number'], exact=True)
                    more.press('ArrowDown')
                    menu = page.get_by_role('menu', name='More actions for '+invoice['number'], exact=True)
                    expect(menu).to_be_visible()
                    expect(menu.get_by_role('menuitem').first).to_be_focused()
                    rect = menu.bounding_box()
                    assert rect and rect['x'] >= 0 and rect['x'] + rect['width'] <= width and rect['y'] + rect['height'] <= 1000
                    assert menu.evaluate('n => n.matches(":popover-open")'), 'Actions are not in the unclipped top layer'
                    capture(f'register-actions-{width}')
                    page.keyboard.press('Escape')
                    expect(more).to_be_focused()

        # Every create path must remain usable on a phone as well as a desktop.
        for width in (390, 1440):
            page.set_viewport_size({'width': width, 'height': 1000})
            for label in ('Sales invoice', 'Purchase bill', 'Payment in', 'Payment out', 'Estimate', 'Sales order', 'Proforma invoice', 'Expense', 'Purchase order', 'Credit note', 'Debit note', 'New party', 'New item'):
                page.get_by_role('button', name='Create', exact=True).click()
                if label == 'Sales invoice': capture(f'create-menu-{width}')
                page.get_by_role('menuitem', name=label, exact=True).click()
                form = page.locator('.overlay .modal').last
                expect(form).to_be_visible()
                assert form.evaluate('n => n.scrollWidth <= n.clientWidth + 1'), f'{label}: dialog overflows at {width}px'
                capture(f'entry-{label.lower().replace(" ", "-")}-{width}')
                form.get_by_role('button', name='Close', exact=True).click()
                discard = page.get_by_role('dialog', name='Discard unsaved changes?', exact=True)
                if discard.count(): discard.get_by_role('button', name='Discard draft', exact=True).click()
        navigate('Settings')
        for key in ('documents', 'accounting', 'data', 'access', 'security', 'commerce'):
            page.locator('#settings-tab-'+key).click()
            capture('settings-'+key)
        navigate('Reports')
        titles = page.locator('.report-choice strong').all_text_contents()
        for index, title in enumerate(titles):
            page.locator('.report-choice').filter(has=page.get_by_text(title, exact=True)).click()
            expect(page.locator('.reports-page')).to_be_visible()
            capture(f'report-{index+1:02d}')
            page.get_by_role('button', name='All reports', exact=True).click()
        assert not errors, errors
        violations = [r for r in reports if r['violations']]
        assert not violations, json.dumps(violations, indent=2)
        print(f'Presentation acceptance passed: {len(reports)} accessibility scans, six dashboard widths, drawer/menu keyboard controls and scroll-locked forms.', flush=True)
    finally:
        context.tracing.stop(path=str(ARTIFACTS/'presentation-trace.zip'))
        context.close(); browser.close()
