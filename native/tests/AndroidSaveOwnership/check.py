"""Compile actual NativeFiles save methods with a synthetic picker/content resolver."""
from pathlib import Path
import argparse,sys,tempfile
root=Path(__file__).resolve().parents[3];sys.path.insert(0,str(root/'native/tests'))
from kotlin_toolchain import add_arguments,run_proof
p=argparse.ArgumentParser();add_arguments(p);args=p.parse_args()
s=(root/'native/android/app/src/main/java/com/apexbooks/accounting/NativeFiles.kt').read_text()
app=(root/'native/android/app/src/main/java/com/apexbooks/accounting/AppModel.kt').read_text()
wiring=app[app.index('    val files=NativeFiles('):app.index('    private var generation=')]
methods=s[s.index('    fun save(bytes:'):s.index('    suspend fun read(')]
fixture=r'''
import kotlinx.coroutines.*
import java.io.*
class Uri
class Resolver{var opens=0;val output=ByteArrayOutputStream();fun openOutputStream(uri:Uri,mode:String):OutputStream{opens++;return output}}
class Context{val contentResolver=Resolver()}
class Files(val context:Context,val captureSaveAccess:()->()->Unit){
 var launchSave:((String)->Unit)?={};var export:ByteArray?=null;var exportFile:File?=null;var exportFinished:((Boolean)->Unit)?=null;var exportAccess:(()->Unit)?=null
 var errorText="";fun error(message:String){errorText=message}
 METHODS
}
class Api{var generation=0;fun captureSession():()->Unit{val stamp=generation;return{check(stamp==generation)}}}
class NativeFiles(val context:Context,val captureSaveAccess:()->()->Unit,val error:(String)->Unit)
class Model{val application=Context();val api=Api();var signedIn=true;var companyId="a";var recordsReady=true;var access=0;var error="";fun readStamp()=access
 WIRING
}
fun main()=runBlocking {
 for(kind in listOf("bytes","file"))for(change in listOf(false,true)){
  val context=Context();var generation=1;val outcomes=mutableListOf<Boolean>();val files=Files(context){val stamp=generation;{check(stamp==generation){"Workspace changed"}}}
  val source=File.createTempFile("synthetic-save-",".part");source.writeBytes(byteArrayOf(1,2,3))
  try{if(kind=="bytes")files.save(byteArrayOf(1,2,3),"synthetic.bin")else files.saveFile(source,"synthetic.bin"){outcomes+=it}
   if(change)generation++
   val result=runCatching{files.saved(Uri())}
   if(change){check(result.isFailure){"Stale picker wrote $kind after workspace changed"};check(context.contentResolver.opens==0)}else{check(result.isSuccess);check(context.contentResolver.output.toByteArray().contentEquals(byteArrayOf(1,2,3)))}
   if(kind=="file")check(outcomes==listOf(!change))
  }finally{source.delete()}
 }
 for(change in listOf("none","session","company","denied","recovered","signed-out")){
  val model=Model();val verify=model.files.captureSaveAccess();when(change){"session"->model.api.generation++;"company"->model.companyId="b";"denied"->model.recordsReady=false;"recovered"->model.access++;"signed-out"->model.signedIn=false}
  check(runCatching{verify()}.isSuccess==(change=="none"))
 }
 run{val context=Context();val files=Files(context){{}};var launches=0;files.launchSave={launches++};files.save(byteArrayOf(1),"first.bin");files.save(byteArrayOf(2),"second.bin");check(launches==1);check(files.errorText.contains("Finish or cancel"));files.saved(Uri());check(context.contentResolver.output.toByteArray().contentEquals(byteArrayOf(1)))}
 for(mode in listOf("cancel","unavailable","throws")){
  val context=Context();val files=Files(context){{}};val outcomes=mutableListOf<Boolean>();val source=File.createTempFile("synthetic-save-",".part")
  try{if(mode=="unavailable")files.launchSave=null;if(mode=="throws")files.launchSave={throw Exception("picker failed")};files.saveFile(source,"synthetic.bin"){outcomes+=it};if(mode=="cancel")files.saved(null);check(outcomes==listOf(false));check(context.contentResolver.opens==0);check(files.exportAccess==null)}finally{source.delete()}
 }
 println("PASS actual AppModel session/company/access capture, duplicate save and cancellation/picker failure")
 println("PASS actual save-picker byte/file ownership before final write")
}
'''.replace('METHODS',methods).replace('WIRING',wiring)
with tempfile.TemporaryDirectory(prefix='apex-save-ownership-') as temp:
 temp=Path(temp);(temp/'Proof.kt').write_text(fixture);run_proof(args,[temp/'Proof.kt'],temp)
