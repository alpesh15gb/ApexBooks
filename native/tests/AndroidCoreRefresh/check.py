"""Compile the production AppModel refresh method with controlled JVM reads."""
from pathlib import Path
import argparse,subprocess,tempfile
root=Path(__file__).resolve().parents[3]
import sys
sys.path.insert(0,str(root/'native/tests'))
from kotlin_toolchain import add_arguments,run_proof
p=argparse.ArgumentParser();add_arguments(p);args=p.parse_args()
source=(root/'native/android/app/src/main/java/com/apexbooks/accounting/AppModel.kt').read_text()
# Completion callbacks have dedicated AndroidImportCompletion/AndroidEntryCompletion suites.
# Extract only refresh: including adjacent methods makes this fixture drift silently.
method=source[source.index('    suspend fun refresh()'):source.index('    suspend fun finishConfirmedImport(',source.index('    suspend fun refresh()'))]
fixture='''import kotlinx.coroutines.*
import com.apexbooks.accounting.scopedCoreRefresh
class ApiFailure(val status:Int):Exception("Synthetic failure")
class JSONArray(val rows:List<Int>)
fun JSONArray.objects()=rows
class Api {val rows=CompletableDeferred<List<Int>>();val banks=CompletableDeferred<JSONArray>();suspend fun records(id:String)=rows.await();suspend fun request(path:String):Any=banks.await();fun company(id:String,path:String)=id+path}
class Draft{val text="unsaved draft";var preview:Any?="old preview"}
class Model {val api=Api();var readEpoch=0;var detail:Any?="detail";var statement:Any?="statement";var pdf:Any?="pdf";fun closePdf(){pdf=null};fun readStamp()=(generation.toLong() shl 32) or readEpoch.toLong();fun canRead(id:String,stamp:Long)=signedIn&&recordsReady&&companyId==id&&readStamp()==stamp;var companyId="A";var signedIn=true;var generation=1;var refreshSequence=0;var records=listOf(10);var banks=listOf(20);var recordsReady=true;var revision=0;val editor=Draft();fun inWorkspace(id:String,stamp:Int)=signedIn&&companyId==id&&generation==stamp
METHOD
}
fun main()=runBlocking {
 for(mode in listOf("mixed","transient","stale","success")){
  val m=Model();var error:Exception?=null
  val work=launch(start=CoroutineStart.UNDISPATCHED){try{m.refresh()}catch(e:Exception){error=e}}
  yield();if(mode=="stale"){m.generation++;m.companyId="B"}
  if(mode=="success"){m.api.rows.complete(listOf(1));m.api.banks.complete(JSONArray(listOf(2)))}else{m.api.rows.completeExceptionally(ApiFailure(503));m.api.banks.completeExceptionally(ApiFailure(if(mode=="transient")503 else 404))}
  work.join();check(m.editor.text=="unsaved draft")
  when(mode){"mixed"->{check(m.records.isEmpty()&&m.banks.isEmpty()&&!m.recordsReady&&error!=null&&m.detail==null&&m.statement==null&&m.pdf==null&&m.editor.preview==null&&m.readEpoch==1);m.recordsReady=true;check(!m.canRead("A",1L shl 32)&&m.canRead("A",m.readStamp()))};"transient"->{check(m.records==listOf(10)&&m.banks==listOf(20)&&error!=null)};"stale"->{check(m.records==listOf(10)&&m.banks==listOf(20)&&error==null)};else->{check(m.records==listOf(1)&&m.banks==listOf(2)&&m.recordsReady&&m.revision==1&&error==null)}}
  println("PASS actual AppModel refresh: $mode preserves draft and scopes cache/error")
 }
}
'''.replace('METHOD',method)
with tempfile.TemporaryDirectory(prefix='apex-core-refresh-') as temp:
 temp=Path(temp);(temp/'Proof.kt').write_text(fixture)
 run_proof(args,[root/'native/android/app/src/main/java/com/apexbooks/accounting/ScopedCoreRefresh.kt',temp/'Proof.kt'],temp)
