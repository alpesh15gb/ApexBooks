from pathlib import Path
import argparse,sys,tempfile
root=Path(__file__).resolve().parents[3];sys.path.insert(0,str(root/'native/tests'))
from kotlin_toolchain import add_arguments,run_proof
parser=argparse.ArgumentParser();add_arguments(parser);args=parser.parse_args()
source=root/'native/android/app/src/main/java/com/apexbooks/accounting/data/ImportReceiptRecovery.kt'
fixture='''
import com.apexbooks.accounting.data.ImportReceiptRecovery
import java.nio.file.Files
fun main(){
 val folder=Files.createTempDirectory("apex-import-proof-").toFile()
 try {
  val path=ImportReceiptRecovery.location(folder,"https://synthetic.invalid","actor@example.invalid","company")
  val recovery=ImportReceiptRecovery(path);val body="SYNTHETIC PRIVATE CSV PAYLOAD"
  val first=recovery.begin(body,"party",true);check(first.key!=null&&!first.retry)
  check(!path.readText().contains(body));check(path.readText().split('\\n').size==3)
  check(runCatching{recovery.begin(body,"party",true)}.isFailure)
  recovery.failed(first,0);recovery.end();path.delete();val retained=recovery.begin(body,"party",true);check(retained.key==first.key&&retained.retry);recovery.end()
  val reopened=ImportReceiptRecovery(path);check(reopened.pending)
  check(runCatching{reopened.begin("changed", "party",true)}.isFailure)
  check(runCatching{reopened.begin(body,"party",false)}.isFailure)
  val retry=reopened.begin(body,"party",true);check(retry.key==first.key&&retry.retry)
  reopened.failed(retry,422);reopened.end();check(reopened.pending)
  check(runCatching{reopened.confirmed("wrong")}.isFailure)
  reopened.confirmed(first.key!!);check(!path.exists()&&!reopened.pending)
  val rejected=reopened.begin(body,"party",true);reopened.failed(rejected,422);reopened.end();check(!path.exists())
  val legacy=reopened.begin(body,"party",false);check(legacy.key==null&&!path.exists());reopened.end()
  check(ImportReceiptRecovery.location(folder,"https://other.invalid","actor@example.invalid","company")!=path)
  check(ImportReceiptRecovery.location(folder,"https://synthetic.invalid","other@example.invalid","company")!=path)
  check(ImportReceiptRecovery.location(folder,"https://synthetic.invalid","actor@example.invalid","other")!=path)
  val pool=java.util.concurrent.Executors.newFixedThreadPool(4)
  try {
   val barrier=java.util.concurrent.CyclicBarrier(4)
   val futures=(1..4).map{pool.submit<String>{barrier.await();val r=ImportReceiptRecovery(path);val a=r.begin(body,"party",true);r.end();a.key!!}}
   val keys=futures.map{it.get()};check(keys.toSet().size==1)
   ImportReceiptRecovery(path).confirmed(keys.first())
   val barrier2=java.util.concurrent.CyclicBarrier(4)
   val attempts=(1..4).map{index->pool.submit<Boolean>{barrier2.await();runCatching{ImportReceiptRecovery(path).begin(body+index,"party",true)}.isSuccess}}
   check(attempts.map{it.get()}.count{it}==1)
   val remaining=ImportReceiptRecovery(path);remaining.confirmed(remaining.marker!!.key)
  }finally{pool.shutdownNow()}
  path.writeText("corrupt");check(runCatching{ImportReceiptRecovery(path)}.isFailure)
  println("PASS Android receipt persistence, frozen retry, legacy gate, rejection, corruption and scope isolation")
 }finally{folder.deleteRecursively()}
}
'''
with tempfile.TemporaryDirectory(prefix='apex-receipt-compile-') as directory:
 d=Path(directory);(d/'Proof.kt').write_text(fixture);run_proof(args,[source,d/'Proof.kt'],d)
