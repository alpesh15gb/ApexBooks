from pathlib import Path
import argparse,sys,tempfile
root=Path(__file__).resolve().parents[3];sys.path.insert(0,str(root/'native/tests'))
from kotlin_toolchain import add_arguments,run_proof
p=argparse.ArgumentParser();add_arguments(p);args=p.parse_args()
s=(root/'native/android/app/src/main/java/com/apexbooks/accounting/RecurringTools.kt').read_text();edit=s.split('@Composable private fun RecurringEdit(',1)[1].split('@Composable private fun RecurringOccurrence(',1)[0]
def function(name):
 start=edit.index('fun '+name+'(');brace=edit.index('{',start);depth=1;end=brace+1
 while depth:
  if edit[end]=='{':depth+=1
  if edit[end]=='}':depth-=1
  end+=1
 return edit[start:end]
method=function('reload')+'\n'+function('requestReload')
assert 'onClick=::requestReload' in edit and 'Reload and replace edits' in edit and 'Keep editing' in edit
fixture=r'''
import kotlinx.coroutines.*
class JSONObject(val name:String="Server",val version:Int=2,val active:Boolean=false){fun optInt(k:String)=version;fun optBoolean(k:String)=active}
fun JSONObject.s(k:String)=if(k=="id")"template" else name
fun encode(v:String)=v
class Command{var unresolved=false}
class Api{var calls=0;var action:suspend()->JSONObject={JSONObject()};fun company(cid:String,path:String)=cid+path;suspend fun request(path:String):Any{calls++;return action()}}
class AppModel(val scope:CoroutineScope){val api=Api();var companyId="a";var generation=0;var tool="recurring_edit";var toolData:JSONObject?=null;var ready=true;var epoch=0;var busy=0;var notice="";var error="";var finishes=0;var job:Job?=null;fun inWorkspace(id:String,stamp:Int)=companyId==id&&generation==stamp;fun finishRecurring(value:String){finishes++};fun captureReadOwner(tool:String,row:JSONObject):()->Boolean{val before=epoch;val id=companyId;val gen=generation;return{epoch==before&&ready&&companyId==id&&gen==generation&&this.tool==tool&&toolData===row}};fun task(action:suspend()->Unit){busy++;job=scope.launch{try{action()}catch(e:Exception){if(e is CancellationException)throw e;error=e.message.orEmpty()}finally{busy--}}}}
class Screen(val vm:AppModel){val row=JSONObject("Original",1,true);val cid=vm.companyId;val stamp=vm.generation;val scope="edit:template";val command=Command();var name="Original";var active=true;var source="source";var loading=false;var confirmReload=false;init{vm.toolData=row};fun changed()=name!=row.name||!active||source.isNotBlank()
 METHOD
}
fun main()=runBlocking{
 val confirm=Screen(AppModel(this));confirm.requestReload();check(confirm.confirmReload&&confirm.vm.job==null&&confirm.vm.api.calls==0);confirm.confirmReload=false;check(confirm.name=="Original"&&confirm.source=="source")
 val clean=Screen(AppModel(this));clean.source="";clean.requestReload();clean.vm.job!!.join();check(!clean.confirmReload&&clean.name=="Server")
 val screen=Screen(AppModel(this));val gate=CompletableDeferred<Unit>();val started=CompletableDeferred<Unit>();screen.vm.api.action={started.complete(Unit);gate.await();JSONObject()};screen.reload();started.await();screen.name="Newer edit";gate.complete(Unit);screen.vm.job!!.join();check(screen.name=="Newer edit"&&screen.vm.toolData===screen.row){"Reload overwrote newer edits"}
 val failure=Screen(AppModel(this));failure.vm.api.action={throw java.io.IOException("offline")};failure.reload();failure.vm.job!!.join();check(failure.name=="Original"&&failure.source=="source"&&failure.vm.toolData===failure.row&&failure.vm.error=="offline")
 val current=Screen(AppModel(this));current.reload();current.vm.job!!.join();check(current.name=="Server"&&!current.active&&current.source==""&&current.vm.finishes==1)
 for(mode in listOf("company","tool","access","replacement"))for(failed in listOf(false,true)){
  val vm=AppModel(this);val f=Screen(vm);val done=CompletableDeferred<Unit>();val begun=CompletableDeferred<Unit>();vm.api.action={begun.complete(Unit);done.await();if(failed)throw java.io.IOException("old");JSONObject()};f.reload();begun.await();when(mode){"company"->vm.companyId="b";"tool"->vm.tool="other";"access"->vm.epoch++;else->vm.toolData=JSONObject()};done.complete(Unit);vm.job!!.join();check(f.name=="Original"&&vm.error==""&&vm.finishes==0)
 }
 val locked=Screen(AppModel(this));locked.command.unresolved=true;locked.reload();check(locked.vm.api.calls==0&&locked.vm.job==null)
 val duplicate=Screen(AppModel(this));val wait=CompletableDeferred<Unit>();duplicate.vm.api.action={wait.await();JSONObject()};duplicate.reload();duplicate.reload();yield();check(duplicate.vm.api.calls==1);wait.complete(Unit);duplicate.vm.job!!.join()
 val uncertain=Screen(AppModel(this));val outcome=CompletableDeferred<Unit>();val readStarted=CompletableDeferred<Unit>();uncertain.vm.api.action={readStarted.complete(Unit);outcome.await();JSONObject()};uncertain.reload();readStarted.await();uncertain.command.unresolved=true;outcome.complete(Unit);uncertain.vm.job!!.join();check(uncertain.name=="Original"&&uncertain.command.unresolved&&uncertain.vm.finishes==0)
 println("PASS actual Android reload: newer edits preserved, current success/error, eight stale success/errors, confirmation gate, unresolved lock and duplicate guard")
}
'''.replace('METHOD',method)
with tempfile.TemporaryDirectory(prefix='apex-recurring-reload-') as folder:
 d=Path(folder);(d/'Proof.kt').write_text(fixture);run_proof(args,[d/'Proof.kt'],d)
