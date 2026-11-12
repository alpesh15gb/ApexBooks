"""Compile actual attachment/recovery handlers and captured read-owner method."""
from pathlib import Path
import argparse,sys,tempfile
root=Path(__file__).resolve().parents[3];sys.path.insert(0,str(root/'native/tests'))
from kotlin_toolchain import add_arguments,run_proof
p=argparse.ArgumentParser();add_arguments(p);args=p.parse_args()
a=(root/'native/android/app/src/main/java/com/apexbooks/accounting/AttachmentsTool.kt').read_text();t=(root/'native/android/app/src/main/java/com/apexbooks/accounting/ToolsScreen.kt').read_text();m=(root/'native/android/app/src/main/java/com/apexbooks/accounting/AppModel.kt').read_text()
handlers=a[a.index('fun sha256('):a.index('class AttachmentDraft')]+a[a.index('private suspend fun downloadRetainedReceipt('):a.index('@Composable fun AttachmentsTool')]+t[t.index('private suspend fun generateScopedRecoveryCodes('):t.index('@Composable private fun BasicTool')]
owner=m[m.index('    fun captureReadOwner('):m.index('    fun workspaceStamp()')]
assert 'if(readOwner()){Text(codes);' in t
assert 'if(current())rows.filter' in a
fixture=r'''
import kotlinx.coroutines.*
import java.security.MessageDigest
class JSONObject{val values=mutableMapOf<String,Any>();fun put(key:String,value:Any)=apply{values[key]=value};fun optLong(key:String,fallback:Long=0)=(values[key] as? Number)?.toLong()?:fallback}
fun JSONObject.s(key:String)=values[key]?.toString()?:""
fun encode(value:String)=value
class Api{var session=0;val bytes=CompletableDeferred<ByteArray>();val response=CompletableDeferred<JSONObject>();fun captureSession():()->Unit{val stamp=session;return{check(stamp==session)}};fun company(id:String,suffix:String)=id+suffix;suspend fun rawBytes(path:String,maximumResponse:Int)=bytes.await();suspend fun request(path:String,method:String,body:JSONObject)=response.await()}
class Files{var saves=0;fun save(bytes:ByteArray,name:String){saves++}}
class AppModel{val api=Api();val files=Files();var companyId="a";var access=0;var ready=true;var signedIn=true;var tool="attachments";var toolData:JSONObject?=JSONObject();fun readStamp()=access;fun canRead(id:String,stamp:Int)=signedIn&&ready&&companyId==id&&access==stamp
 OWNER
}
HANDLERS
fun change(vm:AppModel,kind:String){when(kind){"company"->vm.companyId="b";"denied"->vm.ready=false;"recovered"->vm.access++;"session"->vm.api.session++;"closed"->vm.tool="";"data"->vm.toolData=JSONObject();"signed-out"->vm.signedIn=false}}
fun main()=runBlocking{
 val scopes=listOf("current","company","denied","recovered","session","closed","data","signed-out")
 for(scope in scopes+listOf("corrupt","stale-corrupt")){
  val vm=AppModel();val valid=byteArrayOf(1,2);val row=JSONObject().put("id","r").put("filename","synthetic.pdf").put("size_bytes",2).put("sha256",sha256(valid));val current=vm.captureReadOwner(vm.tool,vm.toolData)
  val task=async(start=CoroutineStart.UNDISPATCHED){runCatching{downloadRetainedReceipt(vm,"a",row,current)}}
  change(vm,if(scope=="stale-corrupt")"recovered"else scope);vm.api.bytes.complete(if(scope.endsWith("corrupt"))byteArrayOf(9)else valid);val result=task.await()
  check(vm.files.saves==if(scope=="current")1 else 0);if(scope=="corrupt")check(result.isFailure)else check(result.getOrNull()==(scope=="current"))
 }
 for(scope in scopes){
  val vm=AppModel();vm.tool="recovery";val current=vm.captureReadOwner(vm.tool,vm.toolData);val original=vm.toolData
  val task=async(start=CoroutineStart.UNDISPATCHED){generateScopedRecoveryCodes(vm,"synthetic-password",current)};change(vm,scope);vm.api.response.complete(JSONObject());val published=task.await();check(published==(scope=="current"));if(scope=="current")check(vm.tool=="recovery_saved"&&vm.toolData!==original)else check(vm.tool!="recovery_saved")
  val view=AppModel();view.tool="recovery_saved";val owner=view.captureReadOwner(view.tool,view.toolData);change(view,scope);saveScopedRecoveryCodes(view,"SYNTHETIC-CODE",owner);check(view.files.saves==if(scope=="current")1 else 0)
 }
 for(mode in listOf("current","stale","unresolved","error","stale-error","cancel")){
  var owned=true;var applied=0;val read=CompletableDeferred<Triple<ByteArray,String,String>>()
  val task=async(start=CoroutineStart.UNDISPATCHED){runCatching{applyReceiptSelection({owned},{read.await()},{applied++})}}
  if(mode in listOf("stale","unresolved","stale-error"))owned=false
  if(mode=="cancel")read.cancel()else if(mode.endsWith("error"))read.completeExceptionally(IllegalArgumentException("Synthetic"))else read.complete(Triple(byteArrayOf(1),"synthetic.pdf","application/pdf"))
  val result=task.await();check(applied==if(mode=="current")1 else 0);if(mode in listOf("error","cancel"))check(result.isFailure)else check(result.getOrNull()==(mode=="current"))
 }
 println("PASS 32 actual attachment/codes read-owner, delayed response, checksum and retained-save scenarios")
}
'''.replace('OWNER',owner).replace('HANDLERS',handlers)
with tempfile.TemporaryDirectory(prefix='apex-retained-read-') as temp:
 temp=Path(temp);(temp/'Proof.kt').write_text(fixture);run_proof(args,[temp/'Proof.kt'],temp)
