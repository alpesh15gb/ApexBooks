from pathlib import Path
import argparse,sys,tempfile
root=Path(__file__).resolve().parents[3];sys.path.insert(0,str(root/'native/tests'))
from kotlin_toolchain import add_arguments,run_proof
p=argparse.ArgumentParser();add_arguments(p);args=p.parse_args()
s=(root/'native/android/app/src/main/java/com/apexbooks/accounting/RecurringTools.kt').read_text()
helper=s[s.index('suspend fun reviewGeneratedRecurringDraft('):s.index('@Composable private fun RecurringReview(')]
callback=s.split('@Composable private fun RecurringOccurrence(',1)[1].split('onSave={',1)[1].split('\n    })',1)[0]
assert '"recurring_review"->RecurringReview(vm,row)' in s
assert '"recurring_review"->RecurringTools' in (root/'native/android/app/src/main/java/com/apexbooks/accounting/ToolsScreen.kt').read_text()
assert 'recurringWrite(' not in helper
fixture=r'''
import kotlinx.coroutines.*
class JSONObject {val data=mutableMapOf<String,Any>();fun put(key:String,value:Any):JSONObject{data[key]=value;return this};fun optBoolean(key:String)=data[key]==true}
fun JSONObject.s(key:String)=data[key]?.toString().orEmpty()
fun JSONObject.o(key:String)=data[key] as? JSONObject?:JSONObject()
fun encode(value:String)=value
class ApiFailure(val status:Int,message:String):Exception(message)
fun draft()=JSONObject().put("id","saved").put("kind","estimate").put("number","EST-SAVED")
class Api {var signedIn=true;var epoch=0;var gets=0;var read:suspend()->JSONObject={draft()};fun captureSession():()->Unit{val before=epoch;return{check(signedIn&&epoch==before)}};fun company(cid:String,path:String)=cid+path;suspend fun record(cid:String,id:String):JSONObject{gets++;return read()}}
class EntryEditor(vm:AppModel,kind:String,previous:JSONObject){init{vm.editorFailure?.let{throw it}}}
class AppModel{
 val api=Api();var signedIn=true;var companyId="a";var generation=0;var readEpoch=0;var page="dashboard";var tool="recurring_occurrence";var toolData:JSONObject?=JSONObject().put("id","template");var recordsReady=true;var writer=true;val canWrite get()=writer&&recordsReady&&signedIn;val draftKinds=setOf("estimate");var editor:EntryEditor?=null;var detail:JSONObject?=null;var notice="";var posts=0;var refreshes=0;var finishes=0;var editorFailure:Exception?=null;var refreshAction:suspend()->Unit={}
 fun workspaceStamp()=generation;fun inWorkspace(id:String,stamp:Int)=signedIn&&id==companyId&&stamp==generation
 fun readStamp()=generation.toLong()*1000+readEpoch;fun canRead(id:String,stamp:Long)=signedIn&&recordsReady&&id==companyId&&readStamp()==stamp
 suspend fun refresh(){refreshes++;refreshAction()};fun finishRecurring(scope:String){finishes++}
}
suspend fun recurringWrite(vm:AppModel,command:Any,path:String,method:String,body:JSONObject,validate:(JSONObject)->Unit={}):JSONObject{vm.posts++;val result=JSONObject().put("record",draft());validate(result);return result}
suspend fun generate(vm:AppModel){val cid=vm.companyId;val stamp=vm.workspaceStamp();val scope="occurrence";val occurrence="2026-01-01";val row=vm.toolData!!;val command=Any();CALLBACK}
HELPER
fun main()=runBlocking{
 val ok=AppModel();generate(ok);check(ok.posts==1&&ok.refreshes==1&&ok.api.gets==1&&ok.editor!=null&&ok.tool=="")
 for(code in listOf(0,403,404,422,503)){
  val vm=AppModel();vm.refreshAction={throw ApiFailure(code,"refresh failed")};val error=runCatching{generate(vm)}.exceptionOrNull();check(error is ApiFailure&&error.status==code&&error.message!!.contains("EST-SAVED is saved"));check(vm.tool=="recurring_review"&&vm.posts==1&&vm.editor==null)
  vm.refreshAction={};reviewGeneratedRecurringDraft(vm);check(vm.posts==1&&vm.editor!=null&&vm.api.gets==1)
 }
 val again=AppModel();again.refreshAction={throw java.io.IOException("offline")};runCatching{generate(again)};val failure=runCatching{reviewGeneratedRecurringDraft(again)}.exceptionOrNull();check(failure!!.message!!.contains("Do not generate")&&again.posts==1);again.refreshAction={};again.writer=false;reviewGeneratedRecurringDraft(again);check(again.editor==null&&again.detail!!.s("id")=="saved")
 for(flag in listOf("cancelled","converted_to")){val vm=AppModel();vm.api.read={draft().put(flag,if(flag=="cancelled")true else "invoice")};generate(vm);check(vm.editor==null&&vm.detail!=null)}
 val opening=AppModel();opening.editorFailure=java.io.IOException("editor setup failed");check(runCatching{generate(opening)}.exceptionOrNull()!!.message!!.contains("is saved"));check(opening.tool=="recurring_review");opening.editorFailure=null;reviewGeneratedRecurringDraft(opening);check(opening.posts==1&&opening.editor!=null)
 for(mode in listOf("company","session","page","tool","awayback","logout"))for(fails in listOf(false,true)){
  val vm=AppModel();val gate=CompletableDeferred<Unit>();val started=CompletableDeferred<Unit>();vm.refreshAction={started.complete(Unit);gate.await();if(fails)throw java.io.IOException("late")};val pending=async{generate(vm)};started.await()
  when(mode){"company"->vm.companyId="b";"session"->vm.api.epoch++;"page"->vm.page="reports";"tool"->vm.tool="other";"awayback"->vm.generation++;else->{vm.signedIn=false;vm.api.signedIn=false}}
  gate.complete(Unit);pending.await();check(vm.editor==null&&vm.detail==null&&vm.notice==""&&vm.api.gets==0)
 }
 for(fails in listOf(false,true)){
  val vm=AppModel();val gate=CompletableDeferred<Unit>();val started=CompletableDeferred<Unit>();vm.api.read={started.complete(Unit);gate.await();if(fails)throw java.io.IOException("late record");draft()};val pending=async{runCatching{generate(vm)}};started.await();vm.readEpoch++;vm.recordsReady=false;gate.complete(Unit);pending.await();check(vm.editor==null&&vm.detail==null)
 }
 val expired=AppModel();expired.refreshAction={expired.api.signedIn=false;expired.api.epoch++;throw ApiFailure(401,"expired")};val expiration=runCatching{generate(expired)}.exceptionOrNull();check(expiration is ApiFailure&&expiration.status==401&&expiration.message!!.contains("is saved"))
 val viewer=AppModel();viewer.writer=false;check(runCatching{generate(viewer)}.isFailure&&viewer.posts==0)
 val cancelled=AppModel();cancelled.refreshAction={throw CancellationException("cancelled")};check(runCatching{generate(cancelled)}.exceptionOrNull() is CancellationException)
 println("PASS actual Android generation callback/completion: confirmed error recovery without repost, viewer/status routing, editor failure, 12 stale refreshes, denied reads, 401, cancellation and forced viewer dispatch")
}
'''.replace('CALLBACK',callback).replace('HELPER',helper)
with tempfile.TemporaryDirectory(prefix='apex-android-recurring-completion-') as folder:
 d=Path(folder);(d/'Proof.kt').write_text(fixture);run_proof(args,[d/'Proof.kt'],d)
