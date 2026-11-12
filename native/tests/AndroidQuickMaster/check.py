from pathlib import Path
import argparse,sys,tempfile
root=Path(__file__).resolve().parents[3];sys.path.insert(0,str(root/'native/tests'))
from kotlin_toolchain import add_arguments,run_proof
p=argparse.ArgumentParser();add_arguments(p);p.add_argument('--source',type=Path);args=p.parse_args()
s=args.source.read_text() if args.source else (root/'native/android/app/src/main/java/com/apexbooks/accounting/EntryEditor.kt').read_text()
methods=s if args.source else s[s.index('    private val quickSubmission='):s.index('    fun targets()')].replace('var quickPending by mutableStateOf(false);private set','var quickPending=false')
screen=(root/'native/android/app/src/main/java/com/apexbooks/accounting/EntryScreen.kt').read_text()
assert 'editor.retryPending || editor.quickPending' in screen
assert 'editor::recoverQuickMaster' in screen
assert '!editor.quickPending && idle' in screen
assert 'editor?.quickPending != true' in (root/'native/android/app/src/main/java/com/apexbooks/accounting/AppModel.kt').read_text()
retry=(root/'native/android/app/src/main/java/com/apexbooks/accounting/data/RetrySubmission.kt').read_text();retry=retry[retry.index('class RetrySubmission'): ]
fixture='''import kotlinx.coroutines.*
import java.math.BigDecimal
class JSONObject(text:String?=null){val values=mutableMapOf<String,Any>();init{if(text!=null)values.putAll(registry.getValue(text))};fun put(k:String,v:Any)=apply{values[k]=v};override fun toString():String{val text=values.toString();registry[text]=values.toMap();return text};companion object{val NULL=Any();val registry=mutableMapOf<String,Map<String,Any>>()}}
fun JSONObject.s(k:String)=values[k]?.toString()?:""
class ApiFailure(val status:Int,message:String):Exception(message)
fun today()="2026-04-01"
RETRY
class LineState{val uiKey="line";val values=JSONObject().put("description","Original item");fun get(k:String)=values.s(k);fun set(k:String,v:String){values.put(k,v)};fun json()=values}
class Api{var epoch=0;var signedIn=true;var calls=0;var fail=false;var failure:Exception?=null;val gate=CompletableDeferred<Unit>();val keys=mutableListOf<String>();val bodies=mutableListOf<String>();fun captureSession():()->Unit{val stamp=epoch;return{check(signedIn&&epoch==stamp)}};suspend fun saveRecord(cid:String,body:JSONObject,key:String):JSONObject{calls++;keys+=key;bodies+=body.toString();gate.await();failure?.let{throw it};if(fail)throw Exception("Current create failed");return JSONObject().put("id","created").put("name",body.s("name"))}}
class VM(val scope:CoroutineScope){val api=Api();var supportedFeatures=setOf("master_create_idempotency");var keyCount=0;fun key()="key-${++keyCount}";var companyId="a";var generation=0;var epoch=0;var ready=true;var writer=true;val canWrite get()=ready&&writer;var editor:Editor?=null;var notice="";var error="";var remembered=0;val jobs=mutableListOf<Job>();fun rememberMaster(row:JSONObject){remembered++};fun readStamp()=epoch;fun canRead(id:String,stamp:Int)=ready&&companyId==id&&epoch==stamp;fun inWorkspace(id:String,stamp:Int)=companyId==id&&generation==stamp;fun task(action:suspend()->Unit){jobs+=scope.launch(start=CoroutineStart.UNDISPATCHED){try{action()}catch(e:Exception){error=e.message?:"error"}}}}
class Editor(val vm:VM){val companyId="a";val workspaceStamp=0;val purchase=true;var quickAdding="";var blocked=false;val canEdit get()=vm.canWrite&&quickAdding.isBlank()&&!blocked&&!quickPending;val canQuickAdd get()=vm.canWrite&&"master_create_idempotency" in vm.supportedFeatures;val fields=mutableMapOf("name" to "Original party");val lines=mutableListOf(LineState());val calls get()=vm.api.calls;var fail:Boolean get()=vm.api.fail;set(v){vm.api.fail=v};val gate get()=vm.api.gate;fun get(k:String)=fields[k]?:"";var saving=false;var scanning=false;var sourceLoading=false;var retryPending=false

METHODS
}
fun main()=runBlocking{
 for(kind in listOf("party","item"))for(mode in listOf("edit","removed","current","company","access","recovered","session","editor","role"))for(failure in listOf(false,true)){
 val vm=VM(this);val e=Editor(vm);vm.editor=e;e.fail=failure;val line=e.lines.single();if(kind=="party")e.quickAddParty()else e.quickAddItem(line)
 when(mode){"edit"->{e.fields["name"]="Newer";line.set("description","Newer")};"removed"->{e.fields["party_id"]="different";e.lines.clear()};"company"->vm.companyId="b";"access"->{vm.epoch++;vm.ready=false};"recovered"->vm.epoch++;"session"->vm.api.epoch++;"editor"->vm.editor=Editor(vm);"role"->vm.writer=false}
 e.gate.complete(Unit);vm.jobs.last().join();val linked=if(kind=="party")e.get("party_id")=="created" else line.get("item_id")=="created"
 check(linked==(mode=="current"&&!failure)){"Unexpected linking $kind/$mode"};check(e.quickAdding.isBlank());if(mode !in listOf("current","edit","removed"))check(vm.remembered==0&&vm.error.isBlank())
 }
 for(kind in listOf("party","item")){val vm=VM(this);val e=Editor(vm);vm.editor=e;val line=e.lines.single();if(kind=="party"){e.quickAddParty();e.quickAddParty()}else{e.quickAddItem(line);e.quickAddItem(line)};check(e.calls==1);e.gate.complete(Unit);vm.jobs.last().join();val v=Editor(vm);vm.editor=v;vm.writer=false;if(kind=="party")v.quickAddParty()else v.quickAddItem(v.lines.single());check(v.calls==1)}
 for(kind in listOf("party","item")){
 val vm=VM(this);val e=Editor(vm);vm.editor=e;e.gate.complete(Unit);e.fail=true;if(kind=="party")e.quickAddParty()else e.quickAddItem(e.lines.single());vm.jobs.last().join();check(e.quickPending);val key=vm.api.keys.single();val body=vm.api.bodies.single();e.fields["name"]="Changed";e.lines.single().set("description","Changed");if(kind=="party")e.quickAddParty()else e.quickAddItem(e.lines.single());check(e.calls==1);vm.supportedFeatures=emptySet();e.recoverQuickMaster();check(e.calls==1&&e.quickPending);vm.supportedFeatures=setOf("master_create_idempotency");vm.writer=false;e.recoverQuickMaster();check(e.calls==1);vm.writer=true;e.fail=false;e.recoverQuickMaster();vm.jobs.last().join();check(e.calls==2&&!e.quickPending&&vm.api.keys.all{it==key}&&vm.api.bodies.all{it==body});check(e.get("party_id").isBlank()&&e.lines.single().get("item_id").isBlank())
 val old=VM(this);val legacy=Editor(old);old.editor=legacy;old.supportedFeatures=emptySet();legacy.quickAddParty();check(legacy.calls==0)
 val v=VM(this);val rejected=Editor(v);v.editor=rejected;rejected.gate.complete(Unit);v.api.failure=ApiFailure(422,"invalid");rejected.quickAddParty();v.jobs.last().join();check(!rejected.quickPending);v.api.failure=null;rejected.fields["name"]="Corrected";rejected.quickAddParty();v.jobs.last().join();check(v.api.keys.distinct().size==2&&v.api.bodies.last().contains("Corrected"))
 }
 println("PASS original unknown retry, capability/role loss, legacy no-dispatch and corrected definitive rejection")
 println("PASS actual Android quick-add callbacks: 36 party/item delayed cases, duplicate/viewer guards")
}
'''.replace('METHODS',methods).replace('RETRY',retry)
with tempfile.TemporaryDirectory(prefix='apex-quick-master-') as folder:
 d=Path(folder);(d/'Proof.kt').write_text(fixture);run_proof(args,[d/'Proof.kt'],d)
