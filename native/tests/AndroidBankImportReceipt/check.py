"""Compile actual bank-import save callback with restart and payload recovery boundaries."""
from pathlib import Path
import argparse,sys,tempfile
root=Path(__file__).resolve().parents[3];sys.path.insert(0,str(root/'native/tests'))
from kotlin_toolchain import add_arguments,run_proof
parser=argparse.ArgumentParser();add_arguments(parser);args=parser.parse_args()
s=(root/'native/android/app/src/main/java/com/apexbooks/accounting/ImportTool.kt').read_text()
line=next(line for line in s.splitlines() if 'ActionDialog(title,vm,' in line)
body=line.split('onSave={',1)[1].rsplit('}){',1)[0]
lookupLine=next(line for line in s.splitlines() if 'Text("Check original import")' in line)
lookup=lookupLine.split('onClick={',1)[1].rsplit('}){Text',1)[0]
fixture='''
import com.apexbooks.accounting.data.ImportReceiptRecovery
import kotlinx.coroutines.*
import java.nio.file.Files
class JSONObject(private val text:String="body"){fun s(key:String)=if(key=="operation_key")text else "";fun a(key:String)=JSONArray();fun optBoolean(key:String)=true;override fun toString()=text}
class JSONArray{fun length()=0}
class ApiFailure(val status:Int,message:String):Exception(message)
fun encode(value:String)=value
class Api{var gets=0;var receiptKey="";fun company(cid:String,path:String)=cid+path;suspend fun request(path:String):Any{gets++;failure?.let{throw it};return JSONObject(receiptKey)};var keys=mutableListOf<String?>();var failure:Exception?=null;var after:(()->Unit)?=null;suspend fun request(path:String,method:String,body:JSONObject,key:String?):Any{keys.add(key);after?.invoke();failure?.let{throw it};return JSONObject(key?:"")}}
class VM{val api=Api();var canWrite=true;var isOwner=true;var tool="statement_import";var toolData:Any?=null;var notice="";var refreshes=0;var refreshFailure:Exception?=null;var supported=true;fun supports(value:String)=supported&&value=="bank_import_receipts";suspend fun task(block:suspend()->Unit){block()};suspend fun refresh(){refreshes++;refreshFailure?.let{throw it}};suspend fun finishConfirmedImport(message:String="Import confirmed."){tool="";toolData=null;try{refresh();notice=message}catch(e:Exception){throw ApiFailure((e as? ApiFailure)?.status?:0,message+" Do not repeat the import. "+e.message)}};suspend fun loadCompanies(id:String){} }
suspend fun ActionDialog(onSave:suspend()->Unit){onSave()}
fun main()=runBlocking{
 val directory=Files.createTempDirectory("apex-import-save-").toFile()
 try {
  val vm=VM();val receipt=ImportReceiptRecovery(java.io.File(directory,"receipt"));var reading=false;var owned=true;val owner={owned};val tool="statement_import";val kind="party";var prepared=JSONObject("private bank payload");val preparedInput="original"
  fun identity()="original"
  val scope="posting";val report:JSONObject?=null
  fun endpoint(stage:String)="/synthetic"
  suspend fun save(){ActionDialog(onSave={BODY})}
  vm.api.failure=java.io.IOException("lost");check(runCatching{save()}.isFailure);check(receipt.pending&&!reading)
  check(receipt.marker?.kind=="bank")
  check(!java.io.File(directory,"receipt").readText().contains("private bank payload"))
  val restart=ImportReceiptRecovery(java.io.File(directory,"receipt"));check(restart.marker==receipt.marker)
  check(runCatching{restart.begin("changed bank or mapping","bank",true)}.isFailure)
  check(runCatching{restart.begin("private bank payload","bank",false)}.isFailure)
  val original=prepared;prepared=JSONObject("changed bank payload");check(runCatching{save()}.isFailure);check(vm.api.keys.size==1);prepared=original
  vm.supported=false;check(runCatching{save()}.isFailure);check(vm.api.keys.size==1);vm.supported=true
  check(ImportReceiptRecovery.location(directory,"origin","actor","company",true)!=ImportReceiptRecovery.location(directory,"origin","actor","company"))
  val first=vm.api.keys.single();vm.api.failure=ApiFailure(422,"later rejection");check(runCatching{save()}.isFailure);check(receipt.pending)
  vm.api.failure=null;save();check(!receipt.pending);check(vm.api.keys.all{it==first});check(vm.refreshes==1)
  vm.canWrite=false;check(runCatching{save()}.isFailure);check(vm.api.keys.size==3)
  vm.canWrite=true;vm.api.failure=java.io.IOException("old error");vm.api.after={owned=false};check(runCatching{save()}.isSuccess);check(receipt.pending);check(vm.refreshes==1)
  owned=true;vm.api.after=null;vm.api.failure=null
  receipt.confirmed(receipt.marker!!.key);vm.supported=false;save();check(vm.api.keys.last()==null&&!receipt.pending)
  vm.supported=true;vm.api.failure=java.io.IOException("lost for lookup");check(runCatching{save()}.isFailure)
  val marker=receipt.marker!!;val cid="company";vm.api.receiptKey=marker.key
  suspend fun lookup(){LOOKUP}
  val writes=vm.api.keys.size;vm.api.failure=ApiFailure(404,"missing receipt");check(runCatching{lookup()}.isFailure);check(receipt.pending)
  vm.api.failure=null;lookup();check(!receipt.pending&&vm.api.keys.size==writes&&vm.api.gets==2)
  vm.notice="";vm.refreshFailure=java.io.IOException("Refresh unavailable")
  val beforeRefreshFailure=vm.api.keys.size;val refreshError=runCatching{save()}.exceptionOrNull();check(refreshError?.message?.contains("confirmed")==true);check(vm.api.keys.size==beforeRefreshFailure+1&&!receipt.pending)
  vm.api.failure=java.io.IOException("lost before receipt recovery");check(runCatching{save()}.isFailure);vm.api.failure=null
  run{val marker=receipt.marker!!;vm.api.receiptKey=marker.key;suspend fun recover(){LOOKUP};val failure=runCatching{recover()}.exceptionOrNull();check(failure?.message?.contains("confirmed")==true&&!receipt.pending)}
  println("PASS actual Android bank import save/restart: keyed replay, unknown/422 preservation, success, role guard, stale error")
 }finally{directory.deleteRecursively()}
}
'''.replace('BODY',body).replace('LOOKUP',lookup)
with tempfile.TemporaryDirectory(prefix='apex-import-save-compile-') as directory:
 d=Path(directory);(d/'Proof.kt').write_text(fixture);run_proof(args,[root/'native/android/app/src/main/java/com/apexbooks/accounting/data/ImportReceiptRecovery.kt',d/'Proof.kt'],d)
