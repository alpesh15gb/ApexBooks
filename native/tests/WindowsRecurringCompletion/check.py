from pathlib import Path
import argparse,os,subprocess,tempfile
root=Path(__file__).resolve().parents[3];p=argparse.ArgumentParser();p.add_argument('--dotnet',default='dotnet');args=p.parse_args()
s=(root/'native/windows/Views/RecurringDrafts.cs').read_text();method=s[s.index('    private async Task ReviewGeneratedRecurringDraft('):s.rindex('\n}')]
assert 'await ReviewGeneratedRecurringDraft(generated)' in s
fixture=r'''
using System.Text.Json.Nodes;
class ApiFailure(int status,string message):Exception(message){public int Status=>status;}
static class J{public static bool Flag(this JsonNode? n,string key)=>n?[key]?.GetValue<bool>()??false;public static string Text(this JsonNode? n,string key)=>n?[key]?.ToString()??"";public static JsonObject Object(this JsonNode n)=>n.AsObject();}
static class FeatureCatalog{public static HashSet<string> Drafts=new(){"estimate"};}
class Panel{public List<object> Children=new();}
class ApiMock{public bool SignedIn=true;public int SessionGeneration,Gets;public Exception? Failure;public bool Cancelled;public string Converted="";public Func<Task>? Delay;public async Task<JsonNode> Record(string cid,string id){Gets++;if(Delay is not null)await Delay();if(Failure is not null)throw Failure;return new JsonObject{["id"]=id,["kind"]="estimate",["number"]="EST-SAVED",["cancelled"]=Cancelled,["converted_to"]=Converted};}}
class Screen{
 public string CompanyId="a",CurrentPage="dashboard";public int workspaceGeneration,generation,saveAccessEpoch;public bool recordsReady=true;public bool CanWrite=true;public ApiMock Api=new();public int Refreshes,Editors,Details,Dialogs;public string Message="";public Func<Task> RefreshAction=()=>Task.CompletedTask;public Func<Func<Task>,Task<bool>>? Recovery;public Func<Task> OpenAction=()=>Task.CompletedTask;
 Panel Stack(int size)=>new();object Text(string value,int size,bool bold=false){Message+=value;return value;}
 async Task Refresh(){Refreshes++;await RefreshAction();generation++;}async Task EditDocument(string kind,JsonObject previous){Editors++;await OpenAction();}async Task TransactionDetails(JsonObject row){Details++;await OpenAction();}
 async Task<bool> Dialog(string title,Panel panel,Func<Task> action,string label,Func<bool> canSave){Dialogs++;if(!canSave())return false;return Recovery is null?false:await Recovery(action);}
 public Task Start()=>ReviewGeneratedRecurringDraft(new JsonObject{["id"]="saved",["kind"]="estimate",["number"]="EST-SAVED"});
 METHOD
}
class Program{
 static void Check(bool value){if(!value)throw new Exception("Assertion failed");}
 static async Task Main(){
 var ok=new Screen();await ok.Start();Check(ok.Refreshes==1&&ok.Api.Gets==1&&ok.Editors==1&&ok.Dialogs==0);
 foreach(var code in new[]{0,403,404,422,503}){
  var f=new Screen();f.RefreshAction=()=>throw new ApiFailure(code,"refresh failed");f.Recovery=async retry=>{Check(f.Message.Contains("EST-SAVED is saved")&&f.Message.Contains("Do not generate"));f.RefreshAction=()=>Task.CompletedTask;await retry();return true;};await f.Start();Check(f.Refreshes==2&&f.Api.Gets==1&&f.Editors==1&&f.Dialogs==1);
 }
 foreach(var cancelled in new[]{false,true}){var changed=new Screen();changed.Api.Cancelled=cancelled;changed.Api.Converted=cancelled?"":"converted-invoice";await changed.Start();Check(changed.Details==1&&changed.Editors==0);}
 var cancel=new Screen{RefreshAction=()=>throw new IOException("offline")};await cancel.Start();Check(cancel.Dialogs==1&&cancel.Editors==0&&cancel.Api.Gets==0);
 var again=new Screen{RefreshAction=()=>throw new IOException("offline")};again.Recovery=async retry=>{Check(again.Message.Contains("is saved"));if(again.Dialogs==2){again.RefreshAction=()=>Task.CompletedTask;again.CanWrite=false;}await retry();return true;};await again.Start();Check(again.Details==1&&again.Editors==0&&again.Refreshes==3);

 var read=new Screen();read.Api.Failure=new ApiFailure(503,"record failed");read.Recovery=async retry=>{read.Api.Failure=null;await retry();return true;};await read.Start();Check(read.Api.Gets==2&&read.Editors==1);
 foreach(var mode in new[]{"company","session","awayback","logout","navigate","page-awayback"})foreach(var failed in new[]{false,true}){
  var screen=new Screen();var gate=new TaskCompletionSource();screen.RefreshAction=async()=>{await gate.Task;if(failed)throw new IOException("old failure");};var task=screen.Start();
  if(mode=="company")screen.CompanyId="b";if(mode=="session")screen.Api.SessionGeneration++;if(mode=="awayback")screen.workspaceGeneration++;if(mode=="logout")screen.Api.SignedIn=false;if(mode=="navigate")screen.CurrentPage="reports";if(mode=="page-awayback")screen.generation+=2;
  gate.SetResult();await task;Check(screen.Dialogs==0&&screen.Editors==0&&screen.Api.Gets==0);
 }
 var delayed=new Screen();var wait=new TaskCompletionSource();delayed.Api.Delay=()=>wait.Task;var pending=delayed.Start();delayed.workspaceGeneration++;wait.SetResult();await pending;Check(delayed.Editors==0&&delayed.Details==0);
 var denied=new Screen();var readGate=new TaskCompletionSource();denied.Api.Delay=()=>readGate.Task;var inFlight=denied.Start();denied.saveAccessEpoch++;denied.recordsReady=false;readGate.SetResult();await inFlight;Check(denied.Editors==0&&denied.Details==0);
 foreach(var writer in new[]{true,false}){
  var opening=new Screen{CanWrite=writer,OpenAction=()=>throw new IOException("final opening failed")};opening.Recovery=async retry=>{Check(opening.Message.Contains("is saved")&&opening.Message.Contains("Do not generate"));opening.OpenAction=()=>Task.CompletedTask;await retry();return true;};await opening.Start();Check(opening.Dialogs==1&&opening.Refreshes==2&&opening.Api.Gets==2&&opening.Editors+opening.Details==2);
 }
 foreach(var mode in new[]{"company","session","page","access"}){
  var opening=new Screen{CanWrite=false};var openingGate=new TaskCompletionSource();opening.OpenAction=async()=>{await openingGate.Task;throw new IOException("late final open failed");};var pendingOpen=opening.Start();
  if(mode=="company")opening.CompanyId="b";if(mode=="session")opening.Api.SessionGeneration++;if(mode=="page")opening.CurrentPage="reports";
  if(mode=="access"){opening.saveAccessEpoch++;opening.recordsReady=false;opening.Recovery=retry=>Task.FromResult(false);}
  openingGate.SetResult();await pendingOpen;Check(opening.Dialogs==(mode=="access"?1:0)&&opening.Refreshes==1);
 }
 Console.WriteLine("PASS final editor/details failure recovery and delayed stale final-open errors; recovery closes before opening another dialog");
 Console.WriteLine("PASS actual recurring completion: current open, five refresh failures/retry, cancel, repeated failure, viewer read-only, GET failure, twelve stale refreshes and stale/denied GET");
 }
}
'''.replace('METHOD',method)
with tempfile.TemporaryDirectory(prefix='apex-recurring-completion-') as folder:
 d=Path(folder);(d/'Program.cs').write_text(fixture);(d/'Proof.csproj').write_text('<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><ImplicitUsings>enable</ImplicitUsings><Nullable>enable</Nullable></PropertyGroup></Project>')
 subprocess.run([args.dotnet,'run','--project',str(d/'Proof.csproj')],check=True,env={**os.environ,'DOTNET_CLI_TELEMETRY_OPTOUT':'1','DOTNET_GENERATE_ASPNET_CERTIFICATE':'false','DOTNET_CLI_HOME':str(d/'home')})
