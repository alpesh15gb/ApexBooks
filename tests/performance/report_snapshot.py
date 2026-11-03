"""Synthetic SQLite query/timing comparison; never uses an external API or database.

Run with the backend development dependencies installed:
    python tests/performance/report_snapshot.py
Timings are local CPU/SQLite evidence, not production or native-device latency.
"""
import os,sys,time,statistics
from pathlib import Path
if os.environ.get('ACCEPTANCE_BASE'):
    raise SystemExit('Unset ACCEPTANCE_BASE; this benchmark uses isolated synthetic SQLite only')
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'backend'))
import test_completion,main
from datetime import date
from decimal import Decimal as D
from sqlalchemy.orm import Session
from sqlalchemy import select,event
assert main.engine.dialect.name=='sqlite'
T=test_completion.CompletionTest();c,h,b=T.client_context();cid=b.rsplit('/',1)[-1];accounts=[]
for code,cat in [('QA-CASH','asset'),('QA-EQUITY','equity')]:accounts.append(c.post(b+'/accounts',headers=h,json={'code':code,'name':code,'category':cat}).json()['id'])
with Session(main.engine) as s:
 uid=s.get(main.Company,cid).owner_id
 for i in range(2000):
  j=main.Journal(company_id=cid,date=date(2026,3 if i%2 else 4,2),reference='BENCH'+str(i),memo='Synthetic',created_by=uid);s.add(j);s.flush()
  for aid,dr,cr in [(accounts[0],D('123.45'),D(0)),(accounts[1],D(0),D('123.45'))]:s.add(main.JournalLine(company_id=cid,journal_id=j.id,account_id=aid,debit=dr,credit=cr))
 s.commit()
def old(s):
 results=[]
 for start in (date(2026,4,1),date(1900,1,1)):
  ac=list(s.scalars(select(main.LedgerAccount).where(main.LedgerAccount.company_id==cid).order_by(main.LedgerAccount.code)));tot={a.id:D(0) for a in ac}
  rows=s.execute(select(main.JournalLine.account_id,main.JournalLine.debit,main.JournalLine.credit).join(main.Journal,(main.Journal.id==main.JournalLine.journal_id)&(main.Journal.company_id==main.JournalLine.company_id)).where(main.Journal.company_id==cid,main.Journal.date>=start,main.Journal.date<=date(2026,4,30))).all()
  for aid,dr,cr in rows:tot[aid]+=dr-cr
  results.append(tot)
 return results
for label,fn in [('old',old),('new',lambda s:main.ledger_snapshot(cid,date(2026,4,1),date(2026,4,30),s,closing_from=date(1900,1,1))[1:])]:
 times=[];counts=[]
 for _ in range(7):
  queries=[]
  def observe(*a):queries.append(a[2])
  event.listen(main.engine,'before_cursor_execute',observe)
  with Session(main.engine) as s:
   before=time.perf_counter();result=fn(s);times.append((time.perf_counter()-before)*1000)
  event.remove(main.engine,'before_cursor_execute',observe);counts.append(len(queries))
  assert result[0][accounts[0]]==D('123450.00') and result[1][accounts[0]]==D('246900.00')
 print(label,'median_ms',round(statistics.median(times),2),'queries',counts,'ledger_rows',6000 if label=='old' else 4000)
T.doCleanups()
