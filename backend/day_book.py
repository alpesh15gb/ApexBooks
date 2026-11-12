"""Day book (Vyapar / MyBillBook style): every transaction dated one day, with the cash and bank it moved."""
from datetime import date
from decimal import Decimal
from fastapi import Depends
from sqlalchemy import select, func, or_
from sqlalchemy.orm import Session

NON_TRANSACTION_KINDS = {'party', 'item', 'bank_account', 'recurring_template',
                         'vyapar_backup_archive', 'document_branding', 'restore_marker'}
SALES = {'sales_invoice', 'pos'}
PURCHASES = {'purchase_bill'}


def install(app, m):
    @app.get('/api/companies/{company_id}/day-book')
    def day_book(company_id: str, day: date | None = None, user: m.User = Depends(m.current_user), session: Session = Depends(m.db)):
        from business_calendar import business_today
        m.company_for(company_id, user, session)
        day = day or business_today()
        money_ids = set(session.scalars(select(m.LedgerAccount.id).where(
            m.LedgerAccount.company_id == company_id, m.LedgerAccount.code.in_(['SYS-CASH', 'SYS-BANK']))))
        money_ids |= set(session.scalars(select(m.BankAccount.ledger_account_id).where(m.BankAccount.company_id == company_id)))
        # Cash + bank movement per journal dated today, keyed to the record it posts when there is one.
        movement = {}
        if money_ids:
            query = (select(m.Journal, m.JournalLine, m.RecordPosting.record_id)
                .join(m.JournalLine, (m.JournalLine.journal_id == m.Journal.id) & (m.JournalLine.company_id == m.Journal.company_id))
                .outerjoin(m.RecordPosting, (m.RecordPosting.journal_id == m.Journal.id) & (m.RecordPosting.company_id == m.Journal.company_id))
                .where(m.Journal.company_id == company_id, m.Journal.date == day, m.JournalLine.account_id.in_(money_ids)))
            for journal, line, record_id in session.execute(query):
                key = record_id or journal.id
                movement[key] = movement.get(key, Decimal('0')) + line.debit - line.credit
        posted = set(session.scalars(select(m.RecordPosting.record_id).where(m.RecordPosting.company_id == company_id)))
        rows = []
        records = session.scalars(select(m.Record).where(m.Record.company_id == company_id, m.Record.date == day,
            m.Record.kind.not_in(NON_TRANSACTION_KINDS)).order_by(m.Record.kind, m.Record.number))
        for r in records:
            moved = movement.pop(r.id, Decimal('0'))
            rows.append({'id': r.id, 'kind': r.kind, 'number': r.number, 'name': r.name, 'amount': str(r.amount),
                'posted': r.id in posted, 'cancelled': bool(r.data.get('cancelled')),
                'money_in': str(max(moved, Decimal('0'))), 'money_out': str(max(-moved, Decimal('0')))})
        # Discover all journals without a current document posting, not only
        # those touching cash/bank. Linked document journals are already rows.
        linked_journals = select(m.RecordPosting.journal_id).where(m.RecordPosting.company_id == company_id)
        journals = list(session.scalars(select(m.Journal).where(m.Journal.company_id == company_id,
            m.Journal.date == day, m.Journal.id.not_in(linked_journals)).order_by(m.Journal.reference, m.Journal.id)))
        journal_ids = [journal.id for journal in journals]
        journal_totals = {jid:(debit,credit) for jid,debit,credit in session.execute(
            select(m.JournalLine.journal_id,func.sum(m.JournalLine.debit),func.sum(m.JournalLine.credit))
            .where(m.JournalLine.company_id == company_id,m.JournalLine.journal_id.in_(journal_ids)).group_by(m.JournalLine.journal_id))} if journal_ids else {}
        reversed_ids = set()
        if journal_ids:
            for reversal in session.scalars(select(m.JournalReversal).where(m.JournalReversal.company_id == company_id,
                or_(m.JournalReversal.original_id.in_(journal_ids),m.JournalReversal.reversal_id.in_(journal_ids)))):
                reversed_ids.update((reversal.original_id,reversal.reversal_id))
        for journal in journals:
            moved = movement.get(journal.id, Decimal('0'))
            debit, credit = journal_totals.get(journal.id,(Decimal('0'),Decimal('0')))
            label = journal.memo or journal.reference
            if journal.id in reversed_ids and journal.reference.startswith(('AUTO:', 'CANCEL:')):
                origin = session.scalar(select(m.Record).where(m.Record.company_id == company_id, m.Record.id == journal.reference.split(':', 1)[1]))
                if origin is not None and origin.data.get('cancelled'): label = f"Cancelled · {origin.number or origin.name}"
            rows.append({'id': journal.id, 'kind': 'journal', 'number': journal.reference, 'name': label, 'amount': str(debit),
                'debit_total':str(debit),'credit_total':str(credit),'posted': True, 'cancelled': False,
                'money_in': str(max(moved, Decimal('0'))), 'money_out': str(max(-moved, Decimal('0')))})
        live = [row for row in rows if row['posted'] and not row['cancelled']]
        total = lambda kinds: str(sum((Decimal(row['amount']) for row in live if row['kind'] in kinds), Decimal('0')))
        money_in = sum((Decimal(row['money_in']) for row in rows), Decimal('0'))
        money_out = sum((Decimal(row['money_out']) for row in rows), Decimal('0'))
        return {'day': day.isoformat(), 'rows': rows, 'count': len(rows),
            'totals': {'sales': total(SALES), 'purchases': total(PURCHASES), 'expenses': total({'expense'}),
                'money_in': str(money_in), 'money_out': str(money_out), 'net': str(money_in - money_out)}}
