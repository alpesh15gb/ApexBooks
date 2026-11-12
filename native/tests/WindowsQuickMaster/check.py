from pathlib import Path
import argparse,os,subprocess,tempfile
root=Path(__file__).resolve().parents[3];p=argparse.ArgumentParser();p.add_argument('--dotnet',default='dotnet');p.add_argument('--before',action='store_true');args=p.parse_args()
s=(root/'native/windows/Views/Documents.cs').read_text();helper=s[s.index('        async Task QuickMaster('):s.index('        void AddLine(')]
if args.before:s=subprocess.check_output(['git','show','HEAD:native/windows/Views/Documents.cs'],cwd=root,text=True)
def callback(marker):
 a=s.index(marker);a=s.index('async()=>{',a)+len('async()=>');b=s.index('},LocalError);',a)+1;return s[a:b]
item=callback('var saveItem=AsyncButton');party=callback('addParty=AsyncButton')
fixture=r'''
using System.Text.Json.Nodes;using ApexBooks_Windows.Services;
class ApiFailure(int status,string message):Exception(message){public int Status=>status;}
enum Visibility{Visible,Collapsed}
class Recovery{public Visibility Visibility;}
static class J{public static string Today=>"2026-04-01";public static string Text(this JsonNode? n,string k)=>n?[k]?.ToString()??"";public static JsonObject Object(this JsonNode n)=>n.AsObject();}
static class ScopedFileExport{public static bool Current(Action a){try{a();return true;}catch{return false;}}}
class Field{public string Text="Original";}
class Submission{public bool Unresolved;}
class Line{public JsonObject Values=new(){["description"]="Original item",["rate"]="100",["gst_rate"]="0"};public bool Linked;public int Links;public JsonObject Data()=>Values.DeepClone().AsObject();public void LinkCreatedItem(JsonObject value){Links++;Linked=true;}}
class ApiMock{public int Posts;public bool Fail;public Exception? Failure;public List<string> Keys=new(),Bodies=new();public Task<JsonNode> SaveRecord(string cid,JsonObject body,string key){Keys.Add(key);Bodies.Add(body.ToJsonString());return Send(cid,HttpMethod.Post,body);}public TaskCompletionSource Gate=new();public string CompanyPath(string cid,string path)=>cid+path;public async Task<JsonNode> Send(string path,HttpMethod method,JsonObject body){Posts++;await Gate.Task;if(Failure is not null)throw Failure;if(Fail)throw new IOException("current error");return new JsonObject{["id"]="new-master",["name"]=body.Text("name")};}}
class Screen{
 public string cid="a",CompanyId="a",partyId="";public int stamp,generation,epoch;public bool sourceLoading,editorOpen=true,writer=true,purchase=true;public Action writeAccess;public Submission submission=new();public RetrySubmission quickSubmission=new();public string quickRetryKey="";public Func<Task>? retryQuickMaster;public Recovery quickRecovery=new();public ApiMock Api=new();public List<JsonNode> Records=new();public Field party=new(),phone=new(),gstin=new(),address=new(),shipping=new();public Line line=new();public List<Line> lines=new();public string Error="";
 public Screen(){lines.Add(line);writeAccess=()=>{if(!writer||cid!=CompanyId)throw new Exception("denied");};}
 Action CaptureFileSaveAccess(){var before=epoch;return()=>{if(before!=epoch)throw new Exception("stale");};}
 JsonObject BodyValue()=>new(){["name"]=party.Text,["address"]=address.Text};void LocalError(Exception e){Error=e.Message;}void ShowAddParty(){}Task Calculate()=>Task.CompletedTask;
 HELPER
 public async Task Item() ITEM
 public async Task Party() PARTY
}
class Program{
 static void Check(bool b,string why="Assertion failed"){if(!b)throw new Exception(why);}
 static async Task Main(){
 foreach(var kind in new[]{"party","item"})foreach(var mode in new[]{"edit","removed","company","role","access","closed","navigation","current"})foreach(var fail in new[]{false,true}){
 var s=new Screen();s.Api.Fail=fail;var pending=kind=="party"?s.Party():s.Item();
 if(mode=="edit"){s.party.Text="Newer party";s.line.Values["description"]="Newer item";}if(mode=="removed"){s.lines.Clear();s.partyId="different-party";}if(mode=="company")s.CompanyId="b";if(mode=="role")s.writer=false;if(mode=="access")s.epoch++;if(mode=="closed")s.editorOpen=false;if(mode=="navigation")s.generation++;
 s.Api.Gate.SetResult();try{await pending;}catch{if(!argsBefore)throw;}
 var applied=kind=="party"?s.partyId=="new-master":s.line.Links>0;
 Check(applied==(mode=="current"&&!fail),"Unexpected linking "+kind+"/"+mode);Check(!s.sourceLoading);
 if(mode is "company" or "role" or "access" or "closed" or "navigation")Check(s.Records.Count==0&&s.Error=="");
 }
 foreach(var kind in new[]{"party","item"}){var s=new Screen();var first=kind=="party"?s.Party():s.Item();var second=kind=="party"?s.Party():s.Item();s.Api.Gate.SetResult();await Task.WhenAll(first,second);Check(s.Api.Posts==1,"Duplicate master POST");var viewer=new Screen{writer=false};await (kind=="party"?viewer.Party():viewer.Item());Check(viewer.Api.Posts==0);}
 foreach(var kind in new[]{"party","item"}){
 var s=new Screen();s.Api.Gate.SetResult();s.Api.Fail=true;await(kind=="party"?s.Party():s.Item());Check(s.quickSubmission.Unresolved);var key=s.Api.Keys.Single();var body=s.Api.Bodies.Single();s.party.Text="Changed";s.line.Values["description"]="Changed";await(kind=="party"?s.Party():s.Item());Check(s.Api.Posts==1);s.writer=false;await s.retryQuickMaster!();Check(s.Api.Posts==1&&s.quickSubmission.Unresolved);s.writer=true;s.Api.Fail=false;await s.retryQuickMaster!();Check(s.Api.Posts==2&&s.Api.Keys.All(k=>k==key)&&s.Api.Bodies.All(b=>b==body)&&!s.quickSubmission.Unresolved);Check(s.partyId==""&&s.line.Links==0);
 var rejected=new Screen();rejected.Api.Gate.SetResult();rejected.Api.Failure=new ApiFailure(422,"invalid");await(kind=="party"?rejected.Party():rejected.Item());Check(!rejected.quickSubmission.Unresolved&&rejected.retryQuickMaster is null);rejected.Api.Failure=null;rejected.party.Text="Corrected";rejected.line.Values["description"]="Corrected";await(kind=="party"?rejected.Party():rejected.Item());Check(rejected.Api.Keys.Distinct().Count()==2&&rejected.Api.Bodies.Last().Contains("Corrected"));
 }
 Console.WriteLine("PASS unknown original body/key retry, changed/new and viewer blocked, definitive rejection corrected with new key");
 Console.WriteLine("PASS actual quick-add callbacks/helper: 16 party + 16 item delayed outcomes, duplicate and viewer gates");
 }
 const bool argsBefore=BEFORE;
}
'''.replace('HELPER',helper).replace('ITEM',item).replace('PARTY',party).replace('BEFORE',str(args.before).lower())
with tempfile.TemporaryDirectory(prefix='apex-quick-master-') as folder:
 d=Path(folder);(d/'Program.cs').write_text(fixture);(d/'Proof.csproj').write_text('<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><ImplicitUsings>enable</ImplicitUsings><Nullable>enable</Nullable></PropertyGroup><ItemGroup><Compile Include="'+str(root/'native/windows/Services/RetrySubmission.cs')+'" /></ItemGroup></Project>')
 subprocess.run([args.dotnet,'run','--project',str(d/'Proof.csproj')],check=True,env={**os.environ,'DOTNET_CLI_TELEMETRY_OPTOUT':'1','DOTNET_GENERATE_ASPNET_CERTIFICATE':'false','DOTNET_CLI_HOME':str(d/'home')})
