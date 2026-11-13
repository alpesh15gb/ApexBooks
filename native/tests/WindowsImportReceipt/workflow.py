from pathlib import Path
import argparse,tempfile,subprocess,os
root=Path(__file__).resolve().parents[3];p=argparse.ArgumentParser();p.add_argument('--dotnet',default='dotnet');args=p.parse_args()
s=(root/'native/windows/Views/Settings.cs').read_text(encoding="utf-8");method=s[s.index('    private async Task MasterCsvImport()'):s.index('    private async Task DataExport()')]
main=(root/'native/windows/MainPage.xaml.cs').read_text(encoding="utf-8");completion=main[main.index('    private async Task FinishConfirmedImport('):main.index('    internal async Task Run(')]
fixture='''
using System.Text;using System.Text.Json.Nodes;using System.Net.Http;using ApexBooks_Windows.Services;
class ApiFailure(int status,string message):Exception(message){public int Status=>status;}
static class J{public static string Text(this JsonNode? n,string key)=>n?[key]?.ToString()??"";public static JsonNode? Copy(this JsonNode? n)=>n?.DeepClone();}
class Panel{public double MinWidth;public List<object> Children=new();}
class Label{public string Text="";}
class Choice{public bool IsEnabled=true;public string Value="party";}
class Button(string label,Func<Task> action,Action<Exception> error){public string Label=>label;public async Task Invoke(){try{await action();}catch(Exception e){error(e);}}}
class FakeFile{public string Name="synthetic.csv";}
static class ApexFiles{public static int Picks,Reads;public static Action? AfterPick;public static Task<FakeFile?> Pick(string ext){Picks++;AfterPick?.Invoke();return Task.FromResult<FakeFile?>(new());}public static Task<byte[]> Read(FakeFile file,int limit){Reads++;return Task.FromResult(Encoding.UTF8.GetBytes("name,phone\\nPrivate party,00123"));}}
static class CompleteBackupTransfer{public static string PrivateDirectory="";}
class Capability{public bool Enabled=true;public bool Supports(string f)=>Enabled;}
class ApiMock{public bool SignedIn=true;public int SessionGeneration;public string Origin="https://synthetic.invalid",Email="actor@example.invalid";public Capability Capabilities=new();public int Commits,Gets;public bool Lose;public JsonNode? Receipt;
 public string CompanyPath(string id,string suffix)=>id+suffix;
 public Task<JsonNode> Send(string path,HttpMethod? method=null,JsonNode? body=null,string? key=null){
 if(method==HttpMethod.Post){if(body?["dry_run"]?.GetValue<bool>()==true)return Task.FromResult<JsonNode>(new JsonObject());Commits++;Receipt=new JsonObject{["operation_key"]=key};if(Lose)throw new IOException("lost response");return Task.FromResult(Receipt.DeepClone());}
 Gets++;if(Receipt is null)throw new ApiFailure(404,"No committed receipt; this does not prove failure");return Task.FromResult(Receipt.DeepClone());}
}
class Screen{
 public string CompanyId="company";public bool CanWrite=true,Owned=true;public ApiMock Api=new();public int Refreshes,Errors,workspaceGeneration;public string Notice="";public Exception? RefreshError;public Func<Task>? AwaitRefresh;public Task Complete()=>FinishConfirmedImport("Import confirmed.");public Task Start()=>MasterCsvImport();
 Action CaptureFileSaveAccess()=>()=>{if(!Owned)throw new InvalidOperationException("stale");};
 void Error(Exception e){Errors++;}void Success(string message){Notice=message;}async Task Refresh(){Refreshes++;if(AwaitRefresh is not null)await AwaitRefresh();if(RefreshError is not null)throw RefreshError;}
 Panel Stack()=>new();Label Text(string value,int size=0)=>new(){Text=value};Choice Select(string label,IEnumerable<(string,string)> values,string selected)=>new(){Value=selected};string Value(Choice value)=>value.Value;
 Button AsyncButton(string label,Func<Task> action,Action<Exception> error,bool primary=false)=>new(label,action,error);
 void RenderReport(Panel panel,JsonNode result){}void Table(Panel panel,JsonArray rows,string title){}
 async Task<bool> Dialog(string title,Panel panel,Func<Task> save,string action,Func<bool>? enabled=null,Func<bool>? unresolved=null){
 if(title.StartsWith("Recover")){await panel.Children.OfType<Button>().Single().Invoke();return false;}
 await panel.Children.OfType<Button>().Single().Invoke();if(enabled?.Invoke()==false)return false;await save();return true;}
 METHOD
 COMPLETION
}
class Program{
 static void Check(bool value){if(!value)throw new Exception("Assertion failed");}
 static async Task Main(){
 var folder=Path.Combine(Path.GetTempPath(),"apex-import-workflow-"+Guid.NewGuid());Directory.CreateDirectory(folder);CompleteBackupTransfer.PrivateDirectory=folder;
 try{
 var first=new Screen();first.Api.Lose=true;try{await first.Start();throw new Exception("Expected lost response");}catch(IOException){}Check(first.Api.Commits==1);
 var path=ImportReceiptRecovery.Location(folder,first.Api.Origin,first.Api.Email,first.CompanyId);Check(File.Exists(path));Check(!File.ReadAllText(path).Contains("Private party"));
 ApexFiles.Picks=0;var restarted=new Screen{Api=first.Api};await restarted.Start();Check(restarted.Api.Commits==1&&restarted.Api.Gets==1&&ApexFiles.Picks==0&&restarted.Refreshes==1&&!File.Exists(path));
 var missing=new ImportReceiptRecovery(path);missing.Begin("original body","party",true);missing.End();var next=new Screen();ApexFiles.Picks=0;await next.Start();Check(next.Api.Gets==1&&next.Api.Commits==0&&ApexFiles.Picks==0&&File.Exists(path));
 next.Api.Capabilities.Enabled=false;await next.Start();Check(next.Api.Gets==1&&next.Api.Commits==0&&File.Exists(path));missing.Confirmed(missing.Saved!.Key);
 var stale=new Screen();ApexFiles.Reads=0;ApexFiles.AfterPick=()=>stale.Owned=false;try{await stale.Start();throw new Exception("Expected stale context");}catch(InvalidOperationException){}Check(ApexFiles.Reads==0&&stale.Api.Commits==0);
 ApexFiles.AfterPick=null;
 foreach(var code in new[]{0,401,403,404,422,503}){
  var screen=new Screen{RefreshError=code==0?new IOException("offline"):new ApiFailure(code,"refresh failed")};
  try{await screen.Start();throw new Exception("Expected refresh failure");}catch(ApiFailure error){Check(error.Status==code&&error.Message.Contains("Master import confirmed.")&&error.Message.Contains("Do not repeat"));}
  Check(screen.Api.Commits==1&&screen.Refreshes==1&&!File.Exists(path));
  var lost=new Screen();lost.Api.Lose=true;try{await lost.Start();}catch(IOException){}
  var recover=new Screen{Api=lost.Api,RefreshError=new ApiFailure(code,"refresh failed")};
  try{await recover.Start();throw new Exception("Expected recovery refresh failure");}catch(ApiFailure error){Check(error.Status==code&&error.Message.Contains("Original import confirmed"));}
  Check(recover.Api.Commits==1&&recover.Api.Gets==1&&!File.Exists(path));
 }
 foreach(var staleCase in new[]{"company","awayback","session","logout"})foreach(var failure in new[]{false,true}){
  var gate=new TaskCompletionSource();var screen=new Screen{AwaitRefresh=()=>gate.Task,RefreshError=failure?new IOException("late failure"):null};
  var pending=screen.Complete();Check(!pending.IsCompleted);
  if(staleCase=="company")screen.CompanyId="other";
  if(staleCase=="awayback")screen.workspaceGeneration++;
  if(staleCase=="session")screen.Api.SessionGeneration++;
  if(staleCase=="logout")screen.Api.SignedIn=false;
  gate.SetResult();await pending;Check(screen.Notice==""&&screen.Refreshes==1);
 }
 var cancelled=new Screen{RefreshError=new OperationCanceledException()};try{await cancelled.Complete();throw new Exception("Expected cancellation");}catch(OperationCanceledException){}
 var ok=new Screen();await ok.Start();Check(ok.Notice=="Master import confirmed."&&ok.Api.Commits==1&&ok.Refreshes==1);
 Console.WriteLine("PASS confirmed POST/receipt GET refresh failure codes, 8 delayed stale contexts, cancellation and current success");
 Console.WriteLine("PASS actual Windows import workflow: lost commit/restart GET-only recovery, missing receipt, capability loss and stale picker");
 }finally{Directory.Delete(folder,true);}
 }
}
'''.replace('METHOD',method).replace('COMPLETION',completion)
with tempfile.TemporaryDirectory(prefix='apex-windows-import-workflow-') as directory:
 d=Path(directory);(d/'Program.cs').write_text(fixture, encoding="utf-8")
 sources=['ImportReceiptRecovery.cs','Csv.cs','ScopedFileExport.cs']
 includes=''.join('<Compile Include="'+str(root/'native/windows/Services'/name)+'" />' for name in sources)
 (d/'Proof.csproj').write_text('<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><ImplicitUsings>enable</ImplicitUsings><Nullable>enable</Nullable></PropertyGroup><ItemGroup>'+includes+'</ItemGroup></Project>', encoding="utf-8")
 env={**os.environ,'DOTNET_CLI_TELEMETRY_OPTOUT':'1','DOTNET_GENERATE_ASPNET_CERTIFICATE':'false','DOTNET_CLI_HOME':str(d/'home')}
 subprocess.run([args.dotnet,'run','--project',str(d/'Proof.csproj')],check=True,env=env)
