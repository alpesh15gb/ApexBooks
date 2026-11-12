"""Compile the actual legacy export flow with delayed synthetic fetch/encryption."""
from pathlib import Path
import argparse,sys,tempfile
root=Path(__file__).resolve().parents[3];sys.path.insert(0,str(root/'native/tests'))
from kotlin_toolchain import add_arguments,run_proof
p=argparse.ArgumentParser();add_arguments(p);args=p.parse_args()
s=(root/'native/android/app/src/main/java/com/apexbooks/accounting/ToolsScreen.kt').read_text()
method=s[s.index('private suspend fun legacyFileExport('):s.index('@Composable private fun BasicTool')]
assert 'if(legacyFileExport(vm,cid,tool,JSONObject(v.toMap())))close();return@ActionDialog' in s
fixture=r'''
import kotlinx.coroutines.*
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
class JSONObject(val values:Map<String,String>){fun optString(key:String,fallback:String)=values[key]?:fallback}
class Api{var epoch=0;val pending=CompletableDeferred<ByteArray>();var path="";fun captureSession():()->Unit{val stamp=epoch;return{check(stamp==epoch)}};fun company(id:String,suffix:String)="/companies/$id$suffix";suspend fun bytes(url:String):ByteArray{path=url;return pending.await()}}
class Files{val saved=mutableListOf<ByteArray>();fun save(bytes:ByteArray,name:String){saved+=bytes}}
class AppModel(var tool:String){val api=Api();val files=Files();var companyId="a";var access=0;var ready=true;fun readStamp()=access;fun canRead(id:String,stamp:Int)=id==companyId&&stamp==access&&ready}
fun today()="2026-04-01"
object NativeFiles{var hold=false;var fail=false;var entered=CountDownLatch(1);var release=CountDownLatch(1);fun encrypt(bytes:ByteArray,password:String):ByteArray{if(hold){entered.countDown();check(release.await(5,TimeUnit.SECONDS))};if(fail)throw Exception("synthetic encrypt failure");return bytes+4}}
METHOD
fun main()=runBlocking{
 var cases=0
 for(tool in listOf("backup","data_export"))for(stage in listOf("fetch","encrypt"))for(outcome in listOf("current","company","denied","recovered","session","closed","stale-error","current-error")){
  if(stage=="encrypt"&&tool!="backup")continue
  NativeFiles.hold=stage=="encrypt";NativeFiles.fail=stage=="encrypt"&&outcome.endsWith("error");NativeFiles.entered=CountDownLatch(1);NativeFiles.release=CountDownLatch(1)
  val vm=AppModel(tool);val values=JSONObject(mapOf("password" to "synthetic-password","export_kind" to "party","format" to "xlsx"))
  val task=async(start=CoroutineStart.UNDISPATCHED){runCatching{legacyFileExport(vm,"a",tool,values)}}
  if(stage=="encrypt"){vm.api.pending.complete(byteArrayOf(1));check(withContext(Dispatchers.IO){NativeFiles.entered.await(5,TimeUnit.SECONDS)})}
  when(outcome){"company","stale-error"->vm.companyId="b";"denied"->vm.ready=false;"recovered"->vm.access++;"session"->vm.api.epoch++;"closed"->vm.tool=""}
  if(stage=="fetch"){if(outcome.endsWith("error"))vm.api.pending.completeExceptionally(Exception("synthetic fetch failure"))else vm.api.pending.complete(byteArrayOf(1))}else NativeFiles.release.countDown()
  val result=task.await();check(vm.api.path.startsWith("/companies/a/"))
  if(outcome=="current"){check(result.getOrNull()==true&&vm.files.saved.size==1)}else{check(vm.files.saved.isEmpty());if(outcome=="current-error")check(result.isFailure)else check(result.getOrNull()==false){"Stale result escaped $tool $stage $outcome: $result"}}
  cases++
 }
 println("PASS actual legacy export: $cases delayed fetch/encryption and stale-error cases")
}
'''.replace('METHOD',method)
with tempfile.TemporaryDirectory(prefix='apex-legacy-export-') as temp:
 temp=Path(temp);(temp/'Proof.kt').write_text(fixture);run_proof(args,[temp/'Proof.kt'],temp)
