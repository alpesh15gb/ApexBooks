from pathlib import Path
import argparse,os,subprocess,tempfile
root=Path(__file__).resolve().parents[3]
p=argparse.ArgumentParser();p.add_argument('--dotnet',default='dotnet');args=p.parse_args()
s=(root/'native/windows/Views/RecurringDrafts.cs').read_text(encoding="utf-8")
names=['Create recurring draft schedule','Manage recurring schedule','Generate next due draft']
callbacks=[s.split('var saved=await Dialog("'+name+'",panel,async()=>{',1)[1].split('\n        },',1)[0] for name in names]
main=(root/'native/windows/MainPage.xaml.cs').read_text(encoding="utf-8")
helper=main[main.index('    private Action CaptureRecurringWriteAccess()'):main.index('    internal string PathFor')]
assert s.count('var writeAccess=CaptureRecurringWriteAccess();')==3
assert s.count('canSave:()=>CanWrite&&ScopedFileExport.Current(writeAccess)')==3
fixture=r'''
using System.Text.Json.Nodes;using System.Net.Http;using ApexBooks_Windows.Services;
class ApiFailure(int status,string text):Exception(text){public int Status=>status;}
static class J{public static string Text(this JsonNode? n,string key)=>n?[key]?.ToString()??"";public static JsonNode? Copy(this JsonNode? n)=>n?.DeepClone();public static JsonObject Object(this JsonNode? n)=>n?.AsObject()??new();}
class Field{public string Text="Original",Value="2026-01-01";public bool? IsChecked=true;}
static class FeatureCatalog{public static HashSet<string> Drafts=new(){"estimate"};}
static class WorkflowMasterValues{public static int RecurringInterval(string v)=>int.Parse(v);public static void RecurringWriteFailed(RetrySubmission s,Exception e){if(e is ApiFailure{Status:409})s.Succeeded();else s.Failed(e);}}
class ApiMock{public int Calls;public Exception? Failure;public List<string> Bodies=new();public List<string> Keys=new();public string CompanyPath(string cid,string suffix)=>cid+suffix;public Task<JsonNode> Send(string path,HttpMethod method,JsonNode body,string key){Calls++;Bodies.Add(body.ToJsonString());Keys.Add(key);if(Failure is not null)throw Failure;return Task.FromResult<JsonNode>(new JsonObject{["record"]=new JsonObject{["id"]="draft",["kind"]="estimate"}});}}
class Screen{
 public bool CanWrite=true;public int epoch;public ApiMock Api=new();public RetrySubmission submission=new();public Field name=new();Field start=new(),end=new(){Value=""},frequency=new(){Value="monthly"},interval=new(){Text="1"},active=new(),refresh=new(){IsChecked=false};
 JsonObject source=new(){["id"]="source"},row=new(){["version"]=1},template=new(){["id"]="template"};JsonObject? generated;string cid="company",id="template",date="2026-01-01",key=Guid.NewGuid().ToString();object panel=new();Action writeAccess;
 public Screen(){writeAccess=CaptureRecurringWriteAccess();}
 Action CaptureFileSaveAccess(){var stamp=epoch;return ()=>{if(stamp!=epoch)throw new InvalidOperationException("stale access");};}
 static string Value(Field f)=>f.Value;static string Value(JsonObject o)=>"source";static void SetFormEnabled(object p,bool v){}
 HELPER
 public async Task Create(){CREATE}
 public async Task Edit(){EDIT}
 public async Task Generate(){GENERATE}
}
class Program{
 static void Check(bool value,string message){if(!value)throw new Exception(message);}
 static async Task Reject(Func<Task> action){try{await action();}catch{return;}throw new Exception("Expected local rejection");}
 static async Task Main(){
 foreach(var command in new[]{"create","edit","generate"}){
  var screen=new Screen();Func<Task> save=command switch{"create"=>screen.Create,"edit"=>screen.Edit,_=>screen.Generate};
  screen.CanWrite=false;await Reject(save);Check(screen.Api.Calls==0,command+" dispatched as viewer");
  screen.CanWrite=true;screen.Api.Failure=new IOException("response lost");await Reject(save);Check(screen.submission.Unresolved&&screen.Api.Calls==1,"unknown request not retained");
  var original=screen.Api.Bodies[0];screen.name.Text="Changed after unknown result";screen.CanWrite=false;await Reject(save);Check(screen.Api.Calls==1&&screen.submission.Unresolved,"viewer modified unresolved command");
  screen.CanWrite=true;screen.Api.Failure=null;await save();Check(screen.Api.Calls==2&&screen.Api.Bodies[1]==original&&screen.Api.Keys.Distinct().Count()==1&&!screen.submission.Unresolved,"original retry not recovered");
  screen.epoch++;await Reject(save);Check(screen.Api.Calls==2,"stale access dispatched");
 }
 Console.WriteLine("PASS 3 actual recurring callbacks: viewer forced-submit rejection, unknown draft retention, editor original-key/body retry, stale access suppression");
 }
}
'''.replace('HELPER',helper).replace('CREATE',callbacks[0]).replace('EDIT',callbacks[1]).replace('GENERATE',callbacks[2])
with tempfile.TemporaryDirectory(prefix='apex-recurring-access-') as folder:
 d=Path(folder);(d/'Program.cs').write_text(fixture, encoding="utf-8")
 (d/'Proof.csproj').write_text('<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><ImplicitUsings>enable</ImplicitUsings><Nullable>enable</Nullable></PropertyGroup><ItemGroup><Compile Include="'+str(root/'native/windows/Services/RetrySubmission.cs')+'" /></ItemGroup></Project>', encoding="utf-8")
 subprocess.run([args.dotnet,'run','--project',str(d/'Proof.csproj')],check=True,env={**os.environ,'DOTNET_CLI_TELEMETRY_OPTOUT':'1','DOTNET_GENERATE_ASPNET_CERTIFICATE':'false','DOTNET_CLI_HOME':str(d/'home')})
