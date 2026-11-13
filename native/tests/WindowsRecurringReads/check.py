from pathlib import Path
import argparse,os,subprocess,tempfile
root=Path(__file__).resolve().parents[3];p=argparse.ArgumentParser();p.add_argument('--dotnet',default='dotnet');args=p.parse_args()
s=(root/'native/windows/Views/RecurringDrafts.cs').read_text(encoding="utf-8")
def function(marker):
 start=s.index(marker);brace=s.index('{',start);depth=1;end=brace+1
 while depth:
  if s[end]=='{':depth+=1
  if s[end]=='}':depth-=1
  end+=1
 return s[start:end]
load=function('async Task Load()')
read=function('private async Task<JsonObject?> ReadRecurringSchedule(').replace('private async','public async',1)
snapshot=function('void InvalidateSnapshot()')
assert 'ReadAccessInvalidated+=Invalidate;' in s and 'closed=true;ReadAccessInvalidated-=Invalidate;' in s
assert 'ReadAccessInvalidated+=InvalidateSnapshot;' in s and 'ReadAccessInvalidated-=InvalidateSnapshot;' in s
fixture=r'''
using System.Text.Json.Nodes;using ApexBooks_Windows.Services;
class ApiFailure(int status,string message):Exception(message){public int Status=>status;}
static class J{public static string Text(this JsonNode? n,string key)=>n?[key]?.ToString()??"";public static JsonObject Object(this JsonNode n)=>n.AsObject();public static JsonArray Array(this JsonNode? n)=>n?.AsArray()??new();}
class Choice{public string Value="all";}class DateField{public string Value="2026-01-01";public Picker Picker=new();}class Picker{public DateTimeOffset Date;}
class Label{public string Text="old calendar";}class Panel{public List<object> Children=new(){"old private data"};}
class ApiMock{public int Calls;public Func<string,Task<JsonNode>> Read=path=>Task.FromResult<JsonNode>(new JsonObject());public string CompanyPath(string id,string path)=>id+path;public Task<JsonNode> Send(string path){Calls++;return Read(path);}}
class Screen{
 public string cid="a",CompanyId="a";public int stamp=0,generation,sequence,epoch;public bool recordsReady=true;public bool closed=false,accessLost=false,CanWrite=true;public ApiMock Api=new();public List<JsonObject> loaded=new(){new JsonObject{["name"]="old"}};public string businessDate="old date",action="";public JsonObject? selected;public Panel panel=new(),rows=new();public Label calendarLabel=new();public Choice view=new();public DateField asOf=new();public int Draws,Closes;public Action access;
 public Screen(){var e=epoch;access=()=>{if(epoch!=e)throw new InvalidOperationException("stale");};}
 Action CaptureFileSaveAccess()=>access;
 string Value(Choice value)=>value.Value;Label Text(string text)=>new(){Text=text};void CloseDialog(){Closes++;}
 bool Context()=>cid==CompanyId&&stamp==generation&&ScopedFileExport.Current(access);bool Owned()=>!accessLost&&Context();bool Current()=>!closed&&Owned();void Draw(){Draws++;}
 INVALIDATE
 CHOOSE
 public LOAD
 READ
 public SNAPSHOT
}
class Program{
 static void Check(bool value,string message="Assertion failed"){if(!value)throw new Exception(message);}
 static JsonNode Result()=>new JsonObject{["rows"]=new JsonArray(new JsonObject{["name"]="loaded"}),["templates"]=new JsonArray(new JsonObject{["name"]="loaded"}),["business_date"]="2026-01-01"};
 static async Task Main(){
 var s=new Screen();var gate=new TaskCompletionSource<JsonNode>();s.Api.Read=path=>gate.Task;var pending=s.Load();s.epoch++;gate.SetResult(Result());await pending;Check(s.Draws==0,"Late Windows recurring list published after access denial");
 foreach(var mode in new[]{"company","page","access","closed"})foreach(var fails in new[]{false,true}){var f=new Screen();var done=new TaskCompletionSource<JsonNode>();f.Api.Read=path=>done.Task;var work=f.Load();if(mode=="company")f.CompanyId="b";if(mode=="page")f.generation++;if(mode=="access")f.epoch++;if(mode=="closed")f.closed=true;if(fails)done.SetException(new ApiFailure(503,"old error"));else done.SetResult(Result());await work;Check(f.Draws==0);}
 var current=new Screen();current.Api.Read=path=>Task.FromResult(Result());await current.Load();Check(current.Draws==1&&current.loaded.Count==1&&current.businessDate=="2026-01-01");
 current.Invalidate();Check(current.loaded.Count==0&&current.businessDate==""&&current.panel.Children.Count==1);current.Choose("view",new());Check(current.Closes==0);var count=current.Api.Calls;await current.Load();Check(current.Api.Calls==count);
 var mixed=new Screen();mixed.Api.Read=path=>Task.FromException<JsonNode>(new ApiFailure(path.Contains("/due")?503:404,"mixed failure"));try{await mixed.Load();throw new Exception("Expected denial");}catch(InvalidOperationException){}Check(mixed.accessLost&&mixed.loaded.Count==0);
 var retry=new Screen();retry.Api.Read=path=>Task.FromException<JsonNode>(new ApiFailure(503,"retryable"));try{await retry.Load();throw new Exception("Expected current failure");}catch(ApiFailure){}Check(retry.loaded.Count==0&&!retry.accessLost);retry.Api.Read=path=>Task.FromResult(Result());await retry.Load();Check(retry.Draws==1);
 var viewer=new Screen{CanWrite=false};viewer.Choose("edit",new());Check(viewer.Closes==0);viewer.Choose("view",new());Check(viewer.Closes==1);
 foreach(var mode in new[]{"company","page","access"})foreach(var fails in new[]{false,true}){var detail=new Screen();var done=new TaskCompletionSource<JsonNode>();detail.Api.Read=path=>done.Task;var work=detail.ReadRecurringSchedule("template");if(mode=="company")detail.CompanyId="b";if(mode=="page")detail.generation++;if(mode=="access")detail.epoch++;if(fails)done.SetException(new ApiFailure(503,"old"));else done.SetResult(Result());Check(await work is null);}
 var ready=new Screen();ready.Api.Read=path=>Task.FromResult(Result());Check(await ready.ReadRecurringSchedule("template") is not null);ready.InvalidateSnapshot();Check(ready.panel.Children.Count==1);ready.recordsReady=false;var before=ready.Api.Calls;Check(await ready.ReadRecurringSchedule("template") is null&&ready.Api.Calls==before);
 var err=new Screen();err.Api.Read=path=>Task.FromException<JsonNode>(new ApiFailure(503,"current"));try{await err.ReadRecurringSchedule("template");throw new Exception("Expected current error");}catch(ApiFailure){}
 Console.WriteLine("PASS actual detail reader: six stale result/error cases, current success/error, readiness gate and snapshot invalidation");
 Console.WriteLine("PASS actual Windows recurring load/selection: late denial, eight stale results/errors, cleared cache, mixed denial, current retry and role guards");
 }
}
'''
invalidate=function('void Invalidate()')
choose=function('void Choose(')
fixture=fixture.replace('LOAD',load).replace('INVALIDATE','public '+invalidate).replace('CHOOSE','public '+choose).replace('READ',read).replace('SNAPSHOT',snapshot)
with tempfile.TemporaryDirectory(prefix='apex-windows-recurring-reads-') as folder:
 d=Path(folder);(d/'Program.cs').write_text(fixture, encoding="utf-8");includes=''.join('<Compile Include="'+str(root/'native/windows/Services'/file)+'" />' for file in ['ScopedFileExport.cs','ScopedCoreRefresh.cs']);(d/'Proof.csproj').write_text('<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><ImplicitUsings>enable</ImplicitUsings><Nullable>enable</Nullable></PropertyGroup><ItemGroup>'+includes+'</ItemGroup></Project>', encoding="utf-8")
 subprocess.run([args.dotnet,'run','--project',str(d/'Proof.csproj')],check=True,env={**os.environ,'DOTNET_CLI_TELEMETRY_OPTOUT':'1','DOTNET_GENERATE_ASPNET_CERTIFICATE':'false','DOTNET_CLI_HOME':str(d/'home')})
