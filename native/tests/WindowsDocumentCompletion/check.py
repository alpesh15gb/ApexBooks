from pathlib import Path
import argparse,os,subprocess,tempfile
root=Path(__file__).resolve().parents[3];p=argparse.ArgumentParser();p.add_argument('--dotnet',default='dotnet');args=p.parse_args()
s=(root/'native/windows/Views/Documents.cs').read_text()
method=s[s.index('    private async Task<bool> FinishConfirmedDocument('):s.index('    private Action CaptureDocumentWriteAccess(')]
assert 'editorSession!=Api.SessionGeneration' in s
assert 'if(await FinishConfirmedDocument(confirmed,showDetails)&&keepNew&&CanWrite)await EditDocument(kind)' in s
fixture=r'''
using System.Text.Json.Nodes;
static class J{public static string Text(this JsonNode n,string k)=>n[k]?.ToString()??"";}
class Panel{public List<object> Children=new();}
class ApiMock{public bool SignedIn=true;public int SessionGeneration;}
class Screen{
 public string CompanyId="a",CurrentPage="sales";public int workspaceGeneration,generation;public bool recordsReady=true;public ApiMock Api=new();public int Refreshes,Details,Dialogs;public string Message="";public Func<Task> Read=()=>Task.CompletedTask,Open=()=>Task.CompletedTask;public Func<Task<bool>> Recovery=()=>Task.FromResult(false);
 Panel Stack(int n)=>new();object Text(string t,int n,bool bold=false){Message+=t;return t;}
 async Task Refresh(){Refreshes++;await Read();generation++;}
 async Task TransactionDetails(JsonObject row){if(row.Text("id")!="saved")throw new Exception("Wrong document");Details++;await Open();}
 Task<bool> Dialog(string title,Panel p,Func<Task> action,string label,Func<bool> canSave){Dialogs++;return canSave()?Recovery():Task.FromResult(false);}
 public Task<bool> Start(bool details=true)=>FinishConfirmedDocument(new JsonObject{["id"]="saved",["number"]="INV-100"},details);
 METHOD
}
class Program{
 static void Check(bool b){if(!b)throw new Exception("Assertion failed");}
 static async Task Main(){
 foreach(var details in new[]{true,false}){var ok=new Screen();Check(await ok.Start(details));Check(ok.Refreshes==1&&ok.Details==(details?1:0)&&ok.Dialogs==0);}
 foreach(var stage in new[]{"refresh","open"}){
 var s=new Screen();if(stage=="refresh")s.Read=()=>throw new IOException("offline");else s.Open=()=>throw new IOException("second GET failed");
 s.Recovery=()=>{Check(s.Message.Contains("INV-100 is saved")&&s.Message.Contains("Do not submit"));s.Read=()=>Task.CompletedTask;s.Open=()=>Task.CompletedTask;return Task.FromResult(true);};Check(await s.Start());Check(s.Refreshes==2&&s.Dialogs==1&&s.Details==(stage=="open"?2:1));
 }
 var cancel=new Screen{Read=()=>throw new IOException("offline")};Check(!await cancel.Start());Check(cancel.Refreshes==1&&cancel.Details==0&&cancel.Dialogs==1);
 var unavailable=new Screen{recordsReady=false};unavailable.Recovery=()=>{unavailable.recordsReady=true;return Task.FromResult(true);};Check(await unavailable.Start());Check(unavailable.Refreshes==2&&unavailable.Details==1);
 foreach(var stage in new[]{"refresh","open"})foreach(var mode in new[]{"company","session","workspace","logout","page","awayback"})foreach(var failure in new[]{false,true}){
 var s=new Screen();var gate=new TaskCompletionSource();Func<Task> delayed=async()=>{await gate.Task;if(failure)throw new IOException("obsolete");};if(stage=="refresh")s.Read=delayed;else s.Open=delayed;
 var t=s.Start();if(mode=="company")s.CompanyId="b";if(mode=="session")s.Api.SessionGeneration++;if(mode=="workspace")s.workspaceGeneration++;if(mode=="logout")s.Api.SignedIn=false;if(mode=="page")s.CurrentPage="reports";if(mode=="awayback")s.generation+=2;
 gate.SetResult();Check(!await t);Check(s.Dialogs==0&&s.Refreshes==1&&s.Details==(stage=="open"?1:0));
 }
 Console.WriteLine("PASS actual document completion: refresh/final-open recovery, cancel, access recovery, 24 stale outcomes; helper has no mutation API");
 }
}
'''.replace('METHOD',method)
with tempfile.TemporaryDirectory(prefix='apex-document-completion-') as folder:
 d=Path(folder);(d/'Program.cs').write_text(fixture);(d/'Proof.csproj').write_text('<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><ImplicitUsings>enable</ImplicitUsings><Nullable>enable</Nullable></PropertyGroup></Project>')
 subprocess.run([args.dotnet,'run','--project',str(d/'Proof.csproj')],check=True,env={**os.environ,'DOTNET_CLI_TELEMETRY_OPTOUT':'1','DOTNET_GENERATE_ASPNET_CERTIFICATE':'false','DOTNET_CLI_HOME':str(d/'home')})
