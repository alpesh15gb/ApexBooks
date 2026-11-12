"""Compile actual EntryEditor source-selection methods in a controlled JVM seam.
No Android runtime, device, server, credentials or production access is used.
"""
from pathlib import Path
import argparse,os,subprocess,tempfile
root=Path(__file__).resolve().parents[3]
p=argparse.ArgumentParser();p.add_argument('--kotlin-home',type=Path,required=True);args=p.parse_args()
source=(root/'native/android/app/src/main/java/com/apexbooks/accounting/EntryEditor.kt').read_text()
methods=source[source.index('    fun chooseSource(id:String)'):source.index('    fun body():JSONObject')]
screen=(root/'native/android/app/src/main/java/com/apexbooks/accounting/EntryScreen.kt').read_text()
assert 'if (editor.document && step == 2 && editor.canSaveAndNew) OutlinedButton' in screen
assert 'if (!editor.document && editor.canSaveAndNew)' not in screen
assert 'if(vm.editor===this)vm.editor=if(keepAfterSave)EntryEditor(vm,kind)else null' in source
assert 'submission.recordCommand(::body,::paymentBody)' in source
assert 'saveIntent.forAttempt(keepOpen&&canSaveAndNew,retryPending)' in source
fixture='''import kotlinx.coroutines.*
import com.apexbooks.accounting.additionalReturnQuantity
class JSONObject(val values:MutableMap<String,Any?> = linkedMapOf()) {
 fun s(key:String)=values[key] as? String ?: ""
 fun o(key:String)=values[key] as? JSONObject ?: JSONObject()
 fun a(key:String)=values[key] as? List<JSONObject> ?: emptyList()
 override fun toString()=values.toString()
}
fun List<JSONObject>.objects()=this
class LineState(val row:JSONObject,val regular:Boolean){fun set(key:String,value:String){row.values[key]=value};init{require(row.s("description")!="malformed")};override fun toString()=row.toString()}
class Api {
 val pending=mutableMapOf<String,CompletableDeferred<JSONObject>>();var calls=0
 suspend fun record(company:String,id:String):JSONObject {calls++;return pending.getOrPut(id){CompletableDeferred()}.await()}
}
class Model(val scope:CoroutineScope){val api=Api();var editor:Editor?=null;var stamp=1;var notice="";var error="";val jobs=mutableListOf<Job>()
 fun inWorkspace(company:String,version:Int)=company=="company"&&stamp==version
 fun task(action:suspend()->Unit){jobs+=scope.launch{try{action()}catch(e:Exception){error=e.message?:"failed"}}}
 suspend fun finish(){jobs.toList().forEach{it.join()}}
}
class Editor(val vm:Model){
 val companyId="company";val workspaceStamp=vm.stamp;val regular=false;val purchase=true
 val fields=linkedMapOf("name" to "Original supplier","applied_to" to "old");val lines=mutableListOf(LineState(JSONObject(linkedMapOf("description" to "Original line")),false))
 val returnSourceLines=mutableListOf<JSONObject>();var sourceSequence=0;var requestedSource:String?=null;var sourceLoading=false;var preview:JSONObject?=null;var previewError="";var dirty=false
 val canEdit get()=!sourceLoading
 fun changed()=dirty
 fun get(key:String)=fields[key]?:""
 fun set(key:String,value:String){fields[key]=value}
 fun body()=JSONObject(linkedMapOf("fields" to fields.toMap(),"lines" to lines.map{it.toString()}))
 fun setReturnSourceLines(row:JSONObject){returnSourceLines.clear();returnSourceLines.addAll(row.o("data").a("lines"))}
 fun supplierOrigin(data:JSONObject)=data.s("supplier_state").ifBlank{"27"}
'''+methods+'''
}
fun row(id:String,description:String="New line")=JSONObject(linkedMapOf("name" to "Supplier $id","data" to JSONObject(linkedMapOf("lines" to listOf(JSONObject(linkedMapOf("description" to description))),"supplier_state" to "36"))))
fun main()=runBlocking {
 check(additionalReturnQuantity("additional_returns","1.250")=="1.250")
 check(additionalReturnQuantity("additional_returns","0")=="0")
 for(value in listOf("","NaN","-1","abc"))check(additionalReturnQuantity("additional_returns",value)=="")
 check(additionalReturnQuantity("","2")=="")
 println("PASS known, exhausted and unknown return quantity defaults")
 suspend fun fresh():Pair<Model,Editor>{val m=Model(this);val e=Editor(m);m.editor=e;return m to e}
 run {val(m,e)=fresh();val before=e.body().toString();e.chooseSource("new");yield();check(e.sourceLoading&&e.body().toString()==before);m.api.pending["new"]!!.completeExceptionally(Exception("503 synthetic"));m.finish();check(e.body().toString()==before&&!e.sourceLoading);e.chooseSource("retry");yield();m.api.pending["retry"]!!.complete(row("retry"));m.finish();check(e.get("applied_to")=="retry"&&e.get("name")=="Supplier retry");println("PASS failed fetch preserves draft and retry atomically replaces it")}
 run {val(m,e)=fresh();e.dirty=true;e.chooseSource("new");check(e.requestedSource=="new"&&m.api.calls==0);e.cancelSourceChange();check(e.requestedSource==null&&e.get("applied_to")=="old");e.chooseSource("new");e.confirmSourceChange();yield();m.api.pending["new"]!!.complete(row("new"));m.finish();check(e.get("applied_to")=="new");println("PASS dirty replacement waits for confirmation; Keep editing preserves draft")}
 for(stale in listOf("company","editor","draft")){val(m,e)=fresh();e.chooseSource("new");yield();when(stale){"company"->m.stamp++;"editor"->m.editor=Editor(m);else->e.set("name","Edited meanwhile")};m.api.pending["new"]!!.complete(row("new"));m.finish();check(e.get("applied_to")=="old");println("PASS stale $stale response cannot replace draft")}
 run {val(m,e)=fresh();val before=e.body().toString();e.chooseSource("bad");yield();m.api.pending["bad"]!!.complete(row("bad","malformed"));m.finish();check(e.body().toString()==before);println("PASS parse failure preserves draft")}
 run {val(m,e)=fresh();e.chooseSource("new");e.chooseSource("duplicate");yield();check(m.api.calls==1);m.api.pending["new"]!!.completeExceptionally(Exception("failed"));m.finish();println("PASS pending source change is single-flight")}
}
'''
with tempfile.TemporaryDirectory(prefix='apex-source-selection-') as temp:
 path=Path(temp);(path/'Proof.kt').write_text(fixture)
 cp=os.pathsep.join(str(x) for x in (args.kotlin_home/'lib').glob('*.jar'))
 subprocess.run(['java','-cp',cp,'org.jetbrains.kotlin.cli.jvm.K2JVMCompiler','-kotlin-home',str(args.kotlin_home),'-classpath',cp,'-d',str(path/'proof.jar'),str(path/'Proof.kt'),str(root/'native/android/app/src/main/java/com/apexbooks/accounting/ReturnCapacity.kt')],check=True)
 subprocess.run(['java','-cp',str(path/'proof.jar')+os.pathsep+cp,'ProofKt'],check=True)
print('Save & new Review placement/reset/retry wiring assertions passed; full Compose/device acceptance remains required.')
