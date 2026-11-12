"""Compile the real AppModel post-confirmation completion method with delayed refresh."""
from pathlib import Path
import argparse,sys,tempfile
root=Path(__file__).resolve().parents[3];sys.path.insert(0,str(root/'native/tests'))
from kotlin_toolchain import add_arguments,run_proof
p=argparse.ArgumentParser();add_arguments(p);args=p.parse_args()
s=(root/'native/android/app/src/main/java/com/apexbooks/accounting/AppModel.kt').read_text();method=s[s.index('    suspend fun finishConfirmedImport('):s.index('    suspend fun finishConfirmedEntry(')]
fixture='''import kotlinx.coroutines.*
class ApiFailure(val status:Int,message:String):Exception(message)
class Api{var signedIn=true;var epoch=0;fun captureSession():()->Unit{val stamp=epoch;return{check(epoch==stamp&&signedIn)}}}
class VM{val api=Api();var companyId="a";var generation=0;var signedIn=true;var tool="statement_import";var toolData:Any?=Any();var notice="";var requests=0;var refreshAction:suspend()->Unit={}
fun workspaceStamp()=generation
fun inWorkspace(id:String,stamp:Int)=signedIn&&companyId==id&&generation==stamp
suspend fun refresh(){requests++;refreshAction()}
METHOD
}
fun main()=runBlocking{
 val vm=VM();vm.finishConfirmedImport();check(vm.requests==1&&vm.notice=="Import confirmed."&&vm.tool=="")
 for(error in listOf(java.io.IOException("offline"),ApiFailure(503,"unavailable"),ApiFailure(403,"access removed"))){
  vm.refreshAction={throw error};val found=runCatching{vm.finishConfirmedImport()}.exceptionOrNull();check(found is ApiFailure&&found.message!!.contains("Do not repeat"));check(found.status==if(error is ApiFailure)error.status else 0)
 }
 vm.refreshAction={vm.api.signedIn=false;vm.api.epoch++;throw ApiFailure(401,"expired")};val expired=runCatching{vm.finishConfirmedImport()}.exceptionOrNull();check(expired is ApiFailure&&expired.status==401&&expired.message!!.contains("confirmed"))
 for(mode in listOf("company","session","away-back"))for(fails in listOf(false,true)){
  val next=VM();val started=CompletableDeferred<Unit>();val done=CompletableDeferred<Unit>();next.refreshAction={started.complete(Unit);done.await();if(fails)throw java.io.IOException("old failure")}
  val call=async{next.finishConfirmedImport()};started.await();when(mode){"company"->next.companyId="b";"session"->next.api.epoch++;else->{next.generation+=2}}
  next.notice="New workspace notice";done.complete(Unit);call.await();check(next.notice=="New workspace notice")
 }
 val cancelled=VM();cancelled.refreshAction={throw CancellationException("cancel")};check(runCatching{cancelled.finishConfirmedImport()}.exceptionOrNull() is CancellationException)
 println("PASS actual completion: confirmed success, offline/503/403/401, six stale refresh cases, cancellation")
}
'''.replace('METHOD',method)
with tempfile.TemporaryDirectory(prefix='apex-import-completion-') as directory:
 d=Path(directory);(d/'Proof.kt').write_text(fixture);run_proof(args,[d/'Proof.kt'],d)
