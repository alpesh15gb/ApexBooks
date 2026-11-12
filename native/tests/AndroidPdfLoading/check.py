"""Compile actual AppModel PDF request methods in a deterministic JVM transport seam."""
from pathlib import Path
import argparse,subprocess,tempfile,os
root=Path(__file__).resolve().parents[3]
import sys
sys.path.insert(0,str(root/'native/tests'))
from kotlin_toolchain import add_arguments,run_proof
p=argparse.ArgumentParser();add_arguments(p);args=p.parse_args()
source=(root/'native/android/app/src/main/java/com/apexbooks/accounting/AppModel.kt').read_text()
methods=source[source.index('    fun closePdf()'):source.index('    fun key()')]
screen=(root/'native/android/app/src/main/java/com/apexbooks/accounting/PdfScreen.kt').read_text()
for required in ['document.template','if(active())vm.documentPdf','Retry format','Retry preview','Retry page','openError.isNotBlank()','pageError.isNotBlank()','vm.files.openPdf','vm.recordsReady&&vm.pdf===document&&!vm.pdfLoading']:
 assert required in screen,required
fixture='''import kotlinx.coroutines.*
class JSONObject(val text:String){override fun toString()=text}
fun JSONObject.s(key:String)=when(key){"id"->text;"kind"->"sales_invoice";else->"INV-1"}
fun encode(value:String)=value
fun friendly(value:String)=value
class ApiFailure(val status:Int):Exception("Synthetic HTTP error")
data class PdfView(val bytes:ByteArray,val name:String,val record:JSONObject?=null,val template:String="")
class Api{val pending=mutableListOf<CompletableDeferred<ByteArray>>();fun company(id:String,path:String)="/$id$path";suspend fun bytes(path:String):ByteArray{val next=CompletableDeferred<ByteArray>();pending+=next;return next.await()}}
class Model(val scope:CoroutineScope){val api=Api();var companyId="A";var generation=1;var readEpoch=0;var recordsReady=true;fun readStamp()=(generation.toLong() shl 32) or readEpoch.toLong();fun canRead(id:String,stamp:Long)=signedIn&&recordsReady&&companyId==id&&readStamp()==stamp;var page="sales_invoice";var signedIn=true;var pdf:PdfView?=PdfView(byteArrayOf(1),"old.pdf",JSONObject("record"),"modern");var pdfLoading=false;var pdfError="";var pdfRequestedTemplate="";var pdfRequest=0;var error="";val jobs=mutableListOf<Job>()
 fun inWorkspace(id:String,stamp:Int)=signedIn&&companyId==id&&generation==stamp
 fun task(action:suspend()->Unit){jobs+=scope.launch(start=CoroutineStart.UNDISPATCHED){action()}}
 fun failure(e:Exception){error=e.message?:"failed"}
 METHODS
}
fun main()=runBlocking{
 val row=JSONObject("record")
 run{val m=Model(this);val old=m.pdf;m.documentPdf(row,"evergreen");check(m.pdf===old&&m.pdf!!.template=="modern"&&m.pdfLoading);m.api.pending[0].completeExceptionally(Exception("Synthetic failure"));m.jobs.last().join();check(m.pdf===old&&!m.pdfLoading&&m.pdfError.isNotBlank());m.documentPdf(row,"evergreen");m.api.pending[1].complete(byteArrayOf(2));m.jobs.last().join();check(m.pdf!!.template=="evergreen"&&m.pdf!!.bytes.contentEquals(byteArrayOf(2)));println("PASS failed format retains matching label/bytes; retry commits both")}
 for(event in listOf("close","company","page","session","denied-recovered")){val m=Model(this);m.documentPdf(row,"evergreen");when(event){"close"->m.closePdf();"company"->{m.companyId="B";m.generation++;m.pdf=null};"page"->m.page="dashboard";"denied-recovered"->{m.readEpoch++;m.recordsReady=true};else->m.signedIn=false};m.api.pending[0].complete(byteArrayOf(2));m.jobs.last().join();check(m.pdf?.template!="evergreen");println("PASS stale $event cannot publish PDF")}
 run{val m=Model(this);m.documentPdf(row,"vintage");m.documentPdf(row,"evergreen");m.api.pending[1].complete(byteArrayOf(3));m.jobs[1].join();m.api.pending[0].completeExceptionally(Exception("obsolete failure"));m.jobs[0].join();check(m.pdf!!.template=="evergreen"&&m.pdfError.isBlank()&&!m.pdfLoading);println("PASS out-of-order request cannot overwrite PDF/error/loading")}
 run{val m=Model(this);m.pdf=null;m.documentPdf(row);m.api.pending[0].completeExceptionally(Exception("initial failure"));m.jobs[0].join();check(m.pdf==null&&m.error=="initial failure"&&!m.pdfLoading);println("PASS initial failure is terminal and visible")}
}
'''.replace(' METHODS',methods)
with tempfile.TemporaryDirectory(prefix='apex-pdf-loading-') as temp:
 path=Path(temp);(path/'Proof.kt').write_text(fixture)
 run_proof(args,[path/'Proof.kt'],path)
print('Production request methods compiled; preview error/retry wiring asserted. Full Compose/PdfRenderer/device acceptance remains open.')
