from pathlib import Path
import argparse,sys,tempfile
root=Path(__file__).resolve().parents[3];sys.path.insert(0,str(root/'native/tests'))
from kotlin_toolchain import add_arguments,run_proof
p=argparse.ArgumentParser();add_arguments(p);p.add_argument('--source',type=Path);args=p.parse_args()
s=args.source.read_text() if args.source else (root/'native/android/app/src/main/java/com/apexbooks/accounting/EntryEditor.kt').read_text()
methods=s if args.source else s[s.index('    fun quickAddParty()'):s.index('    fun targets()')]
fixture='''import kotlinx.coroutines.*
import java.math.BigDecimal
class JSONObject{val values=mutableMapOf<String,String>();fun put(k:String,v:String)=apply{values[k]=v};override fun toString()=values.toString()}
fun JSONObject.s(k:String)=values[k]?:""
class LineState{val uiKey="line";val values=JSONObject().put("description","Original item");fun get(k:String)=values.s(k);fun set(k:String,v:String){values.put(k,v)};fun json()=values}
class Api{var epoch=0;var signedIn=true;fun captureSession():()->Unit{val stamp=epoch;return{check(signedIn&&epoch==stamp)}}}
class VM(val scope:CoroutineScope){val api=Api();var companyId="a";var generation=0;var epoch=0;var ready=true;var writer=true;val canWrite get()=ready&&writer;var editor:Editor?=null;var notice="";var error="";var remembered=0;val jobs=mutableListOf<Job>();fun rememberMaster(row:JSONObject){remembered++};fun readStamp()=epoch;fun canRead(id:String,stamp:Int)=ready&&companyId==id&&epoch==stamp;fun inWorkspace(id:String,stamp:Int)=companyId==id&&generation==stamp;fun task(action:suspend()->Unit){jobs+=scope.launch(start=CoroutineStart.UNDISPATCHED){try{action()}catch(e:Exception){error=e.message?:"error"}}}}
class Editor(val vm:VM){val companyId="a";val workspaceStamp=0;val purchase=true;var quickAdding="";var blocked=false;val canEdit get()=vm.canWrite&&quickAdding.isBlank()&&!blocked;val canQuickAdd get()=vm.canWrite;val fields=mutableMapOf("name" to "Original party");val lines=mutableListOf(LineState());var calls=0;var fail=false;val gate=CompletableDeferred<Unit>();fun get(k:String)=fields[k]?:"";suspend fun createMaster(kind:String,name:String,data:JSONObject):JSONObject{calls++;gate.await();if(fail)throw Exception("Current create failed");return JSONObject().put("id","created").put("name",name)}
METHODS
}
fun main()=runBlocking{
 for(kind in listOf("party","item"))for(mode in listOf("edit","removed","current","company","access","recovered","session","editor","role"))for(failure in listOf(false,true)){
 val vm=VM(this);val e=Editor(vm);vm.editor=e;e.fail=failure;val line=e.lines.single();if(kind=="party")e.quickAddParty()else e.quickAddItem(line)
 when(mode){"edit"->{e.fields["name"]="Newer";line.set("description","Newer")};"removed"->{e.fields["party_id"]="different";e.lines.clear()};"company"->vm.companyId="b";"access"->{vm.epoch++;vm.ready=false};"recovered"->vm.epoch++;"session"->vm.api.epoch++;"editor"->vm.editor=Editor(vm);"role"->vm.writer=false}
 e.gate.complete(Unit);vm.jobs.last().join();val linked=if(kind=="party")e.get("party_id")=="created" else line.get("item_id")=="created"
 check(linked==(mode=="current"&&!failure)){"Unexpected linking $kind/$mode"};check(e.quickAdding.isBlank());if(mode !in listOf("current","edit","removed"))check(vm.remembered==0&&vm.error.isBlank())
 }
 for(kind in listOf("party","item")){val vm=VM(this);val e=Editor(vm);vm.editor=e;val line=e.lines.single();if(kind=="party"){e.quickAddParty();e.quickAddParty()}else{e.quickAddItem(line);e.quickAddItem(line)};check(e.calls==1);e.gate.complete(Unit);vm.jobs.last().join();val v=Editor(vm);vm.editor=v;vm.writer=false;if(kind=="party")v.quickAddParty()else v.quickAddItem(v.lines.single());check(v.calls==0)}
 println("PASS actual Android quick-add callbacks: 36 party/item delayed cases, duplicate/viewer guards")
}
'''.replace('METHODS',methods)
with tempfile.TemporaryDirectory(prefix='apex-quick-master-') as folder:
 d=Path(folder);(d/'Proof.kt').write_text(fixture);run_proof(args,[d/'Proof.kt'],d)
