"""Compile the actual ImportTool save callback with synthetic API boundaries."""
from pathlib import Path
import argparse,sys,tempfile
root=Path(__file__).resolve().parents[3];sys.path.insert(0,str(root/'native/tests'))
from kotlin_toolchain import add_arguments,run_proof
parser=argparse.ArgumentParser();add_arguments(parser);args=parser.parse_args()
s=(root/'native/android/app/src/main/java/com/apexbooks/accounting/ImportTool.kt').read_text()
line=next(line for line in s.splitlines() if 'ActionDialog(title,vm,' in line)
body=line.split('onSave={',1)[1].rsplit('}){',1)[0]
fixture='''
import com.apexbooks.accounting.data.ImportReceiptRecovery
import kotlinx.coroutines.*
import java.nio.file.Files
class JSONObject(private val text:String="body"){fun s(key:String)=if(key=="operation_key")text else "";fun a(key:String)=JSONArray();fun optBoolean(key:String)=true;override fun toString()=text}
class JSONArray{fun length()=0}
class ApiFailure(val status:Int,message:String):Exception(message)
class Api{var keys=mutableListOf<String?>();var failure:Exception?=null;var after:(()->Unit)?=null;suspend fun request(path:String,method:String,body:JSONObject,key:String?):Any{keys.add(key);after?.invoke();failure?.let{throw it};return JSONObject(key?:"")}}
class VM{val api=Api();var canWrite=true;var tool="master_import";var toolData:Any?=null;var notice="";var refreshes=0;fun supports(value:String)=true;suspend fun refresh(){refreshes++};suspend fun loadCompanies(id:String){} }
suspend fun ActionDialog(onSave:suspend()->Unit){onSave()}
fun main()=runBlocking{
 val directory=Files.createTempDirectory("apex-import-save-").toFile()
 try {
  val vm=VM();val receipt=ImportReceiptRecovery(java.io.File(directory,"receipt"));var reading=false;var owned=true;val owner={owned};val tool="master_import";val kind="party";val prepared=JSONObject("private payload");val preparedInput="original"
  fun identity()="original"
  val scope="posting";val report:JSONObject?=null
  fun endpoint(stage:String)="/synthetic"
  suspend fun save(){ActionDialog(onSave={BODY})}
  vm.api.failure=java.io.IOException("lost");check(runCatching{save()}.isFailure);check(receipt.pending&&!reading)
  val first=vm.api.keys.single();vm.api.failure=ApiFailure(422,"later rejection");check(runCatching{save()}.isFailure);check(receipt.pending)
  vm.api.failure=null;save();check(!receipt.pending);check(vm.api.keys.all{it==first});check(vm.refreshes==1)
  vm.canWrite=false;check(runCatching{save()}.isFailure);check(vm.api.keys.size==3)
  vm.canWrite=true;vm.api.failure=java.io.IOException("old error");vm.api.after={owned=false};check(runCatching{save()}.isSuccess);check(receipt.pending);check(vm.refreshes==1)
  println("PASS actual Android import save: keyed replay, unknown/422 preservation, success, role guard, stale error")
 }finally{directory.deleteRecursively()}
}
'''.replace('BODY',body)
with tempfile.TemporaryDirectory(prefix='apex-import-save-compile-') as directory:
 d=Path(directory);(d/'Proof.kt').write_text(fixture);run_proof(args,[root/'native/android/app/src/main/java/com/apexbooks/accounting/data/ImportReceiptRecovery.kt',d/'Proof.kt'],d)
