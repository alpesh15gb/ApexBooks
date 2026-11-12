"""Keyboard, accessible-tree and zoom checks on run_local.py's disposable books.

APEX_ZOOM_BROWSER_CHANNEL=chrome additionally checks actual 200%/400% browser
zoom in temporary profiles. It never reads or changes the user's profile.
"""
import json
import base64
import math
import os
import re
import tempfile
from pathlib import Path
from uuid import uuid4
from playwright.sync_api import sync_playwright, expect
from browser_support import browser_engine, launch_browser
from test_http_workflow import LiveAccountingWorkflow, BASE

if not os.environ.get('APEX_E2E_BASE'):
    raise RuntimeError('Run through run_local.py with isolated servers')
ARTIFACTS = Path(os.environ['APEX_E2E_ARTIFACTS']) / 'accessibility-deep'
ARTIFACTS.mkdir(parents=True, exist_ok=True)
AXE = Path(__file__).resolve().parents[2] / 'frontend/node_modules/axe-core/axe.min.js'
client = LiveAccountingWorkflow()
credentials = {'email': f'accessibility-{uuid4().hex}@example.invalid', 'password': 'Synthetic-accessibility-only-42'}
client.request('POST', '/api/auth/register', credentials)
client.token = client.request('POST', '/api/auth/login', credentials)['token']
company = client.request('POST', '/api/companies', {'name': 'Accessible Studio', 'tax_mode': 'unregistered', 'state_code': '27'})
root = '/api/companies/' + company['id']
invoices = [client.request('POST', root+'/records', {
    'kind': 'sales_invoice', 'name': 'Keyboard customer', 'date': '2026-11-01',
    'data': {'lines': [{'description': f'Synthetic service {i}', 'quantity': 1, 'rate': 100, 'gst_rate': 0}]},
}, key=uuid4().hex) for i in range(2)]
checks, captures, errors, zoom_results = [], [], [], []


def check(label, condition=True):
    assert condition, label
    checks.append(label)
    print('ACCESSIBILITY: '+label, flush=True)


def sign_in(page):
    page.goto(BASE, wait_until='domcontentloaded')
    page.get_by_label('Email address', exact=True).fill(credentials['email'])
    page.get_by_label('Password', exact=True).fill(credentials['password'])
    page.get_by_role('button', name='Sign in', exact=True).press('Enter')
    expect(page.get_by_role('status').filter(has_text='Company data loaded')).to_be_visible()


def navigate(page, name):
    menu = page.get_by_role('button', name='Open menu', exact=True)
    if menu.is_visible():
        menu.press('Enter')
    nav = page.locator('.sidebar')
    choice = nav.get_by_role('button', name=name, exact=True)
    if not choice.count():
        nav.get_by_role('button', name='Sales', exact=True).press('Enter')
    nav.get_by_role('button', name=name, exact=True).press('Enter')
    expect(page.locator('#workspace-content')).to_be_visible()


def create(page, name):
    trigger = page.get_by_role('button', name='Create', exact=True)
    trigger.press('ArrowDown')
    page.get_by_role('menuitem', name=name, exact=True).press('Enter')
    modal = page.locator('.overlay .modal').last
    expect(modal).to_be_visible()
    return modal


def capture(page, label):
    page.evaluate('async () => {await document.fonts.ready;await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))}')
    overflow = page.evaluate('document.documentElement.scrollWidth > innerWidth + 1')
    if overflow:
        page.screenshot(path=str(ARTIFACTS/f'{label}-overflow.png'))
        geometry = page.evaluate("({width:innerWidth,scrollWidth:document.documentElement.scrollWidth,elements:[...document.querySelectorAll('body *')].filter(n=>n.getBoundingClientRect().right>innerWidth+1 && getComputedStyle(n).position!=='fixed').slice(0,25).map(n=>({tag:n.tagName,cls:n.className,right:n.getBoundingClientRect().right,text:n.textContent.slice(0,80)}))})")
        (ARTIFACTS/f'{label}-overflow.json').write_text(json.dumps(geometry, indent=2), encoding='utf-8')
    assert not overflow, label+': horizontal page overflow'
    if not page.evaluate('!!window.axe'):
        page.add_script_tag(path=str(AXE))
    violations = page.evaluate("async () => (await axe.run(document,{runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21aa']}})).violations.map(v=>({id:v.id,impact:v.impact,nodes:v.nodes.map(n=>n.target)}))")
    captures.append({'screen': label, 'violations': violations})
    (ARTIFACTS/f'{label}-tree.yml').write_text(page.locator('body').aria_snapshot(), encoding='utf-8')
    if browser_engine() == 'chromium' or page.viewport_size is None:
        session = page.context.new_cdp_session(page)
        try:
            tree = session.send('Accessibility.getFullAXTree')
            exposed = [node for node in tree['nodes'] if not node.get('ignored')]
            (ARTIFACTS/f'{label}-browser-ax.json').write_text(json.dumps(exposed, indent=2), encoding='utf-8')
            if page.locator('.overlay .modal').count():
                assert not any(node.get('name', {}).get('value') == 'Search workspace' for node in exposed), 'Modal background is exposed in browser accessibility tree'
        finally:
            session.detach()
    if page.viewport_size is None:
        # Playwright's viewport-sized clip uses CSS dimensions at browser zoom;
        # an un-clipped CDP surface capture retains the entire physical viewport.
        session = page.context.new_cdp_session(page)
        try:
            shot = session.send('Page.captureScreenshot', {'format': 'png', 'captureBeyondViewport': False, 'fromSurface': True})
            (ARTIFACTS/f'{label}.png').write_bytes(base64.b64decode(shot['data']))
        finally:
            session.detach()
    else:
        page.screenshot(path=str(ARTIFACTS/f'{label}.png'), full_page=False)
    (ARTIFACTS/'audits.json').write_text(json.dumps(captures, indent=2), encoding='utf-8')
    assert not violations, label+': '+json.dumps(violations)


