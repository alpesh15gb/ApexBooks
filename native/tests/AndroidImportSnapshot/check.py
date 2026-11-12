"""Compile production import ownership gate with delayed file/preview fixtures."""
from pathlib import Path
import argparse,sys,tempfile
root=Path(__file__).resolve().parents[3];sys.path.insert(0,str(root/'native/tests'))
from kotlin_toolchain import add_arguments,run_proof
p=argparse.ArgumentParser();add_arguments(p);args=p.parse_args()
s=(root/'native/android/app/src/main/java/com/apexbooks/accounting/ImportTool.kt').read_text()
methods=s[s.index('internal class ImportReadRequest'):s.index('@Composable fun ImportTool')]
assert 'preparedInput=input' in s and 'val input=identity();vm.task' in s
assert 'fun reset(){request.change();' in s and 'fun remap(){reset();' in s
assert 'if(!owner())return@ActionDialog' in s
fixture=r'''
import kotlinx.coroutines.*
METHODS
fun main()=runBlocking{
 for(mode in listOf("current","options","file","owner","closed","error","stale-error","cancel","duplicate")){
  val gate=ImportReadRequest();val ticket=gate.begin()!!;var owned=true;var published="previous";val response=CompletableDeferred<String>();var loads=0
  val result=async(start=CoroutineStart.UNDISPATCHED){runCatching{readImportSnapshot(gate,ticket,{owned},{loads++;response.await()},{published=it})}}
  if(mode in listOf("options","file","stale-error"))gate.change()
  if(mode in listOf("owner","closed"))owned=false
  if(mode=="duplicate")check(gate.begin()==null)
  if(mode=="cancel")response.cancel()else if(mode.endsWith("error"))response.completeExceptionally(IllegalArgumentException("Synthetic"))else response.complete("new")
  val outcome=result.await();val valid=mode in listOf("current","duplicate");check(published==if(valid)"new"else"previous");check(loads==1)
  if(mode in listOf("error","cancel"))check(outcome.isFailure)else check(outcome.getOrNull()==valid)
  check(gate.begin()!=null)
 }
 // Option changes that happen during payload preparation suppress network dispatch.
 run {val gate=ImportReadRequest();val ticket=gate.begin()!!;var calls=0;var published=false
  val result=readImportSnapshot(gate,ticket,{true},{current->gate.change();if(!current())throw IllegalStateException("Changed");calls++;"payload"},{published=true})
  check(!result&&calls==0&&!published)
 }
 // A stale request before it starts must not read a file at all.
 run {val gate=ImportReadRequest();val ticket=gate.begin()!!;var reads=0;check(!readImportSnapshot(gate,ticket,{false},{reads++;"file"},{error("Unexpected publish")}));check(reads==0)}
 println("PASS 11 production import gate cases: options/file/access, stale errors, cancellation, duplicate preview and failed replacement preservation")
}
'''.replace('METHODS',methods)
with tempfile.TemporaryDirectory(prefix='apex-import-snapshot-') as d:
 d=Path(d);(d/'Proof.kt').write_text(fixture);run_proof(args,[d/'Proof.kt'],d)
