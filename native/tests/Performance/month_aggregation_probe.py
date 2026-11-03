# Algorithm-only synthetic probe: not Android/.NET/native rendering timings.
from decimal import Decimal
from time import perf_counter
from statistics import median
import json
months=[f'2026-{m:02}' for m in range(4,12)]
kinds=['sales_invoice','pos','credit_note','purchase_bill','debit_note','expense','party','item']
rows=[{'posted':i%7!=0,'date':f'2026-{i%12+1:02}-{i%28+1:02}','kind':kinds[i%8],'amount':Decimal(i%10000)/100} for i in range(50000)]
start,end='2026-04-01','2026-11-03'
def amount(r):
 k=r['kind'];v=r['amount'];return(v if k in ('sales_invoice','pos') else -v if k=='credit_note' else Decimal(0),v if k=='purchase_bill' else -v if k=='debit_note' else Decimal(0))
def old():
 out={};visits=0
 for m in months:
  matching=[]
  for r in rows:
   visits+=1
   if r['posted'] and start<=r['date']<=end and r['date'].startswith(m):matching.append(r)
  out[m]=(sum((amount(r)[0] for r in matching),Decimal(0)),sum((amount(r)[1] for r in matching),Decimal(0)))
 return out,visits
def proposed():
 out={m:(Decimal(0),Decimal(0)) for m in months};visits=0
 for r in rows:
  visits+=1
  if not r['posted'] or not start<=r['date']<=end:continue
  m=r['date'][:7]
  if m not in out:continue
  a,b=amount(r);x,y=out[m];out[m]=(x+a,y+b)
 return out,visits
assert old()[0]==proposed()[0]
result={'rows':len(rows),'months':len(months),'exact_decimal_totals_equal':True,'warning':'Python algorithm proxy only; not native UI timing'}
for label,fn in [('current_repeated_scan',old),('proposed_single_scan',proposed)]:
 times=[]
 for _ in range(7):
  t=perf_counter();_,visits=fn();times.append((perf_counter()-t)*1000)
 result[label]={'record_predicate_visits':visits,'median_ms':round(median(times),2)}
print(json.dumps(result,indent=2))
