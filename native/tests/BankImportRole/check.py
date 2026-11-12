"""Compile real native bank import save/verification callbacks with role transitions."""
from pathlib import Path
import argparse,sys,tempfile,subprocess,os
root=Path(__file__).resolve().parents[3];sys.path.insert(0,str(root/'native/tests'))
from kotlin_toolchain import add_arguments,run_proof
p=argparse.ArgumentParser();add_arguments(p);p.add_argument('--dotnet',default='dotnet');args=p.parse_args()
s=(root/'native/android/app/src/main/java/com/apexbooks/accounting/ImportTool.kt').read_text()
line=next(x for x in s.splitlines() if 'ActionDialog(title,vm,' in x);body=line.split('onSave={',1)[1].rsplit('}){',1)[0]
fixture='''import com.apexbooks.accounting.data.ImportReceiptRecovery
import kotlinx.coroutines.*
class JSONObject(private val text:String="body"){fun s(key:String)="";fun a(key:String)=JSONArray();fun optBoolean(key:String)=true;override fun toString()=text}
class JSONArray{fun length()=0}
class ApiFailure(val status:Int):Exception()
class Api{var calls=0;suspend fun request(path:String,method:String,body:JSONObject,key:String?):Any{calls++;return JSONObject()}}
class VM{val api=Api();var canWrite=true;var tool="statement_import";var toolData:Any?=null;var notice="";var refreshes=0;fun supports(value:String)=false;suspend fun refresh(){refreshes++};suspend fun loadCompanies(id:String){} }
suspend fun ActionDialog(onSave:suspend()->Unit){onSave()}
fun main()=runBlocking{
 val vm=VM();val receipt:ImportReceiptRecovery?=null;var reading=false;var owned=true;val owner={owned};val tool="statement_import";val kind="party";val prepared=JSONObject();val preparedInput="original";fun identity()="original"
 val scope="posting";val report:JSONObject?=null;fun endpoint(stage:String)="/synthetic"
 suspend fun save(){ActionDialog(onSave={BODY})}
 vm.canWrite=false;check(runCatching{save()}.isFailure);check(vm.api.calls==0)
 vm.canWrite=true;save();check(vm.api.calls==1&&vm.refreshes==1)
 owned=false;check(runCatching{save()}.isFailure);check(vm.api.calls==1)
 println("PASS Android actual bank import callback: viewer blocked, editor resumes, stale owner blocked")
}'''.replace('BODY',body)
w=(root/'native/windows/Views/StatementImport.cs').read_text();verify=w.split('void Verify(){',1)[1].split('\n',1)[0];verify=verify[:verify.rfind('}')]
commit=w.split('try{await Dialog("Import bank statement",panel,async()=>{',1)[1].split('},"Import reviewed rows"',1)[0]
assert 'Verify();if(!double.IsFinite' in w
cs='''using System.Text.Json.Nodes;using System.Net.Http;
class ApiMock{public int calls;public string CompanyPath(string c,string p)=>c+p;public Task Send(string p,HttpMethod m,JsonObject b){calls++;return Task.CompletedTask;}}
class Flow{public bool CanWrite=true,closed=false,validating=false;public Action access=()=>{};public string cid="synthetic",reviewed="{}";public ApiMock Api=new();void Verify(){VERIFY}JsonObject Build(){Verify();return new();}public async Task Save(){COMMIT}}
class Program{static async Task Main(){var f=new Flow();f.CanWrite=false;try{await f.Save();throw new Exception("Viewer allowed");}catch(InvalidOperationException){}if(f.Api.calls!=0)throw new Exception("Dispatched");f.CanWrite=true;await f.Save();if(f.Api.calls!=1)throw new Exception("Editor failed");f.closed=true;try{await f.Save();throw new Exception("Closed allowed");}catch(InvalidOperationException){}if(f.Api.calls!=1)throw new Exception("Stale dispatched");Console.WriteLine("PASS Windows actual bank Verify/save: viewer blocked, editor resumes, closed blocked");}}
'''.replace('VERIFY',verify).replace('COMMIT',commit)
with tempfile.TemporaryDirectory(prefix='apex-bank-role-') as folder:
 d=Path(folder);(d/'Proof.kt').write_text(fixture);run_proof(args,[root/'native/android/app/src/main/java/com/apexbooks/accounting/data/ImportReceiptRecovery.kt',d/'Proof.kt'],d)
 (d/'Program.cs').write_text(cs);(d/'Proof.csproj').write_text('<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><ImplicitUsings>enable</ImplicitUsings></PropertyGroup></Project>')
 subprocess.run([args.dotnet,'run','--project',str(d/'Proof.csproj')],check=True,env={**os.environ,'DOTNET_CLI_TELEMETRY_OPTOUT':'1','DOTNET_GENERATE_ASPNET_CERTIFICATE':'false','DOTNET_CLI_HOME':str(d/'home')})
