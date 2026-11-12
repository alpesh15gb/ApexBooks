"""Use retained posting evidence; never infer historic order from random IDs."""
from datetime import datetime, timezone
from sqlalchemy import select

ORDERING_NOTE = ('Within each date, entries with recorded posting timestamps appear in posting order. '
                'Entries without timestamps follow in reference order; their historical entry sequence is unknown. '
                'Same-day intermediate balances depend on this ordering; closing balances are unchanged.')


def timestamp(value):
    try:
        result=datetime.fromisoformat(str(value).replace('Z','+00:00'))
        return result.replace(tzinfo=timezone.utc) if result.tzinfo is None else result.astimezone(timezone.utc)
    except (ValueError,TypeError):return None


def order_rows(m,session,company_id,rows):
    entity_ids=set(rows) | {row.get('_record_id') for row in rows.values() if row.get('_record_id')}
    events={}
    for event in session.scalars(select(m.AuditEvent).where(m.AuditEvent.company_id==company_id,m.AuditEvent.entity_id.in_(entity_ids))):
        action,details=event.action,event.details
        for _ in range(20):
            if action!='backup.source_event' or not isinstance(details,dict):break
            action,details=details.get('source_action'),details.get('source_details')
        if action in {'journal.created','record.cancelled'}:
            key=(event.entity_id,action);value=timestamp(event.occurred_at)
            if value is not None and (key not in events or value<events[key]):events[key]=value
    for row in rows.values():
        value=events.get((row.get('_record_id'),'record.cancelled')) if row.get('_reversal') else timestamp(row.get('_created_at'))
        value=value or events.get((row['id'],'journal.created'))
        row['posting_timestamp']=value.isoformat() if value else None
    return sorted(rows.values(),key=lambda row:(row['date'],row['posting_timestamp'] is None,row['posting_timestamp'] or '',row['reference'],row['kind'],row['description'],row['cash'],row['bank'],row['id']))
