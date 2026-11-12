from pathlib import Path
import argparse,tempfile,subprocess,os
root=Path(__file__).resolve().parents[3];p=argparse.ArgumentParser();p.add_argument('--dotnet',default='dotnet');args=p.parse_args()
s=(root/'native/windows/Views/Settings.cs').read_text();method=s[s.index('    private async Task MasterCsvImport()'):s.index('    private async Task DataExport()')]
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
class ApiMock{public string Origin="https://synthetic.invalid",Email="actor@example.invalid";public Capability Capabilities=new();public int Commits,Gets;public bool Lose;public JsonNode? Receipt;
 public string CompanyPath(string id,string suffix)=>id+suffix;
 public Task<JsonNode> Send(string path,HttpMethod? method=null,JsonNode? body=null,string? key=null){
 if(method==HttpMethod.Post){if(body?["dry_run"]?.GetValue<bool>()==true)return Task.FromResult<JsonNode>(new JsonObject());Commits++;Receipt=new JsonObject{["operation_key"]=key};if(Lose)throw new IOException("lost response");return Task.FromResult(Receipt.DeepClone());}
 Gets++;if(Receipt is null)throw new ApiFailure(404,"No committed receipt; this does not prove failure");return Task.FromResult(Receipt.DeepClone());}
}
class Screen{
 public string CompanyId="company";public bool CanWrite=true,Owned=true;public ApiMock Api=new();public int Refreshes,Errors;public Task Start()=>MasterCsvImport();
 Action CaptureFileSaveAccess()=>()=>{if(!Owned)throw new InvalidOperationException("stale");};
 void Error(Exception e){Errors++;}void Success(string message){}Task Refresh(){Refreshes++;return Task.CompletedTask;}
 Panel Stack()=>new();Label Text(string value,int size=0)=>new(){Text=value};Choice Select(string label,IEnumerable<(string,string)> values,string selected)=>new(){Value=selected};string Value(Choice value)=>value.Value;
 Button AsyncButton(string label,Func<Task> action,Action<Exception> error,bool primary=false)=>new(label,action,error);
 void RenderReport(Panel panel,JsonNode result){}void Table(Panel panel,JsonArray rows,string title){}
 async Task<bool> Dialog(string title,Panel panel,Func<Task> save,string action,Func<bool>? enabled=null,Func<bool>? unresolved=null){
 if(title.StartsWith("Recover")){await panel.Children.OfType<Button>().Single().Invoke();return false;}
 await panel.Children.OfType<Button>().Single().Invoke();if(enabled?.Invoke()==false)return false;await save();return true;}
 METHOD
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
 Console.WriteLine("PASS actual Windows import workflow: lost commit/restart GET-only recovery, missing receipt, capability loss and stale picker");
 }finally{Directory.Delete(folder,true);}
 }
}
'''.replace('METHOD',method)
with tempfile.TemporaryDirectory(prefix='apex-windows-import-workflow-') as directory:
 d=Path(directory);(d/'Program.cs').write_text(fixture)
 sources=['ImportReceiptRecovery.cs','Csv.cs','ScopedFileExport.cs']
 includes=''.join('<Compile Include="'+str(root/'native/windows/Services'/name)+'" />' for name in sources)
 (d/'Proof.csproj').write_text('<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><ImplicitUsings>enable</ImplicitUsings><Nullable>enable</Nullable></PropertyGroup><ItemGroup>'+includes+'</ItemGroup></Project>')
 env={**os.environ,'DOTNET_CLI_TELEMETRY_OPTOUT':'1','DOTNET_GENERATE_ASPNET_CERTIFICATE':'false','DOTNET_CLI_HOME':str(d/'home')}
 subprocess.run([args.dotnet,'run','--project',str(d/'Proof.csproj')],check=True,env=env)
