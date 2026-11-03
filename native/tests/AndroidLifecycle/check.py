"""Verify the production company-load cancellation boundary without Android runtime.

Uses Kotlin/compiler/coroutines already shipped with the Gradle distribution.
No Android stubs are invoked and no network requests or credentials are used.
"""
from pathlib import Path
import argparse
import os
import subprocess
import tempfile
root=Path(__file__).resolve().parents[3]
parser=argparse.ArgumentParser()
parser.add_argument("--gradle-home",type=Path)
args=parser.parse_args()
candidates=([args.gradle_home] if args.gradle_home else [])
if os.environ.get("GRADLE_HOME"):candidates.append(Path(os.environ["GRADLE_HOME"]))
cache=Path(os.environ.get("GRADLE_USER_HOME",str(Path.home()/".gradle")))
candidates.extend(cache.glob("wrapper/dists/gradle-8.14.3-bin/*/gradle-8.14.3"))
gradle=next((p for p in candidates if (p/"lib/kotlin-compiler-embeddable-2.0.21.jar").is_file()),None)
if gradle is None:raise SystemExit("Pass --gradle-home for the existing Gradle 8.14.3 distribution; no download is performed.")
backup=(root/'native/android/app/src/main/java/com/apexbooks/accounting/CompleteBackupTool.kt').read_text()
open_action=next(line for line in backup.splitlines() if 'Text("Open restored company")' in line)
assert 'vm.task{' in open_action and 'onClick={act{' not in open_action, "Restored company navigation must outlive its dialog scope"
s=(root/'native/android/app/src/main/java/com/apexbooks/accounting/AppModel.kt').read_text()
choose=next(x.strip() for x in s.splitlines() if x.strip().startswith('suspend fun chooseCompany('))
task=next(x.strip() for x in s.splitlines() if x.strip().startswith('fun task('))
temporary=tempfile.TemporaryDirectory(prefix='apex-navigation-proof-');p=Path(temporary.name)
fixture='''import kotlinx.coroutines.*
class JSONObject(val id:String="")
fun JSONObject.s(key:String)=id
class JSONArray
fun JSONArray.objects()=listOf(JSONObject("bank"))
class Api(val release:CompletableDeferred<Unit>){suspend fun records(id:String):List<JSONObject>{release.await();return listOf(JSONObject("record-$id"))};fun company(id:String,path:String)=id; suspend fun request(path:String):Any{release.await();return JSONArray()}}
class Model(val viewModelScope:CoroutineScope,val changed:CompletableDeferred<Unit>,val release:CompletableDeferred<Unit>){
 val api=Api(release);var generation=0;var refreshSequence=0;var company=JSONObject();set(value){field=value;changed.complete(Unit)}
 var companyForm=false;var tool="restore";var toolData:Any?=null;var records=emptyList<JSONObject>();var banks=emptyList<JSONObject>();var recordsReady=false
 var editor:Any?=null;var detail:Any?=null;var pdf:Any?=null;var statement:Any?=null;var busy=0;var error="";var notice=""
 fun failure(e:Exception){if(e is CancellationException)throw e;throw AssertionError(e)}
'''+choose+'\n'+task+'''
}
fun main()=runBlocking {
 for(sessionOwned in listOf(false,true)){
  val vmJob=SupervisorJob();val vmScope=CoroutineScope(coroutineContext+vmJob)
  val dialogJob=Job();val dialogScope=CoroutineScope(coroutineContext+dialogJob)
  val changed=CompletableDeferred<Unit>();val release=CompletableDeferred<Unit>();val model=Model(vmScope,changed,release)
  val caller=dialogScope.launch {if(sessionOwned)model.task{model.chooseCompany(JSONObject("restored"))}else model.chooseCompany(JSONObject("restored"))}
  changed.await();yield();dialogJob.cancel();release.complete(Unit);caller.join()
  withTimeout(3000){if(sessionOwned)while(!model.recordsReady)yield()}
  check(model.recordsReady==sessionOwned){"Unexpected recordsReady=${model.recordsReady}"}
  check(model.company.id=="restored"&&model.tool.isEmpty())
  println(if(sessionOwned)"PASS: unchanged production task()/chooseCompany() finish records after dialog cancellation"else"REPRODUCED: unchanged production chooseCompany() leaves selected company with recordsReady=false after dialog cancellation")
  vmJob.cancelAndJoin()
 }
}
'''
(p/'Proof.kt').write_text(fixture)
lib=gradle/'lib';cp=':'.join(str(x) for x in lib.glob('*.jar'))
subprocess.run(['java','-cp',cp,'org.jetbrains.kotlin.cli.jvm.K2JVMCompiler','-no-stdlib','-no-reflect','-classpath',cp,'-d',str(p/'proof.jar'),str(p/'Proof.kt')],check=True)
subprocess.run(['java','-cp',str(p/'proof.jar')+':'+cp,'ProofKt'],check=True)
temporary.cleanup()
