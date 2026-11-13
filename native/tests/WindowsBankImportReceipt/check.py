from pathlib import Path
import argparse,tempfile,subprocess,os
root=Path(__file__).resolve().parents[3]
p=argparse.ArgumentParser();p.add_argument('--dotnet',default='dotnet');args=p.parse_args()
s=(root/'native/windows/Views/StatementImport.cs').read_text(encoding="utf-8")
body=s.split('try{if(await Dialog("Import bank statement",panel,async()=>{',1)[1].split('},"Import reviewed rows"',1)[0]
lookup=s.split('"Check original import",async()=>{',1)[1].split('},CurrentError,true)',1)[0]
start=s.index('try{if(await Dialog("Import bank statement"')
finish=s[start:s.index('\n    }\n}',start)]
assert '()=>ImportStatement(Value(bank))' in (root/'native/windows/Views/Accounting.cs').read_text(encoding="utf-8")
fixture='''
using System.Text.Json.Nodes;
using System.Net.Http;
using ApexBooks_Windows.Services;
class ApiFailure(int status,string message):Exception(message){public int Status=>status;}
static class J{public static bool Flag(this JsonNode? node,string key)=>bool.TryParse(node.Text(key),out var value)&&value;public static string Text(this JsonNode? node,string key)=>node?[key]?.GetValue<string>()??"";}
class ApiMock{public int Gets;public string LookupKey="";public Task<JsonNode> Send(string path){Gets++;if(Failure is not null)throw Failure;return Task.FromResult<JsonNode>(new JsonObject{["operation_key"]=LookupKey});}public List<string?> Keys=new();public Exception? Failure;public static string CompanyPath(string id,string suffix)=>id+suffix;public Task<JsonNode> Send(string path,HttpMethod method,JsonNode? body,string? key){Keys.Add(key);if(Failure is not null)throw Failure;return Task.FromResult<JsonNode>(new JsonObject{["operation_key"]=key});}}
class Choice{public bool IsEnabled=true;public string Value="bank";}
class Label{public string Text="";}
class Program{
 static void Check(bool ok){if(!ok)throw new Exception("Assertion failed");}
 static void Reject(Action action){try{action();}catch{return;}throw new Exception("Expected rejection");}
 static async Task Main(){
  var folder=Path.Combine(Path.GetTempPath(),"apex-import-proof-"+Guid.NewGuid());Directory.CreateDirectory(folder);
  try{
   Check(ClientCapabilities.Parse(new JsonObject{["capabilities_version"]=1,["supported_features"]=new JsonArray("bank_import_receipts")}).Supports("bank_import_receipts"));Check(!ClientCapabilities.Unavailable.Supports("bank_import_receipts"));
   var path=ImportReceiptRecovery.Location(folder,"https://synthetic.invalid","actor@example.invalid","company");
   Check(ImportReceiptRecovery.Location(folder,"https://synthetic.invalid","actor@example.invalid","company",true)!=path);
   var recovery=new ImportReceiptRecovery(path);var original="SYNTHETIC PRIVATE PAYLOAD";var first=recovery.Begin(original,"bank",true);
   Check(first.Key is not null&&!first.Retry);Check(!File.ReadAllText(path).Contains(original)&&File.ReadAllText(path).Split('\\n').Length==3);
   Reject(()=>recovery.Begin(original,"bank",true));recovery.Failed(first,0);recovery.End();File.Delete(path);var retained=recovery.Begin(original,"bank",true);Check(retained.Key==first.Key&&retained.Retry);recovery.End();
   var reopened=new ImportReceiptRecovery(path);Check(reopened.Pending);Reject(()=>reopened.Begin("changed","bank",true));Reject(()=>reopened.Begin(original,"bank",false));
   var retry=reopened.Begin(original,"bank",true);Check(retry.Key==first.Key&&retry.Retry);reopened.Failed(retry,422);reopened.End();Check(reopened.Pending);Reject(()=>reopened.Confirmed("wrong"));reopened.Confirmed(first.Key!);Check(!File.Exists(path));
   var rejected=reopened.Begin(original,"bank",true);reopened.Failed(rejected,422);reopened.End();Check(!File.Exists(path));var legacy=reopened.Begin(original,"bank",false);Check(legacy.Key is null&&!File.Exists(path));reopened.End();
   Check(ImportReceiptRecovery.Location(folder,"https://other.invalid","actor@example.invalid","company")!=path);Check(ImportReceiptRecovery.Location(folder,"https://synthetic.invalid","other@example.invalid","company")!=path);Check(ImportReceiptRecovery.Location(folder,"https://synthetic.invalid","actor@example.invalid","other")!=path);
   using(var barrier=new Barrier(4)){var tasks=Enumerable.Range(0,4).Select(_=>Task.Run(()=>{barrier.SignalAndWait();var r=new ImportReceiptRecovery(path);return r.Begin(original,"bank",true).Key;})).ToArray();var keys=await Task.WhenAll(tasks);Check(keys.Distinct().Count()==1);new ImportReceiptRecovery(path).Confirmed(keys[0]!);}
   using(var barrier=new Barrier(4)){var tasks=Enumerable.Range(0,4).Select(i=>Task.Run(()=>{barrier.SignalAndWait();try{new ImportReceiptRecovery(path).Begin(original+i,"bank",true);return true;}catch{return false;}})).ToArray();Check((await Task.WhenAll(tasks)).Count(v=>v)==1);var r=new ImportReceiptRecovery(path);r.Confirmed(r.Saved!.Key);}
   File.WriteAllText(path,"corrupt");Reject(()=>new ImportReceiptRecovery(path));File.Delete(path);
   var receipt=new ImportReceiptRecovery(path);var Api=new ApiMock();var kind=new Choice();var recoveryNotice=new Label();var cid="company";var reviewed="";var validating=false;var allowed=true;var supported=true;
   void Guard(){if(!allowed)throw new InvalidOperationException("Access changed");}
   bool Supported()=>supported;
   string Value(Choice value)=>value.Value;
   JsonObject Body()=>new(){["kind"]="bank",["rows"]=new JsonArray(new JsonObject{["name"]="private party"})};
   JsonObject Build(){Guard();return Body();}
   void Verify()=>Guard();void RecoveryState(){}
   reviewed=Body().ToJsonString();
   async Task Save(){CALLBACK}
   Api.Failure=new IOException("lost");try{await Save();throw new Exception("Expected failure");}catch(IOException){}Check(receipt.Pending&&!receipt.Busy);var key=Api.Keys.Single();
   Api.Failure=new ApiFailure(422,"later rejection");try{await Save();throw new Exception("Expected failure");}catch(ApiFailure){}Check(receipt.Pending);
   Api.Failure=null;await Save();Check(!receipt.Pending&&Api.Keys.All(value=>value==key));allowed=false;try{await Save();throw new Exception("Expected access failure");}catch(InvalidOperationException){}Check(Api.Keys.Count==3);
   allowed=true;Api.Failure=new IOException("lost again");try{await Save();}catch(IOException){}
   var saved=receipt.Saved!;Api.LookupKey=saved.Key;Api.Failure=null;bool checking=false,recovered=false;var message=new Label();void RecoveryGuard()=>Guard();
   async Task Lookup(){LOOKUP}
   var count=Api.Keys.Count;await Lookup();Check(recovered&&!receipt.Pending&&Api.Gets==1&&Api.Keys.Count==count);
   allowed=false;try{await Lookup();throw new Exception("Expected access failure");}catch(InvalidOperationException){}Check(Api.Gets==1);
   allowed=true;var panel=new object();var closed=false;var cancel=false;var completions=0;Exception? refreshFailure=null;Action access=Guard;bool CanWrite=true;
   async Task<bool> Dialog(string title,object panel,Func<Task> action,string label,Func<bool> enabled,Func<bool> unresolved){if(cancel||!enabled())return false;await action();return true;}
   Task FinishConfirmedImport(string text){Check(text=="Bank import confirmed.");completions++;if(refreshFailure is not null)throw refreshFailure;return Task.CompletedTask;}
   async Task Import(){FINISH}
   count=Api.Keys.Count;refreshFailure=new ApiFailure(503,"confirmed but refresh failed");
   try{await Import();throw new Exception("Expected refresh failure");}catch(ApiFailure){}
   Check(completions==1&&closed&&!receipt.Pending&&Api.Keys.Count==count+1);
   closed=false;cancel=true;await Import();Check(completions==1&&closed&&Api.Keys.Count==count+1);
   cancel=false;closed=false;refreshFailure=null;await Import();Check(completions==2&&closed&&Api.Keys.Count==count+2&&!receipt.Pending);
   Console.WriteLine("PASS actual bank dialog completion: one POST on confirmed refresh failure, none on cancel, current success");
   Console.WriteLine("PASS Windows bank receipt persistence/races and actual save callback: frozen retries, role guard, legacy and corruption");
  }finally{Directory.Delete(folder,true);}
 }
}
'''.replace('CALLBACK',body.replace('Api.CompanyPath','ApiMock.CompanyPath')).replace('LOOKUP',lookup.replace('Api.CompanyPath','ApiMock.CompanyPath')).replace('FINISH',finish.replace('Api.CompanyPath','ApiMock.CompanyPath'))
with tempfile.TemporaryDirectory(prefix='apex-windows-import-') as directory:
 d=Path(directory);(d/'Program.cs').write_text(fixture, encoding="utf-8")
 (d/'Proof.csproj').write_text('<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><ImplicitUsings>enable</ImplicitUsings><Nullable>enable</Nullable></PropertyGroup><ItemGroup><Compile Include="'+str(root/'native/windows/Services/ImportReceiptRecovery.cs')+'" /><Compile Include="'+str(root/'native/windows/Services/ClientCapabilities.cs')+'" /><Compile Include="'+str(root/'native/windows/Services/BuildIdentity.cs')+'" /><Compile Include="'+str(root/'native/windows/Services/ScopedFileExport.cs')+'" /></ItemGroup></Project>', encoding="utf-8")
 env={**os.environ,'DOTNET_CLI_TELEMETRY_OPTOUT':'1','DOTNET_SKIP_FIRST_TIME_EXPERIENCE':'1','DOTNET_GENERATE_ASPNET_CERTIFICATE':'false','DOTNET_CLI_HOME':str(d/'home')}
 subprocess.run([args.dotnet,'run','--project',str(d/'Proof.csproj')],check=True,env=env)
