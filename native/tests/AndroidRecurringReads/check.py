from pathlib import Path
import argparse,sys,tempfile
root=Path(__file__).resolve().parents[3];sys.path.insert(0,str(root/'native/tests'))
from kotlin_toolchain import add_arguments,run_proof
p=argparse.ArgumentParser();add_arguments(p);args=p.parse_args()
s=(root/'native/android/app/src/main/java/com/apexbooks/accounting/RecurringTools.kt').read_text();hub=s.split('@Composable private fun RecurringHub(',1)[1].split('@Composable private fun RecurringCreate(',1)[0]
a=hub.index('LaunchedEffect(');b=hub.index('{',a);depth=1;end=b+1
while depth:
 if hub[end]=='{':depth+=1
 if hub[end]=='}':depth-=1
 end+=1
body=hub[b+1:end-1].replace('return@LaunchedEffect','return')
detail=s[s.index('suspend fun openRecurringSchedule('):s.index('@Composable private fun RecurringHub(')]
assert 'LaunchedEffect(cid,revision,access,vm.recordsReady)' in hub
assert 'vm.canRead(cid,access)&&vm.tool=="recurring"' in hub
fixture=r'''
import kotlinx.coroutines.*
fun encode(value:String)=value
class ApiFailure(val status:Int,message:String="denied"):Exception(message)
class JSONArray(val rows:List<JSONObject>){fun objects()=rows}
class JSONObject(val name:String="schedule"){fun a(key:String)=JSONArray(listOf(JSONObject("loaded")));fun s(key:String)=name}
fun JSONObject.s(key:String)=name
class Api{var signedIn=true;var session=0;var calls=0;var read:suspend()->JSONObject={JSONObject()};fun company(cid:String,path:String)=cid+path;suspend fun request(path:String):Any{calls++;return read()}}
class AppModel{val api=Api();var companyId="a";var generation=0;var epoch=0;var recordsReady=true;var tool="recurring";var toolData:JSONObject?=null;var failures=0;fun workspaceStamp()=generation;fun inWorkspace(cid:String,stamp:Int)=cid==companyId&&stamp==generation;fun readStamp()=generation.toLong()*1000+epoch;fun canRead(cid:String,stamp:Long)=recordsReady&&cid==companyId&&readStamp()==stamp;fun failure(e:Exception){failures++};fun captureReadOwner(tool:String,data:JSONObject?):()->Boolean{val id=companyId;val stamp=readStamp();val session=api.session;return{api.signedIn&&api.session==session&&canRead(id,stamp)&&this.tool==tool&&toolData===data}}}
class Screen(val vm:AppModel){val cid=vm.companyId;val stamp=vm.generation;val access=vm.readStamp();var rows:List<JSONObject>?=listOf(JSONObject("previous"));var failure="";var dueIds=emptySet<String>();var businessDate="previous date";var timezone="previous timezone";suspend fun load(){BODY}}
DETAIL
fun main()=runBlocking{
 val vm=AppModel();val screen=Screen(vm);val gate=CompletableDeferred<Unit>();vm.api.read={gate.await();JSONObject()};val task=async{screen.load()};yield();vm.epoch++;vm.recordsReady=false;gate.complete(Unit);task.await();check(screen.rows==null){"Late recurring list published after access denial"}
 val denied=Screen(vm);denied.load();check(denied.rows==null&&denied.businessDate==""&&denied.timezone==""&&denied.failure.isNotBlank())
 vm.recordsReady=true;val current=Screen(vm);current.load();check(current.rows!!.size==1)
 for(mode in listOf("company","session","tool","access"))for(fails in listOf(false,true)){
  val owner=AppModel();val f=Screen(owner);val done=CompletableDeferred<Unit>();owner.api.read={done.await();if(fails)throw ApiFailure(503,"old error");JSONObject()};val pending=async{f.load()};yield();when(mode){"company"->owner.companyId="b";"session"->owner.api.session++;"tool"->owner.tool="other";else->owner.epoch++};done.complete(Unit);pending.await();check(f.rows==null&&f.failure==""&&owner.failures==0)
 }
 val failing=Screen(AppModel());failing.vm.api.read={throw ApiFailure(503,"current error")};failing.load();check(failing.failure=="current error")
 val expired=Screen(AppModel());expired.vm.api.read={expired.vm.api.signedIn=false;expired.vm.api.session++;throw ApiFailure(401,"expired")};expired.load();check(expired.vm.failures==1)
 val detail=AppModel();openRecurringSchedule(detail,JSONObject());check(detail.tool=="recurring_edit"&&detail.toolData!=null&&detail.api.calls==1)
 for(mode in listOf("company","session","tool","access"))for(fails in listOf(false,true)){
  val owner=AppModel();val done=CompletableDeferred<Unit>();owner.api.read={done.await();if(fails)throw ApiFailure(503,"late detail error");JSONObject()};val pending=async{openRecurringSchedule(owner,JSONObject())};yield();when(mode){"company"->owner.companyId="b";"session"->owner.api.session++;"tool"->owner.tool="other";else->owner.epoch++};done.complete(Unit);pending.await();check(owner.toolData==null&&owner.tool!="recurring_edit")
 }
 val invalid=AppModel();invalid.recordsReady=false;openRecurringSchedule(invalid,JSONObject());check(invalid.api.calls==0)
 val error=AppModel();error.api.read={throw ApiFailure(503,"current details error")};check(runCatching{openRecurringSchedule(error,JSONObject())}.exceptionOrNull()!!.message=="current details error")
 val expiry=AppModel();expiry.api.read={expiry.api.signedIn=false;throw ApiFailure(401,"expired details")};check((runCatching{openRecurringSchedule(expiry,JSONObject())}.exceptionOrNull() as ApiFailure).status==401)
 println("PASS actual detail read: current success/error/expiry, no dispatch without access, eight stale reads/errors")
 println("PASS actual recurring list read: denied late response, cleared cached calendar, recovery, eight stale reads/errors, current failure and expiry")
}
'''.replace('BODY',body).replace('DETAIL',detail)
with tempfile.TemporaryDirectory(prefix='apex-recurring-reads-') as folder:
 d=Path(folder);(d/'Proof.kt').write_text(fixture);run_proof(args,[d/'Proof.kt'],d)
