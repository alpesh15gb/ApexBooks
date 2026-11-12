"""Stable statement presentation from retained entry timestamps, without changing books."""
from cash_book_order import timestamp
ORDERING_NOTE = ('Within each date, entries with recorded entry timestamps appear in that order. '
                 'Entries without timestamps follow in reference order; their historical entry sequence is unknown. '
                 'Reference/type/party/amount break timestamp ties. Same-day intermediate balances depend on this ordering; closing balances are unchanged.')

def posting_timestamp(record):
    value=timestamp((record.data or {}).get('created_at'))
    return value.isoformat() if value else None

def record_key(record):
    stamp=posting_timestamp(record);data=record.data or {}
    return (record.date,stamp is None,stamp or '',record.number or '',record.kind,record.name,str(record.amount),
            str(data.get('unallocated_credit',0)),str(data.get('payment_kind','')),record.id)
