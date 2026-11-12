from pathlib import Path
import argparse,os,subprocess,tempfile
root=Path(__file__).resolve().parents[3];p=argparse.ArgumentParser();p.add_argument('--dotnet',default='dotnet');args=p.parse_args()
s=(root/'native/windows/Views/Documents.cs').read_text()
def function(marker):
 start=s.index(marker);brace=s.index('{',start);depth=1;end=brace+1
 while depth:
  if s[end]=='{':depth+=1
  if s[end]=='}':depth-=1
  end+=1
 return s[start:end]
save=function('async Task Save()')
helper=function('private Action CaptureDocumentWriteAccess()')
assert 'canSave:()=>ScopedFileExport.Current(writeAccess)&&!sourceLoading&&pendingSourceId is null' in s
assert s.count('!ScopedFileExport.Current(readAccess)')>=2
fixture=r'''
using System.Text.Json.Nodes;using ApexBooks_Windows.Services;
class ApiFailure(int status,string message):Exception(message){public int Status=>status;}
static class J{public static string Text(this JsonNode? n,string key)=>n?[key]?.ToString()??"";}
class Field{public string Text="Original party";}
class Line{public JsonObject Data()=>new(){["item_id"]="item"};}
class Review{public bool IsAcknowledged(string value)=>true;}
static class WorkflowMasterValues{public static bool IsActive(JsonNode n)=>true;}
static class NativeUi{public static void SetFormEnabled(object panel,bool enabled){}}
class ApiMock{public bool SignedIn=true;public int SessionGeneration,Calls;public Exception? Failure;public List<string> Bodies=new(),Keys=new(),Payments=new();public Task<JsonNode> SaveRecord(string cid,JsonObject body,string key,JsonObject? previous){Calls++;Bodies.Add(body.ToJsonString());Keys.Add(key);if(Failure is not null)throw Failure;return Task.FromResult<JsonNode>(new JsonObject{["id"]="saved"});}public Task<JsonNode> SaveRecordWithPayment(string cid,JsonObject body,JsonObject payment,string key){Payments.Add(payment.ToJsonString());return SaveRecord(cid,body,key,null);}}
class Screen{
 public string CompanyId="a",role="editor";public int workspaceGeneration;public bool recordsReady=true;public bool CanWrite=>recordsReady&&role is "editor" or "owner";public ApiMock Api=new();public Field party=new();public RetrySubmission submission=new();public bool sourceLoading=false;public string? pendingSourceId;Review fixedReview=new();string cid="a",kind="purchase_order",partyId="",appliedTo="",retryKey=Guid.NewGuid().ToString();JsonObject? previous=null,lastPayment=null;JsonNode? savedResult;object panel=new();List<Line> lines=new(){new()};List<JsonObject> Records=new();public JsonObject? Pay;Action writeAccess;
 public Screen(){writeAccess=CaptureDocumentWriteAccess();}
 bool NeedsFixedReview()=>false;string FixedSignature()=>"";JsonObject? PaymentBody()=>Pay;JsonObject BodyValue()=>new(){["name"]=party.Text};
 HELPER
 public SAVE
}
class Program{
 static void Check(bool value,string message="Assertion failed"){if(!value)throw new Exception(message);}
 static async Task Reject(Func<Task> action){try{await action();}catch{return;}throw new Exception("Expected local write rejection");}
 static async Task Main(){
 var viewer=new Screen();viewer.role="viewer";await Reject(viewer.Save);Check(viewer.Api.Calls==0,"Viewer document dispatched");
 foreach(var paid in new[]{false,true}){
  var f=new Screen();if(paid)f.Pay=new JsonObject{["amount"]="100"};f.Api.Failure=new IOException("lost response");await Reject(f.Save);Check(f.submission.Unresolved&&f.Api.Calls==1);var original=f.Api.Bodies.Single();var key=f.Api.Keys.Single();
  f.recordsReady=false;await Reject(f.Save);Check(f.Api.Calls==1&&f.submission.Unresolved);f.recordsReady=true;f.role="viewer";await Reject(f.Save);Check(f.Api.Calls==1&&f.submission.Unresolved);
  f.party.Text="Changed while uncertain";if(paid)f.Pay=new JsonObject{["amount"]="500"};f.role="editor";f.Api.Failure=null;await f.Save();Check(f.Api.Calls==2&&f.Api.Bodies.All(x=>x==original)&&f.Api.Keys.All(x=>x==key)&&!f.submission.Unresolved);if(paid)Check(f.Api.Payments.Distinct().Count()==1);
 }
 var rejected=new Screen();rejected.Pay=new JsonObject{["amount"]="100"};rejected.Api.Failure=new ApiFailure(422,"invalid document");await Reject(rejected.Save);Check(!rejected.submission.Unresolved&&rejected.Api.Payments.Count==1);rejected.Pay=null;rejected.party.Text="Corrected";rejected.Api.Failure=null;await rejected.Save();Check(rejected.Api.Calls==2&&rejected.Api.Payments.Count==1&&rejected.Api.Bodies.Last().Contains("Corrected"),"Definitive rejection retained unwanted payment");
 foreach(var mode in new[]{"company","session","workspace","logout"}){var f=new Screen();if(mode=="company")f.CompanyId="b";if(mode=="session")f.Api.SessionGeneration++;if(mode=="workspace")f.workspaceGeneration++;if(mode=="logout")f.Api.SignedIn=false;await Reject(f.Save);Check(f.Api.Calls==0);}
 Console.WriteLine("PASS actual Windows document Save/guard: viewer blocked, read denial/recovery preserves original body/key and payment, four stale scopes blocked");
 }
}
'''.replace('HELPER',helper).replace('SAVE',save)
with tempfile.TemporaryDirectory(prefix='apex-document-access-') as folder:
 d=Path(folder);(d/'Program.cs').write_text(fixture);(d/'Proof.csproj').write_text('<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><ImplicitUsings>enable</ImplicitUsings><Nullable>enable</Nullable></PropertyGroup><ItemGroup><Compile Include="'+str(root/'native/windows/Services/RetrySubmission.cs')+'" /></ItemGroup></Project>')
 subprocess.run([args.dotnet,'run','--project',str(d/'Proof.csproj')],check=True,env={**os.environ,'DOTNET_CLI_TELEMETRY_OPTOUT':'1','DOTNET_GENERATE_ASPNET_CERTIFICATE':'false','DOTNET_CLI_HOME':str(d/'home')})
