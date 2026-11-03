"""Verify the production company-load cancellation boundary without Android runtime.

Uses Kotlin/compiler/coroutines already shipped with the Gradle distribution.
Uses the already-cached org.json test dependency and the production strict decoder.
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
json_version="20250517"
json_jars=sorted((cache/"caches/modules-2/files-2.1/org.json/json"/json_version).glob("*/json-*.jar"))
if not json_jars:raise SystemExit("Run the existing Android unit-test build first: its cached org.json:json:20250517 dependency is required; no download is performed.")
json_jar=json_jars[0]
company_reads=root/'native/android/app/src/main/java/com/apexbooks/accounting/data/CompanyReads.kt'
api_source=(root/'native/android/app/src/main/java/com/apexbooks/accounting/data/ApexApi.kt').read_text()
api_failure=next(line for line in api_source.splitlines() if line.startswith('class ApiFailure('))
backup=(root/'native/android/app/src/main/java/com/apexbooks/accounting/CompleteBackupTool.kt').read_text()
open_action=next(line for line in backup.splitlines() if 'Text("Open restored company")' in line)
assert 'vm.task{' in open_action and 'onClick={act{' not in open_action, "Restored company navigation must outlive its dialog scope"
s=(root/'native/android/app/src/main/java/com/apexbooks/accounting/AppModel.kt').read_text()
choose=next(x.strip() for x in s.splitlines() if x.strip().startswith('suspend fun chooseCompany('))
task=next(x.strip() for x in s.splitlines() if x.strip().startswith('fun task('))
temporary=tempfile.TemporaryDirectory(prefix='apex navigation proof ');p=Path(temporary.name)
fixture='''import kotlinx.coroutines.*
import org.json.JSONObject
import org.json.JSONArray
import com.apexbooks.accounting.data.companyRows
fun JSONObject.s(key:String)=optString(key,"")
class Api(val release:CompletableDeferred<Unit>){suspend fun records(id:String):List<JSONObject>{release.await();return listOf(JSONObject().put("id","record-$id"))};fun company(id:String,path:String)=id; suspend fun request(path:String):Any{release.await();return JSONArray().put(JSONObject().put("id","bank"))}}
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
  val caller=dialogScope.launch {if(sessionOwned)model.task{model.chooseCompany(JSONObject().put("id","restored"))}else model.chooseCompany(JSONObject().put("id","restored"))}
  changed.await();yield();dialogJob.cancel();release.complete(Unit);caller.join()
  withTimeout(3000){if(sessionOwned)while(!model.recordsReady)yield()}
  check(model.recordsReady==sessionOwned){"Unexpected recordsReady=${model.recordsReady}"}
  check(model.company.getString("id")=="restored"&&model.tool.isEmpty())
  println(if(sessionOwned)"PASS: unchanged production task()/chooseCompany() finish records after dialog cancellation"else"REPRODUCED: unchanged production chooseCompany() leaves selected company with recordsReady=false after dialog cancellation")
  vmJob.cancelAndJoin()
 }
}
'''
(p/'Proof.kt').write_text(fixture)
(p/'ApiFailure.kt').write_text('package com.apexbooks.accounting.data\n'+api_failure+'\n')
lib=gradle/'lib';cp=os.pathsep.join(str(x) for x in [*sorted(lib.glob('*.jar')),json_jar])
def run_java(name, arguments):
    # The compiler classpath occurs twice and exceeds Windows' command limit.
    # Quote for Java's argument-file parser, not a shell. Doubling backslashes
    # keeps Windows path components from being interpreted as escapes.
    def quote(value):
        return '"'+str(value).replace('\\','\\\\').replace('"','\\"').replace('\n','\\n').replace('\r','\\r')+'"'
    argument_file=p/(name+'.args')
    argument_file.write_text('\n'.join(quote(value) for value in arguments)+'\n',encoding='utf-8')
    subprocess.run(['java','@'+str(argument_file)],check=True)

try:
    run_java('compile',['-cp',cp,'org.jetbrains.kotlin.cli.jvm.K2JVMCompiler','-no-stdlib','-no-reflect','-classpath',cp,'-d',p/'proof.jar',p/'Proof.kt',p/'ApiFailure.kt',company_reads])
    run_java('run',['-cp',str(p/'proof.jar')+os.pathsep+cp,'ProofKt'])
finally:
    temporary.cleanup()
