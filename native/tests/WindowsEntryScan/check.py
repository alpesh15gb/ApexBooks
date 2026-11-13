from pathlib import Path
import argparse,os,subprocess,tempfile
root=Path(__file__).resolve().parents[3];p=argparse.ArgumentParser();p.add_argument('--dotnet',default='dotnet');p.add_argument('--source',type=Path);args=p.parse_args()
s=(root/'native/windows/Views/Documents.cs').read_text(encoding="utf-8")
if args.source:
 old=args.source.read_text(encoding="utf-8");method='async Task ScanPurchase()\n'+old[old.index('            {'):old.index('            }, LocalError)')]+'}'
else:method=s[s.index('            async Task ScanPurchase()'):s.index('            var ocr = AsyncButton("Scan purchase bill", ScanPurchase')]
fixture=r'''
using System.Text.Json.Nodes;
static class J{public static string Text(this JsonNode? n,string key)=>n?[key]?.ToString()??"";public static JsonArray Array(this JsonNode? n)=>n as JsonArray??new();}
static class ScopedFileExport{public static bool Current(Action a){try{a();return true;}catch{return false;}}}
class Field{public string Text="original";public bool IsChecked;public Field Picker=>this;public DateTimeOffset? Date;}
enum InfoBarSeverity{Warning,Error}
class Info{public InfoBarSeverity Severity;public string Message="";public bool IsOpen;}
class Submission{public bool Unresolved;}
static class ApexFiles{public static TaskCompletionSource PickGate=new(),ImageGate=new();public static bool Cancel;public static Task<object?> Pick(params string[] extensions)=>DoPick();static async Task<object?> DoPick(){await PickGate.Task;return Cancel?null:new object();}public static async Task<string> Image(object f,int size,int bytes){await ImageGate.Task;return "synthetic";}public static void Reset(){PickGate=new();ImageGate=new();Cancel=false;}}
class ApiMock{public int Calls;public TaskCompletionSource Gate=new();public bool Fail;public string CompanyPath(string cid,string path)=>cid+path;public async Task<JsonNode> Send(string path,HttpMethod method,JsonObject body){Calls++;await Gate.Task;if(Fail)throw new IOException("OCR failed");return new JsonObject{["draft"]=new JsonObject{["supplier_name"]="Scanned",["items"]=new JsonArray()}};}}
class Screen{
 public string cid="a",CompanyId="a",partyId="party";public int stamp,generation,epoch;public bool sourceLoading,editorOpen=true,writer=true;public Submission submission=new(),quickSubmission=new();public Field party=new(),phone=new(),shipping=new(),due=new(),discount=new(),round=new(),number=new(),address=new(),gstin=new(),supplierState=new(),supply=new(),date=new();public JsonObject Company=new(){["state_code"]="27"};public Info info=new();public ApiMock Api=new();public string Error="";public int Replaced;public Action writeAccess;
 public Screen(){writeAccess=()=>{if(!writer||CompanyId!=cid)throw new Exception("access");};}
 Action CaptureFileSaveAccess(){var before=epoch;return()=>{if(epoch!=before)throw new Exception("access");};}
 JsonObject BodyValue()=>new(){["party"]=party.Text};void ReplaceLines(JsonArray lines,bool scanned){Replaced++;}void LocalError(Exception e){Error=e.Message;}
 public METHOD
}
class Program{
 static void Check(bool b,string m="Assertion failed"){if(!b)throw new Exception(m);}
 static async Task Main(){
 foreach(var stage in new[]{"picker","image","ocr"})foreach(var mode in new[]{"company","access","closed","role","navigation","edit","current"})foreach(var fail in new[]{false,true}){
 ApexFiles.Reset();var s=new Screen();s.Api.Fail=fail;if(stage!="picker")ApexFiles.PickGate.SetResult();if(stage=="ocr")ApexFiles.ImageGate.SetResult();var task=s.ScanPurchase();
 if(mode=="company")s.CompanyId="b";if(mode=="access")s.epoch++;if(mode=="closed")s.editorOpen=false;if(mode=="role")s.writer=false;if(mode=="navigation")s.generation++;if(mode=="edit")s.party.Text="newer";
 ApexFiles.PickGate.TrySetResult();ApexFiles.ImageGate.TrySetResult();s.Api.Gate.SetResult();await task;
 Check(s.Api.Calls==((stage=="ocr"||mode=="current")?1:0),"Stale scan dispatch "+stage+"/"+mode);Check(s.Replaced==((mode=="current"&&!fail)?1:0),"Draft overwritten "+mode);Check(!s.sourceLoading);if(mode!="current"&&mode!="edit")Check(s.Error=="");
 }
 ApexFiles.Reset();var cancel=new Screen();ApexFiles.Cancel=true;ApexFiles.PickGate.SetResult();await cancel.ScanPurchase();Check(cancel.Api.Calls==0&&!cancel.sourceLoading);
 ApexFiles.Reset();var dupe=new Screen();var first=dupe.ScanPurchase();await dupe.ScanPurchase();ApexFiles.PickGate.SetResult();ApexFiles.ImageGate.SetResult();dupe.Api.Gate.SetResult();await first;Check(dupe.Api.Calls==1);
 var unresolved=new Screen();unresolved.submission.Unresolved=true;await unresolved.ScanPurchase();Check(unresolved.Api.Calls==0);
 Console.WriteLine("PASS actual Windows scan: 42 delayed picker/image/OCR outcomes, cancellation, duplicate and unresolved guards");
 }
}
'''.replace('METHOD',method)
with tempfile.TemporaryDirectory(prefix='apex-windows-scan-') as folder:
 d=Path(folder);(d/'Program.cs').write_text(fixture, encoding="utf-8");(d/'Proof.csproj').write_text('<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><ImplicitUsings>enable</ImplicitUsings><Nullable>enable</Nullable></PropertyGroup></Project>', encoding="utf-8")
 subprocess.run([args.dotnet,'run','--project',str(d/'Proof.csproj')],check=True,env={**os.environ,'DOTNET_CLI_TELEMETRY_OPTOUT':'1','DOTNET_GENERATE_ASPNET_CERTIFICATE':'false','DOTNET_CLI_HOME':str(d/'home')})
