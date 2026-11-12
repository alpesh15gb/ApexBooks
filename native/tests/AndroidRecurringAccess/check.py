from pathlib import Path
import argparse,sys,tempfile
root=Path(__file__).resolve().parents[3];sys.path.insert(0,str(root/'native/tests'))
from kotlin_toolchain import add_arguments,run_proof
p=argparse.ArgumentParser();add_arguments(p);args=p.parse_args()
s=(root/'native/android/app/src/main/java/com/apexbooks/accounting/RecurringTools.kt').read_text();edit=s.split('@Composable private fun RecurringEdit(',1)[1].split('@Composable private fun RecurringOccurrence(',1)[0]
assert 'enabled=!loading&&(vm.canWrite||(!command.unresolved&&!changed()))' in edit
assert 'hasChanges=::changed' in edit
callback=edit.split('onSave={',1)[1].split('\n    })',1)[0];close=next(line.strip() for line in edit.splitlines() if 'fun close()' in line)
command=s[s.index('class RecurringCommand {'):s.index('fun recurringBusinessDate')]
write=s[s.index('private suspend fun recurringWrite('):s.index('@Composable private fun RecurringPending')]
retry=(root/'native/android/app/src/main/java/com/apexbooks/accounting/data/RetrySubmission.kt').read_text().split('class RetrySubmission',1)[1]
fixture=r'''
import kotlinx.coroutines.*
import java.util.UUID
import kotlin.reflect.KProperty
class State<T>(var value:T){operator fun getValue(owner:Any?,p:KProperty<*>)=value;operator fun setValue(owner:Any?,p:KProperty<*>,next:T){value=next}}
fun <T> mutableStateOf(value:T)=State(value)
class JSONObject(){companion object{val NULL=Any();val snapshots=mutableMapOf<String,Map<String,Any>>()};val data=linkedMapOf<String,Any>();constructor(text:String):this(){data.putAll(snapshots[text]!!)};fun put(k:String,v:Any):JSONObject{data[k]=v;return this};fun optBoolean(k:String)=data[k]==true;fun optInt(k:String)=data[k] as? Int?:0;override fun toString():String{val text=data.toString();snapshots[text]=data.toMap();return text}}
fun JSONObject.s(k:String)=data[k]?.toString().orEmpty()
fun encode(v:String)=v
class ApiFailure(val status:Int,message:String):Exception(message)
class RetrySubmission RETRY
COMMAND
class Api{var calls=0;var failure:Exception?=null;val bodies=mutableListOf<String>();val keys=mutableListOf<String>();fun company(id:String,path:String)=id+path;suspend fun request(path:String,method:String,body:JSONObject,key:String):Any{calls++;bodies.add(body.toString());keys.add(key);failure?.let{throw it};return JSONObject()}}
class AppModel{val api=Api();var canWrite=true;var companyId="a";var generation=0;var tool="recurring_edit";var toolData:JSONObject?=JSONObject();var notice="";var finishes=0;fun workspaceStamp()=generation;fun inWorkspace(cid:String,stamp:Int)=cid==companyId&&generation==stamp;fun finishRecurring(scope:String){finishes++}}
WRITE
suspend fun ActionDialog(onSave:suspend()->Unit){onSave()}
class Screen(val vm:AppModel=AppModel()){
 val cid=vm.companyId;val stamp=vm.workspaceStamp();val scope="edit:template";val command=RecurringCommand();val row=JSONObject().put("id","template").put("name","Original").put("is_active",true).put("version",1);var name="Original";var active=true;var source="";var loading=false
 init{vm.toolData=row}
 fun changed()=name!=row.s("name")||active!=row.optBoolean("is_active")||source.isNotBlank()
 CLOSE
 suspend fun save(){ActionDialog(onSave={CALLBACK})}
}
fun main()=runBlocking{
 val screen=Screen();screen.name="First edit";screen.vm.api.failure=java.io.IOException("response lost");check(runCatching{screen.save()}.isFailure);check(screen.command.unresolved);val key=screen.command.key;val original=screen.vm.api.bodies.single()
 screen.vm.canWrite=false;screen.name="Changed after unknown";runCatching{screen.save()};check(screen.command.unresolved&&screen.vm.finishes==0&&screen.vm.tool=="recurring_edit"){"Viewer Done discarded unresolved save"};check(screen.vm.api.calls==1&&screen.command.key==key)
 runCatching{screen.close()};check(screen.command.unresolved&&screen.vm.finishes==0)
 screen.vm.canWrite=true;screen.vm.api.failure=null;screen.save();check(screen.vm.api.calls==2&&screen.vm.api.keys.all{it==key}&&screen.vm.api.bodies.all{it==original}&&!screen.command.unresolved&&screen.vm.finishes==1)
 val dirty=Screen();dirty.name="Unsaved";dirty.vm.canWrite=false;check(runCatching{dirty.save()}.isFailure);check(dirty.name=="Unsaved"&&dirty.vm.finishes==0&&dirty.vm.api.calls==0)
 val viewer=Screen();viewer.vm.canWrite=false;viewer.save();check(viewer.vm.finishes==1&&viewer.vm.api.calls==0)
 val replaced=Screen();replaced.vm.toolData=JSONObject();replaced.save();replaced.close();check(replaced.vm.api.calls==0&&replaced.vm.finishes==0)
 val stale=Screen();stale.vm.companyId="b";stale.save();check(stale.vm.finishes==0&&stale.vm.api.calls==0);stale.close();check(stale.vm.finishes==0)
 println("PASS actual Android recurring edit callback/command: unknown viewer Done/close preserves key/body, editor recovery, dirty viewer preservation, clean viewer close, stale handlers")
}
'''.replace('RETRY',retry).replace('COMMAND',command).replace('WRITE',write).replace('CLOSE',close).replace('CALLBACK',callback)
with tempfile.TemporaryDirectory(prefix='apex-recurring-access-') as folder:
 d=Path(folder);(d/'Proof.kt').write_text(fixture);run_proof(args,[d/'Proof.kt'],d)