def visible_field(page, field, label):
    field.focus()
    expect(field).to_be_focused()
    assert field.evaluate('''n => {
        const r=n.getBoundingClientRect();
        return r.width>0 && r.height>0 && r.x>=0 && r.y>=0 && r.bottom<=innerHeight+1 && r.right<=innerWidth+1
            && document.elementFromPoint(r.x+r.width/2,r.y+r.height/2)===n;
    }'''), label+': focused field is clipped or obscured'


with sync_playwright() as p:
    browser = launch_browser(p)
    context = browser.new_context(viewport={'width': 1280, 'height': 960}, reduced_motion='reduce')
    context.tracing.start(screenshots=True, snapshots=True, sources=True)
    page = context.new_page()
    page.set_default_timeout(15000)
    page.on('pageerror', lambda error: errors.append(str(error)))
    try:
        sign_in(page)
        page.locator('.skip-link').focus()
        page.keyboard.press('Enter')
        expect(page.locator('#workspace-content')).to_be_focused()
        check('Skip link reaches workspace content')

        search = page.get_by_role('combobox', name='Search workspace', exact=True)
        search.fill('Settings')
        expect(search).to_have_attribute('aria-expanded', 'true')
        page.keyboard.press('ArrowDown')
        active = search.get_attribute('aria-activedescendant')
        expect(page.locator('#'+active)).to_have_attribute('role', 'option')
        page.keyboard.press('Escape')
        page.keyboard.press('Enter')
        expect(page.get_by_role('heading', name='Business overview', exact=True)).to_be_visible()
        check('Closed combobox does not activate an invisible search result')
        page.keyboard.press('ArrowDown')
        expect(search).to_have_attribute('aria-expanded', 'true')
        page.keyboard.press('Tab')
        # Clear-search is a deliberate adjacent button, followed by Create.
        if page.get_by_role('button', name='Clear workspace search').evaluate('n=>n===document.activeElement'):
            page.keyboard.press('Tab')
        expect(page.get_by_role('listbox', name='Workspace search results')).to_have_count(0)
        check('Combobox results do not become extra Tab stops')

        trigger = page.get_by_role('button', name='Create', exact=True)
        trigger.press('ArrowDown')
        expect(page.get_by_role('menuitem', name='Sales invoice', exact=True)).to_be_focused()
        page.keyboard.press('End')
        expect(page.get_by_role('menuitem', name='New item', exact=True)).to_be_focused()
        page.keyboard.press('Escape')
        expect(trigger).to_be_focused()
        check('Create menu supports arrows/Home/End and returns to its own trigger')

        editor = create(page, 'Sales invoice')
        expect(editor.get_by_role('button', name='Close', exact=True)).to_be_focused()
        page.keyboard.press('Control+k')
        check('Global search cannot take focus or open behind a modal', editor.evaluate('n=>n.contains(document.activeElement)'))
        expect(page.get_by_role('listbox', name='Workspace search results')).to_have_count(0)
        customer = editor.get_by_label('Customer / description', exact=True)
        customer.fill('Keyboard customer')
        page.keyboard.press('Escape')
        confirm = page.get_by_role('dialog', name='Discard unsaved changes?', exact=True)
        expect(confirm).to_be_visible()
        confirm.get_by_role('button', name='Close', exact=True).press('Shift+Tab')
        check('Nested discard dialog keeps keyboard focus inside', confirm.evaluate('n=>n.contains(document.activeElement)'))
        page.keyboard.press('Escape')
        expect(customer).to_be_focused()
        check('Closing a nested confirmation restores the previous editor field')
        editor.get_by_role('button', name='Add item / service', exact=True).press('Enter')
        expect(editor.get_by_label('Item 2 description', exact=True)).to_be_focused()
        editor.get_by_role('button', name='Remove item 2', exact=True).press('Enter')
        expect(editor.get_by_label('Item 1 description', exact=True)).to_be_focused()
        check('Adding/removing invoice rows keeps focus on a remaining item field')
        editor.get_by_label('Item 1 description', exact=True).fill('Keyboard reviewed service')
        editor.get_by_label('Item 1 rate', exact=True).fill('100')
        def reject_save(route):
            if route.request.method == 'POST':
                route.fulfill(status=422, content_type='application/json', body=json.dumps({'detail': 'Synthetic validation: review this document before saving.'}))
            else:
                route.continue_()
        page.route('**/api/companies/*/records', reject_save)
        editor.get_by_role('button', name='Save invoice', exact=True).press('Enter')
        expect(editor.get_by_role('alert')).to_contain_text('Synthetic validation')
        capture(page, 'invoice-error-announcement')
        check('Asynchronous invoice validation is exposed as an alert')
        page.unroute('**/api/companies/*/records', reject_save)
        page.keyboard.press('Escape')
        page.get_by_role('button', name='Discard draft', exact=True).press('Enter')
        expect(trigger).to_be_focused()
        check('Discarding a menu-opened editor restores the Create trigger')

        payment = create(page, 'Payment in')
        payment.get_by_role('combobox', name='Invoice or bill', exact=True).select_option(invoices[0]['id'])
        payment.get_by_role('button', name='Add another document', exact=True).press('Enter')
        second = payment.get_by_role('group', name='Document 2 allocation', exact=True)
        expect(second.get_by_role('combobox')).to_be_focused()
        second.get_by_role('button', name='Remove document 2', exact=True).press('Enter')
        expect(payment.get_by_role('combobox', name='Invoice or bill', exact=True)).to_be_focused()
        capture(page, 'payment-allocation-keyboard')
        check('Payment allocations have contextual names and preserve keyboard focus')
        page.keyboard.press('Escape')
        page.get_by_role('button', name='Discard draft', exact=True).press('Enter')

        master = create(page, 'New party')
        expect(page.get_by_role('dialog', name='New party', exact=True)).to_be_visible()
        master.get_by_label('Party name', exact=True).fill('   ')
        master.get_by_role('button', name='Save party', exact=True).press('Enter')
        expect(master.get_by_role('alert')).to_contain_text('Enter a party name')
        master.get_by_label('Party name', exact=True).fill('Unposted keyboard party')
        page.keyboard.press('Escape')
        expect(master.get_by_role('alert').filter(has_text='Discard unsaved changes?')).to_be_visible()
        expect(master.get_by_role('button', name='Keep editing', exact=True)).to_be_focused()
        master.get_by_role('button', name='Keep editing', exact=True).press('Enter')
        expect(master.get_by_label('Party name', exact=True)).to_have_value('Unposted keyboard party')
        expect(master.get_by_label('Party name', exact=True)).to_be_focused()
        capture(page, 'master-name-and-discard')
        page.keyboard.press('Escape')
        master.get_by_role('button', name='Discard changes', exact=True).press('Enter')
        check('Master editor names its task, announces invalid names and protects unsaved changes')

        navigate(page, 'Settings')
        tabs = page.get_by_role('tablist', name='Settings categories')
        expect(tabs).to_be_visible()
        check('Every settings tab references an existing panel', tabs.get_by_role('tab').evaluate_all("nodes=>nodes.every(n=>document.getElementById(n.getAttribute('aria-controls')))"))
        company_tab = tabs.get_by_role('tab', name='Company', exact=True)
        company_tab.focus();page.keyboard.press('ArrowDown')
        documents = tabs.get_by_role('tab', name='Documents & branding', exact=True)
        expect(documents).to_be_focused();expect(documents).to_have_attribute('aria-selected', 'true')
        page.get_by_role('button', name='Transaction prefixes', exact=True).press('Enter')
        check('Settings jump moves focus into the requested section', page.locator('#setting-prefixes').evaluate('n=>n.contains(document.activeElement)'))
        check('Reduced-motion mode disables smooth CSS scrolling', page.evaluate("matchMedia('(prefers-reduced-motion: reduce)').matches && getComputedStyle(document.documentElement).scrollBehavior !== 'smooth'"))
        capture(page, 'settings-keyboard-destination')
        page.get_by_label('Find a setting', exact=True).fill('zzzz-no-setting')
        expect(page.get_by_role('status').filter(has_text='No matching settings')).to_be_visible()
        page.get_by_label('Find a setting', exact=True).fill('')

        navigate(page, 'Reports')
        def reject_report(route):
            route.fulfill(status=503, content_type='application/json', body=json.dumps({'detail': 'Synthetic report unavailable. Please retry.'}))
        page.route('**/api/companies/*/reports/summary?*', reject_report)
        page.get_by_role('button', name=re.compile('^Transaction summary')).press('Enter')
        expect(page.get_by_role('alert')).to_contain_text('Synthetic report unavailable')
        capture(page, 'report-error-announcement')
        check('Report failures are announced instead of silently replacing the table')
        page.unroute('**/api/companies/*/reports/summary?*', reject_report)
        page.get_by_role('combobox', name='Report', exact=True).select_option('ageing')
        expect(page.get_by_role('heading', name='Open documents', exact=True)).to_be_visible()
        page.set_viewport_size({'width': 390, 'height': 844})
        detail_table = page.locator('.ageing-page .register').last.get_by_role('table')
        expect(detail_table.get_by_role('columnheader')).to_have_count(7)
        capture(page, 'mobile-ageing-table-relations')
        check('Mobile report cards retain their table column headers in the accessible tree')

        # Reflow in all engines. The optional profile-based pass below uses actual
        # browser zoom as well, rather than treating CSS transforms as zoom.
        for width, height in [(640, 480), (320, 240)]:
            page.set_viewport_size({'width': width, 'height': height})
            navigate(page, 'Dashboard')
            capture(page, f'reflow-dashboard-{width}')
            invoice = create(page, 'Sales invoice')
            expect(invoice.get_by_role('button', name='Save invoice', exact=True)).to_be_visible()
            visible_field(page, invoice.get_by_label('Customer / description', exact=True), f'Customer at {width}px')
            visible_field(page, invoice.get_by_label('Item 1 rate', exact=True), f'Item rate at {width}px')
            invoice.get_by_role('button', name='Close', exact=True).press('Shift+Tab')
            check(f'Invoice keyboard actions remain reachable at {width} CSS pixels', invoice.evaluate('n=>n.contains(document.activeElement)'))
            capture(page, f'reflow-invoice-{width}')
            page.keyboard.press('Escape')
        check('No uncaught JavaScript errors during accessibility journeys', not errors)
    except BaseException:
        page.screenshot(path=str(ARTIFACTS/'failure.png'))
        (ARTIFACTS/'failure.html').write_text(page.content(), encoding='utf-8')
        raise
    finally:
        context.tracing.stop(path=str(ARTIFACTS/'keyboard-trace.zip'))
        context.close();browser.close()

    zoom_channel = os.environ.get('APEX_ZOOM_BROWSER_CHANNEL')
    if zoom_channel:
        if zoom_channel not in {'chrome', 'msedge'}:
            raise RuntimeError('Choose a locally installed Chrome or Edge channel for real zoom')
        for zoom in (2, 4):
            with tempfile.TemporaryDirectory(prefix='apex-accessibility-zoom-') as directory:
                profile = Path(directory)/'Default';profile.mkdir()
                # Chromium's profile zoom preference; x is the default partition.
                # Verified against innerWidth and devicePixelRatio below.
                (profile/'Preferences').write_text(json.dumps({'partition': {'default_zoom_level': {'x': math.log(zoom)/math.log(1.2)}}}))
                context = p.chromium.launch_persistent_context(directory, channel=zoom_channel, headless=True,
                    no_viewport=True, reduced_motion='reduce', args=['--window-size=1280,960'])
                page = context.pages[0];page.set_default_timeout(15000)
                try:
                    sign_in(page)
                    metrics = page.evaluate('({width:innerWidth,height:innerHeight,dpr:devicePixelRatio,outerWidth})')
                    assert abs(metrics['dpr']-zoom) < .01 and metrics['width'] <= 1280/zoom
                    zoom_results.append({'factor': zoom, 'metrics': metrics, 'channel': zoom_channel})
                    for name in ('Dashboard', 'Reports', 'Settings'):
                        navigate(page, name)
                        capture(page, f'browser-zoom-{zoom*100}-{name.lower()}')
                    editor = create(page, 'Sales invoice')
                    visible_field(page, editor.get_by_label('Customer / description', exact=True), f'Customer at {zoom*100}%')
                    visible_field(page, editor.get_by_label('Item 1 rate', exact=True), f'Item rate at {zoom*100}%')
                    capture(page, f'browser-zoom-{zoom*100}-invoice')
                    editor.get_by_role('button', name='Close', exact=True).press('Shift+Tab')
                    check(f'Actual {zoom*100}% zoom retains keyboard access to invoice actions', editor.evaluate('n=>n.contains(document.activeElement)'))
                    page.keyboard.press('Escape')
                finally:
                    context.close()

result = {'passed': True, 'engine': browser_engine(), 'checks': checks, 'screens': len(captures),
          'browser_zoom': zoom_results, 'spoken_screen_reader_tested': False, 'errors': errors}
(ARTIFACTS/'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
print('ACCESSIBILITY: all focused checks passed', flush=True)
