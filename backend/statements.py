"""Formatted Profit & Loss and Balance Sheet statements derived only from posted ledger journals."""
from decimal import Decimal
from datetime import date as DateType
from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

ZERO = Decimal('0')

# System account code -> statement group. Anything else is classified by its ledger category.
PL_GROUP = {
    'SYS-SALES': 'sales', 'SYS-COGS': 'cost_of_sales', 'SYS-PURCHASE': 'cost_of_sales',
    'SYS-STOCK-GAIN': 'other_income', 'SYS-STOCK-LOSS': 'operating', 'SYS-EXPENSE': 'operating', 'SYS-ROUND': 'operating',
}
BS_GROUP = {
    'SYS-CASH': 'cash_bank', 'SYS-BANK': 'cash_bank', 'SYS-AR': 'receivables', 'SYS-INVENTORY': 'inventory',
    'SYS-SUPP-ADV': 'advances', 'SYS-SUPP-CREDIT': 'advances',
    'SYS-IN-CGST': 'tax_assets', 'SYS-IN-SGST': 'tax_assets', 'SYS-IN-IGST': 'tax_assets',
    'SYS-AP': 'payables', 'SYS-CUST-ADV': 'customer_balances', 'SYS-CUST-CREDIT': 'customer_balances',
    'SYS-OUT-CGST': 'tax_liabilities', 'SYS-OUT-SGST': 'tax_liabilities', 'SYS-OUT-IGST': 'tax_liabilities',
    'SYS-OPENING': 'capital',
}
ASSET_SECTIONS = [('cash_bank', 'Cash and bank'), ('receivables', 'Accounts receivable'), ('inventory', 'Inventory'),
                  ('advances', 'Advances and supplier credits'), ('tax_assets', 'Input GST (pending review)'), ('other_assets', 'Other assets')]
LIABILITY_SECTIONS = [('payables', 'Accounts payable'), ('customer_balances', 'Customer advances and credits'),
                      ('tax_liabilities', 'Output GST payable'), ('other_liabilities', 'Other liabilities')]


def money(value):
    return str(value.quantize(Decimal('0.01')))


