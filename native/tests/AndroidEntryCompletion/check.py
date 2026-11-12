"""Compile the real AppModel entry post-confirmation completion method with delayed refresh."""
from pathlib import Path
import argparse,sys,tempfile
root=Path(__file__).resolve().parents[3];sys.path.insert(0,str(root/'native/tests'))
from kotlin_toolchain import add_arguments,run_proof
p=argparse.ArgumentParser();add_arguments(p);args=p.parse_args()
s=(root/'native/android/app/src/main/java/com/apexbooks/accounting/AppModel.kt').read_text();method=s[s.index('    suspend fun finishConfirmedEntry('):s.index('    fun navigate(key:String)')]
editor=(root/'native/android/app/src/main/java/com/apexbooks/accounting/EntryEditor.kt').read_text()
assert 'vm.finishConfirmedEntry(' in editor
assert editor.index('submission.succeeded()') < editor.index('vm.finishConfirmedEntry(')
fixture='''import kotlinx.coroutines.*
class ApiFailure(val status:Int,message:String):Exception(message)
class Api{var signedIn=true;var epoch=0;fun captureSession():()->Unit{val stamp=epoch;return{check(epoch==stamp&&signedIn)}}}
class VM{val api=Api();var companyId="a";var generation=0;var signedIn=true;var page="sales";var editor:Any?=Any();var notice="";var requests=0;var refreshAction:suspend()->Unit={}
fun workspaceStamp()=generation
fun inWorkspace(id:String,stamp:Int)=signedIn&&companyId==id&&generation==stamp
suspend fun refresh(){requests++;refreshAction()}
METHOD
}
fun main()=runBlocking{
 val vm=VM();vm.finishConfirmedEntry("Entry saved.");check(vm.requests==1&&vm.notice=="Entry saved.")
 for(error in listOf(java.io.IOException("offline"),ApiFailure(503,"unavailable"),ApiFailure(403,"access removed"))){
  vm.refreshAction={throw error};val found=runCatching{vm.finishConfirmedEntry("Entry saved.")}.exceptionOrNull();check(found is ApiFailure&&found.message!!.contains("Do not submit"));check(found.status==if(error is ApiFailure)error.status else 0)
 }
 vm.refreshAction={vm.api.signedIn=false;vm.api.epoch++;throw ApiFailure(401,"expired")};val expired=runCatching{vm.finishConfirmedEntry("Entry saved.")}.exceptionOrNull();check(expired is ApiFailure&&expired.status==401&&expired.message!!.contains("saved"))
 for(mode in listOf("company","session","away-back","page","editor"))for(fails in listOf(false,true)){
  val next=VM();val started=CompletableDeferred<Unit>();val done=CompletableDeferred<Unit>();next.refreshAction={started.complete(Unit);done.await();if(fails)throw java.io.IOException("old failure")}
  val call=async{next.finishConfirmedEntry("Entry saved.")};started.await();when(mode){"company"->next.companyId="b";"session"->next.api.epoch++;"page"->next.page="reports";"editor"->next.editor=Any();else->{next.generation+=2}}
  next.notice="New workspace notice";done.complete(Unit);call.await();check(next.notice=="New workspace notice")
 }
 val cancelled=VM();cancelled.refreshAction={throw CancellationException("cancel")};check(runCatching{cancelled.finishConfirmedEntry("Entry saved.")}.exceptionOrNull() is CancellationException)
 println("PASS actual completion: confirmed success, offline/503/403/401, ten stale refresh cases, cancellation")
}
'''.replace('METHOD',method)
with tempfile.TemporaryDirectory(prefix='apex-entry-completion-') as directory:
 d=Path(directory);(d/'Proof.kt').write_text(fixture);run_proof(args,[d/'Proof.kt'],d)
