from pathlib import Path
import argparse,sys,tempfile
root=Path(__file__).resolve().parents[3];sys.path.insert(0,str(root/'native/tests'))
from kotlin_toolchain import add_arguments,run_proof
p=argparse.ArgumentParser();add_arguments(p);args=p.parse_args()
source=(root/'native/android/app/src/main/java/com/apexbooks/accounting/AppModel.kt').read_text()
methods='\n'.join(line for line in source.splitlines() if line.startswith('    fun edit(') or line.startswith('    fun convert('))
fixture='''import kotlinx.coroutines.*
class JSONObject(val id:String="r",val kind:String="sales_invoice"){fun o(key:String)=this}
fun JSONObject.s(key:String)=if(key=="kind")kind else if(key=="id")id else ""
class EntryEditor(val vm:Model,val kind:String,val previous:JSONObject?=null,val conversion:JSONObject?=null){val text="retained draft";fun setReturnSourceLines(row:JSONObject){}}
class Api{val pending=CompletableDeferred<JSONObject>();suspend fun record(company:String,id:String)=pending.await()}
class Model(val scope:CoroutineScope){val api=Api();var companyId="A";var generation=1;var epoch=0;var recordsReady=true;val canWrite get()=recordsReady;fun readStamp()=epoch;fun canRead(id:String,stamp:Int)=id==companyId&&recordsReady&&epoch==stamp;var editor:EntryEditor?=EntryEditor(this,"estimate");var error="";val jobs=mutableListOf<Job>();fun task(action:suspend()->Unit){jobs+=scope.launch(start=CoroutineStart.UNDISPATCHED){try{action()}catch(e:Exception){error=e.message?:"error"}}}
METHODS
}
fun main()=runBlocking{
 for(operation in listOf("edit","convert"))for(outcome in listOf("success","denied","recovered","stale-error")){
  val m=Model(this);val retained=m.editor;if(operation=="edit")m.edit(JSONObject())else m.convert(JSONObject())
  if(outcome!="success"){m.epoch++;m.recordsReady=outcome=="recovered"}
  if(outcome=="stale-error")m.api.pending.completeExceptionally(Exception("obsolete"))else m.api.pending.complete(JSONObject())
  m.jobs.last().join();check(if(outcome=="success")m.editor!==retained else m.editor===retained);check(m.error.isBlank());println("PASS actual $operation: $outcome")
 }
}
'''.replace('METHODS',methods)
with tempfile.TemporaryDirectory(prefix='apex-editor-access-') as temp:
 temp=Path(temp);(temp/'Proof.kt').write_text(fixture);run_proof(args,[temp/'Proof.kt'],temp)
