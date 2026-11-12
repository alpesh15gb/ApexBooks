"""Compile the actual DayBook status/reference expressions, not Compose controls."""
from pathlib import Path
import argparse,sys,tempfile
root=Path(__file__).resolve().parents[3];sys.path.insert(0,str(root/'native/tests'))
from kotlin_toolchain import add_arguments,run_proof
p=argparse.ArgumentParser();add_arguments(p);args=p.parse_args()
s=(root/'native/android/app/src/main/java/com/apexbooks/accounting/DayBookScreen.kt').read_text()
status=s.split('val state = ',1)[1].split('\n',1)[0]
reference=s.split('Text(listOf(',1)[1].split(', fontWeight',1)[0]
fixture=r'''
class Row(val status:String,val posted:Boolean=false,val cancelled:Boolean=false,val display:String="",val number:String="REF"){fun s(key:String)=when(key){"status"->status;"display_number"->display;"number"->number;else->"Party"};fun optBoolean(key:String)=if(key=="posted")posted else cancelled}
fun state(row:Row,kind:String="estimate")=STATUS
fun label(row:Row)=listOf(REFERENCE
fun main(){check(state(Row("converted"))==" · converted");check(state(Row("converted",cancelled=true))==" · cancelled");check(state(Row("non_posting"))==" · non-posting");check(state(Row(""))==" · unposted");check(state(Row("posted",posted=true))=="");check(label(Row("",display="Original posting · INV1",number="AUTO:id"))=="Original posting · INV1 · Party");check(label(Row(""))=="REF · Party");println("PASS seven actual Android Day book status/reference expressions")}
'''.replace('STATUS',status).replace('REFERENCE',reference)
with tempfile.TemporaryDirectory(prefix='apex-daybook-label-') as d:
 d=Path(d);(d/'Proof.kt').write_text(fixture);run_proof(args,[d/'Proof.kt'],d)
