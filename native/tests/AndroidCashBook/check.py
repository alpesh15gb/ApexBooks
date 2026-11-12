"""Compile active CashBookTool load/export bodies with controlled transports."""
from pathlib import Path
import argparse,sys,tempfile
root=Path(__file__).resolve().parents[3];sys.path.insert(0,str(root/'native/tests'))
from kotlin_toolchain import add_arguments,run_proof
p=argparse.ArgumentParser();add_arguments(p);args=p.parse_args()
source=(root/'native/android/app/src/main/java/com/apexbooks/accounting/AccountingSafetyTools.kt').read_text().split('@Composable fun CashBookTool')[1]
load=source.split('    LaunchedEffect(cid,requested,attempt) {',1)[1].split('\n    }\n    ActionDialog',1)[0].replace('return@LaunchedEffect','return')
export=source.split('            val snapshot=applied?:return@OutlinedButton',1)[1].split('\n        })',1)[0]
query=next(line.strip() for line in source.splitlines() if line.strip().startswith('fun query('))
fixture='''import kotlinx.coroutines.*
fun encode(value:String)=java.net.URLEncoder.encode(value,"UTF-8")
class Api {val reads=mutableListOf<Pair<String,CompletableDeferred<String>>>();val downloads=mutableListOf<Pair<String,CompletableDeferred<ByteArray>>>();fun company(id:String,path:String)="/$id$path";suspend fun request(path:String):Any{val d=CompletableDeferred<String>();reads+=path to d;return withContext(NonCancellable){d.await()}};suspend fun bytes(path:String):ByteArray{val d=CompletableDeferred<ByteArray>();downloads+=path to d;return d.await()}}
class Files{val saved=mutableListOf<String>();fun save(bytes:ByteArray,name:String){saved+=name}}
class Model(val scope:CoroutineScope){val api=Api();val files=Files();var recordsReady=true;var epoch=0;var tool="cashbook";fun readStamp()=epoch;fun canRead(id:String,stamp:Int)=recordsReady&&epoch==stamp;val jobs=mutableListOf<Job>();fun task(fn:suspend()->Unit){jobs+=scope.launch(start=CoroutineStart.UNDISPATCHED){fn()}}}
class Book(val vm:Model){val cid="A";var requested=Triple("2026-04-01","2026-04-30","bank A");var applied:Triple<String,String,String>?=null;var report:Any?=null;var loading=false;var failure=""
QUERY
suspend fun load(){LOAD}
fun export(fmt:String){val snapshot=applied?:return;EXPORT}
}
fun main()=runBlocking {
 val m=Model(this);val b=Book(m);val a=b.requested
 val first=launch(start=CoroutineStart.UNDISPATCHED){b.load()};m.api.reads.last().second.complete("A rows");first.join();check(b.applied==a)
 b.requested=Triple("2026-05-01","2026-05-31","bank B")
 b.export("xlsx");check(m.api.downloads.last().first.endsWith("?from_date=2026-04-01&to_date=2026-04-30&bank_account_id=bank+A"));m.api.downloads.last().second.complete(byteArrayOf(1));m.jobs.last().join()
 val failed=launch(start=CoroutineStart.UNDISPATCHED){b.load()};m.api.reads.last().second.completeExceptionally(Exception("Synthetic failure"));failed.join();check(b.applied==a&&b.report=="A rows"&&b.failure.isNotBlank());println("PASS edited and failed filters export the displayed snapshot")
 val stale=launch(start=CoroutineStart.UNDISPATCHED){b.load()};stale.cancel();m.api.reads.last().second.complete("obsolete");stale.join();check(b.applied==a&&b.report=="A rows");println("PASS cancelled stale load cannot publish even when transport ignores cancellation")
 b.export("pdf");m.epoch++;m.api.downloads.last().second.complete(byteArrayOf(2));m.jobs.last().join();check(m.files.saved.size==1);println("PASS access denial/recovery suppresses old export side effect")
 b.export("pdf");m.tool="";m.api.downloads.last().second.complete(byteArrayOf(3));m.jobs.last().join();check(m.files.saved.size==1);println("PASS closed tool suppresses pending export")
}
'''.replace('QUERY',query).replace('LOAD',load).replace('EXPORT',export.lstrip(';'))
with tempfile.TemporaryDirectory(prefix='apex-cashbook-') as temp:
 temp=Path(temp);(temp/'Proof.kt').write_text(fixture);run_proof(args,[temp/'Proof.kt'],temp)
