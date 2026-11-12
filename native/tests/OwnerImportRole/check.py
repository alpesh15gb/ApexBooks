"""Compile real native bank import save/verification callbacks with role transitions."""
from pathlib import Path
import argparse,sys,tempfile,subprocess,os
root=Path(__file__).resolve().parents[3];sys.path.insert(0,str(root/'native/tests'))
from kotlin_toolchain import add_arguments,run_proof
p=argparse.ArgumentParser();add_arguments(p);p.add_argument('--dotnet',default='dotnet');p.add_argument('--android-only',action='store_true');args=p.parse_args()
s=(root/'native/android/app/src/main/java/com/apexbooks/accounting/ImportTool.kt').read_text()
line=next(x for x in s.splitlines() if 'ActionDialog(title,vm,' in x);body=line.split('onSave={',1)[1].rsplit('}){',1)[0]
fixture='''import com.apexbooks.accounting.data.ImportReceiptRecovery
import kotlinx.coroutines.*
class JSONObject(private val text:String="body"){fun s(key:String)="";fun a(key:String)=JSONArray();fun optBoolean(key:String)=true;override fun toString()=text}
class JSONArray{fun length()=0}
class ApiFailure(val status:Int,message:String=""):Exception(message)
class Api{var calls=0;suspend fun request(path:String,method:String,body:JSONObject,key:String?):Any{calls++;return JSONObject()}}
class VM{val api=Api();var canWrite=true;var isOwner=true;var tool="statement_import";var toolData:Any?=null;var notice="";var refreshes=0;fun supports(value:String)=false;suspend fun refresh(){refreshes++};suspend fun finishConfirmedImport(message:String="Import confirmed."){tool="";toolData=null;try{refresh();notice=message}catch(e:Exception){throw ApiFailure((e as? ApiFailure)?.status?:0,message+" Do not repeat the import. "+e.message)}};suspend fun loadCompanies(id:String){} }
suspend fun ActionDialog(onSave:suspend()->Unit){onSave()}
fun main()=runBlocking{
 val vm=VM();val receipt:ImportReceiptRecovery?=null;var reading=false;var owned=true;val owner={owned};var tool="statement_import";val kind="party";val prepared=JSONObject();val preparedInput="original";fun identity()="original"
 val scope="posting";val report:JSONObject?=JSONObject();fun endpoint(stage:String)="/synthetic"
 suspend fun save(){ActionDialog(onSave={BODY})}
 vm.canWrite=false;check(runCatching{save()}.isFailure);check(vm.api.calls==0)
 vm.canWrite=true;save();check(vm.api.calls==1&&vm.refreshes==1)
 owned=false;check(runCatching{save()}.isFailure);check(vm.api.calls==1)
 owned=true
 for(next in listOf("restore","vyapar")){tool=next;vm.isOwner=false;val before=vm.api.calls;check(runCatching{save()}.isFailure);check(vm.api.calls==before);vm.isOwner=true;save();check(vm.api.calls==before+1)}
 println("PASS Android actual owner import callbacks plus bank roles: viewer blocked, editor resumes, stale owner blocked")
}'''.replace('BODY',body)
w=(root/'native/windows/MainPage.xaml.cs').read_text()
method=w.split('    private Action CaptureOwnerImportAccess()',1)[1].split('    internal string PathFor',1)[0]
settings=(root/'native/windows/Views/Settings.cs').read_text();complete=(root/'native/windows/Views/CompleteBackups.cs').read_text()
assert 'var verify=CaptureOwnerImportAccess();' in settings.split('private async Task RestoreCompany()',1)[1].split('private async Task VyaparMigration()',1)[0]
assert 'var verify=CaptureOwnerImportAccess();' in settings.split('private async Task VyaparMigration()',1)[1].split('private async Task MasterCsvImport()',1)[0]
assert 'panel,async()=>{verify();if(digest.Length==0' in settings
assert 'verify();if (!Ready()' in settings
assert 'panel,async()=>{verify();if(transfer.Preview is null)' in complete
cs='''class Flow{public bool CanWrite=true,IsOwner=true,Owned=true;Action CaptureFileSaveAccess()=>()=>{if(!Owned)throw new InvalidOperationException("Stale");};public Action CaptureOwnerImportAccess()METHOD}
class Program{static void Reject(Action action){try{action();}catch(InvalidOperationException){return;}throw new Exception("Expected block");}static void Main(){var f=new Flow();var guard=f.CaptureOwnerImportAccess();f.IsOwner=false;Reject(guard);f.CanWrite=false;Reject(guard);f.CanWrite=true;f.IsOwner=true;guard();f.Owned=false;Reject(guard);f.Owned=true;f.IsOwner=false;Reject(()=>f.CaptureOwnerImportAccess());Console.WriteLine("PASS Windows actual owner import access: owner/editor/viewer/recovery/stale and guarded dispatch wiring");}}'''.replace('METHOD',method)
with tempfile.TemporaryDirectory(prefix='apex-bank-role-') as folder:
 d=Path(folder);(d/'Proof.kt').write_text(fixture);run_proof(args,[root/'native/android/app/src/main/java/com/apexbooks/accounting/data/ImportReceiptRecovery.kt',d/'Proof.kt'],d)
 if args.android_only:sys.exit(0)
 (d/'Program.cs').write_text(cs);(d/'Proof.csproj').write_text('<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><ImplicitUsings>enable</ImplicitUsings></PropertyGroup></Project>')
 subprocess.run([args.dotnet,'run','--project',str(d/'Proof.csproj')],check=True,env={**os.environ,'DOTNET_CLI_TELEMETRY_OPTOUT':'1','DOTNET_GENERATE_ASPNET_CERTIFICATE':'false','DOTNET_CLI_HOME':str(d/'home')})
