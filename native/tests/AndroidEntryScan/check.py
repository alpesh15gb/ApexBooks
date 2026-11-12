from pathlib import Path
import argparse,sys,tempfile
root=Path(__file__).resolve().parents[3];sys.path.insert(0,str(root/'native/tests'))
from kotlin_toolchain import add_arguments,run_proof
p=argparse.ArgumentParser();add_arguments(p);p.add_argument('--source',type=Path);args=p.parse_args()
s=args.source.read_text() if args.source else (root/'native/android/app/src/main/java/com/apexbooks/accounting/EntryEditor.kt').read_text()
method=s[s.index('    fun scan('):s.rindex('\n}')] if not args.source else s
fixture='''import kotlinx.coroutines.*
class JSONObject{val values=mutableMapOf<String,String>();fun put(k:String,v:String)=apply{values[k]=v};override fun toString()=values.toString()}
fun JSONObject.s(k:String)=values[k]?:""
fun JSONObject.o(k:String)=this
fun JSONObject.a(k:String)=emptyList<JSONObject>()
fun List<JSONObject>.objects()=this
fun today()="2026-04-01"
class LineState(val value:JSONObject,regular:Boolean,importedFromOcr:Boolean=false){fun json()=value}
class Api{var epoch=0;var signedIn=true;var posts=0;val gate=CompletableDeferred<Unit>();var failure=false;fun captureSession():()->Unit{val before=epoch;return{check(signedIn&&epoch==before)}};fun company(id:String,path:String)=id+path;suspend fun request(path:String,verb:String,body:JSONObject):Any{posts++;gate.await();if(failure)throw Exception("OCR failed");return JSONObject().put("supplier_name","Recognized supplier")}}
class Files{val gate=CompletableDeferred<Unit>();suspend fun image(uri:android.net.Uri,size:Int,bytes:Int):String{gate.await();return "synthetic-image"}}
class VM(val scope:CoroutineScope){val api=Api();val files=Files();var companyId="a";var generation=0;var epoch=0;var ready=true;var writer=true;val canWrite get()=ready&&writer;var editor:Editor?=null;var notice="";var error="";val company=JSONObject().put("state_code","27");val jobs=mutableListOf<Job>();fun readStamp()=epoch;fun canRead(id:String,stamp:Int)=ready&&companyId==id&&epoch==stamp;fun inWorkspace(id:String,stamp:Int)=companyId==id&&generation==stamp;fun task(action:suspend()->Unit){jobs+=scope.launch(start=CoroutineStart.UNDISPATCHED){try{action()}catch(e:Exception){error=e.message?:"error"}}}}
class Editor(val vm:VM){val companyId="a";val workspaceStamp=0;val regular=true;var scanning=false;var saving=false;var sourceLoading=false;var retryPending=false;var ocrTotal="";val fields=mutableMapOf("name" to "Retained supplier");val lines=mutableListOf(LineState(JSONObject().put("quantity","2"),true));fun set(k:String,v:String){fields[k]=v};fun get(k:String)=fields[k]?:""
METHOD
}
fun main()=runBlocking{
 for(stage in listOf("image","ocr"))for(mode in listOf("current","company","access","recovered","session","editor","role","field","line"))for(fails in listOf(false,true)){
 val vm=VM(this);val editor=Editor(vm);vm.editor=editor;vm.api.failure=fails
 if(stage=="ocr")vm.files.gate.complete(Unit)
 editor.scan(android.net.Uri());check(editor.scanning)
 when(mode){"company"->vm.companyId="b";"access"->{vm.epoch++;vm.ready=false};"recovered"->vm.epoch++;"session"->vm.api.epoch++;"editor"->vm.editor=Editor(vm);"role"->vm.writer=false;"field"->editor.set("name","Newer edit");"line"->editor.lines[0].value.put("quantity","9")}
 vm.files.gate.complete(Unit);vm.api.gate.complete(Unit);vm.jobs.last().join()
 check(!editor.scanning)
 val changed=mode!="current";check(vm.api.posts==if(stage=="image"&&changed)0 else 1){"Stale image dispatched for $mode"}
 check(editor.get("name")==if(mode=="current"&&!fails)"Recognized supplier" else if(mode=="field")"Newer edit" else "Retained supplier"){"Draft replaced for $stage/$mode"}
 if(mode !in listOf("current","field","line"))check(vm.error.isBlank())
 }
 val vm=VM(this);val e=Editor(vm);vm.editor=e;e.retryPending=true;e.scan(android.net.Uri());check(vm.jobs.isEmpty());e.retryPending=false;e.scan(android.net.Uri());e.scan(android.net.Uri());check(vm.jobs.size==1);vm.files.gate.complete(Unit);vm.api.gate.complete(Unit);vm.jobs.last().join()
 println("PASS actual scan: 36 delayed image/OCR outcomes, stale dispatch/draft/error guards, unresolved and duplicate guards")
}
'''.replace('METHOD',method)
with tempfile.TemporaryDirectory(prefix='apex-scan-') as folder:
 d=Path(folder);(d/'Proof.kt').write_text(fixture);(d/'Uri.kt').write_text('package android.net\nclass Uri')
 run_proof(args,[d/'Proof.kt',d/'Uri.kt'],d)