def install(app, m):
    def build(company_id, from_date, to_date, user, session):
        m.company_for(company_id, user, session)
        if from_date > to_date:
            raise HTTPException(422, 'Start date must be before end date')
        accounts, period = m.account_movements(company_id, from_date, to_date, session)
        _, cumulative = m.account_movements(company_id, DateType(1900, 1, 1), to_date, session)

        def line(account, amount):
            return {'code': account.code, 'name': account.name, 'amount': money(amount)}

        # ---- Profit & Loss (period movements; income is credit-positive, costs debit-positive)
        pl = {key: [] for key in ('sales', 'cost_of_sales', 'other_income', 'operating')}
        for a in accounts:
            if a.category not in {'income', 'expense'}:
                continue
            group = PL_GROUP.get(a.code) or ('other_income' if a.category == 'income' else 'operating')
            amount = -period[a.id] if a.category == 'income' else period[a.id]
            # Contra entries that net to income (e.g. stock loss) are expenses; keep their natural sign.
            if amount != 0:
                pl[group].append(line(a, amount))
        total = lambda items: sum((Decimal(i['amount']) for i in items), ZERO)
        sales, cost, other_income, operating = (total(pl[k]) for k in ('sales', 'cost_of_sales', 'other_income', 'operating'))
        gross = sales - cost
        net = gross + other_income - operating
        profit_loss = {
            'revenue': {'lines': pl['sales'], 'total': money(sales)},
            'cost_of_sales': {'lines': pl['cost_of_sales'], 'total': money(cost)},
            'gross_profit': money(gross),
            'gross_margin_percent': money(gross * 100 / sales) if sales else None,
            'other_income': {'lines': pl['other_income'], 'total': money(other_income)},
            'operating_expenses': {'lines': pl['operating'], 'total': money(operating)},
            'net_profit': money(net),
        }

        # ---- Balance sheet at to_date (cumulative)
        assets = {key: [] for key, _ in ASSET_SECTIONS}
        liabilities = {key: [] for key, _ in LIABILITY_SECTIONS}
        capital = []
        profit_to_date = ZERO
        for a in accounts:
            balance = cumulative[a.id]
            if a.category == 'income':
                profit_to_date += -balance
            elif a.category == 'expense':
                profit_to_date -= balance
            elif balance == 0:
                continue
            elif a.category == 'asset':
                group = BS_GROUP.get(a.code) or ('cash_bank' if a.code.startswith('BANK-') else 'other_assets')
                assets[group].append(line(a, balance))
            elif a.category == 'liability':
                liabilities[BS_GROUP.get(a.code) or 'other_liabilities'].append(line(a, -balance))
            elif a.category == 'equity':
                capital.append(line(a, -balance))
        profit_before = profit_to_date - net  # accumulated result before this period (positive = profit)
        section = lambda catalogue, store: [{'key': key, 'label': label, 'lines': store[key], 'total': money(total(store[key]))}
                                           for key, label in catalogue if store[key]]
        asset_sections = section(ASSET_SECTIONS, assets)
        liability_sections = section(LIABILITY_SECTIONS, liabilities)
        total_assets = sum((Decimal(s['total']) for s in asset_sections), ZERO)
        total_liabilities = sum((Decimal(s['total']) for s in liability_sections), ZERO)
        capital_total = total(capital)
        equity_lines = capital + ([{'code': '', 'name': 'Retained profit brought forward', 'amount': money(profit_before)}] if profit_before != 0 else []) \
            + [{'code': '', 'name': 'Profit for the period', 'amount': money(net)}]
        total_equity = capital_total + profit_before + net
        balance_sheet = {
            'as_of': to_date.isoformat(),
            'assets': {'sections': asset_sections, 'total': money(total_assets)},
            'liabilities': {'sections': liability_sections, 'total': money(total_liabilities)},
            'equity': {'lines': equity_lines, 'total': money(total_equity)},
            'total_liabilities_and_equity': money(total_liabilities + total_equity),
            'difference': money(total_assets - total_liabilities - total_equity),
        }
        company = m.company_for(company_id, user, session)
        return {'company': company.name, 'from_date': from_date.isoformat(), 'to_date': to_date.isoformat(),
                'basis': 'Posted ledger journals. Cancelled documents are reversed. Input GST is shown as an asset pending review.',
                'profit_loss': profit_loss, 'balance_sheet': balance_sheet}

    @app.get('/api/companies/{company_id}/reports/statements')
    def statements(company_id: str, from_date: DateType, to_date: DateType, user=Depends(m.current_user), session: Session = Depends(m.db)):
        return build(company_id, from_date, to_date, user, session)

    @app.get('/api/companies/{company_id}/reports/statements.{fmt}')
    def export_statements(company_id: str, fmt: str, from_date: DateType, to_date: DateType, user=Depends(m.current_user), session: Session = Depends(m.db)):
        data = build(company_id, from_date, to_date, user, session)
        pl, bs = data['profit_loss'], data['balance_sheet']
        rows = []

        def head(text):
            rows.append([text, ''])

        def lines(items):
            for item in items:
                rows.append(['    ' + item['name'], item['amount']])

        def grouped(sections):
            for s in sections:
                rows.append(['  ' + s['label'], s['total']])
                if len(s['lines']) > 1:
                    lines(s['lines'])

        head('PROFIT AND LOSS · %s to %s' % (data['from_date'], data['to_date']))
        head('Revenue'); lines(pl['revenue']['lines']); rows.append(['Total revenue', pl['revenue']['total']])
        head('Cost of sales'); lines(pl['cost_of_sales']['lines']); rows.append(['Total cost of sales', pl['cost_of_sales']['total']])
        rows.append(['GROSS PROFIT', pl['gross_profit']])
        if pl['other_income']['lines']:
            head('Other income'); lines(pl['other_income']['lines']); rows.append(['Total other income', pl['other_income']['total']])
        head('Operating expenses'); lines(pl['operating_expenses']['lines']); rows.append(['Total operating expenses', pl['operating_expenses']['total']])
        rows.append(['NET PROFIT' if Decimal(pl['net_profit']) >= 0 else 'NET LOSS', pl['net_profit']])
        rows.append(['', ''])
        head('BALANCE SHEET · as of %s' % bs['as_of'])
        head('Assets'); grouped(bs['assets']['sections']); rows.append(['TOTAL ASSETS', bs['assets']['total']])
        head('Liabilities'); grouped(bs['liabilities']['sections']); rows.append(['TOTAL LIABILITIES', bs['liabilities']['total']])
        head('Equity'); lines(bs['equity']['lines']); rows.append(['TOTAL EQUITY', bs['equity']['total']])
        rows.append(['TOTAL LIABILITIES AND EQUITY', bs['total_liabilities_and_equity']])
        company = m.company_for(company_id, user, session)
        return m.export_table(company.name, 'Profit and loss and balance sheet %s to %s' % (from_date, to_date), ['Particulars', 'Amount'], rows, fmt, 'financial-statements')
