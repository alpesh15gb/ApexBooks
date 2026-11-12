"""Compile actual Windows recovery view and attachment download callback."""
from pathlib import Path
import argparse,tempfile,subprocess,os
root=Path(__file__).resolve().parents[3];p=argparse.ArgumentParser();p.add_argument('--dotnet',default='dotnet');args=p.parse_args()
s=(root/'native/windows/Views/Settings.cs').read_text();recovery=s[s.index('    private async Task RecoveryCodes()'):s.index('    private async Task AuditHistory()')]
a=(root/'native/windows/Views/RetainedReceipts.cs').read_text();download=a.split('AsyncButton("Download verified copy",async()=>{',1)[1].split('},Error)',1)[0]
assert 'ReadAccessInvalidated+=InvalidateRead;' in a and 'rows.Children.Clear();status.Text="Company access removed' in a
fixture=r'''
using System;using System.IO;using System.Linq;using System.Net.Http;using System.Text;using System.Text.Json.Nodes;using System.Collections.Generic;using System.Threading.Tasks;using System.Security.Cryptography;using ApexBooks_Windows.Services;
static class J{public static JsonArray Array(this JsonNode? node)=>node as JsonArray??new();public static string Text(this JsonNode? node,string key="")=>(key==""?node:node?[key])?.ToString()??"";public static decimal Number(this JsonNode? node,string key)=>decimal.Parse(node.Text(key));}
class Panel{public List<object> Children=new();}class TextBox{public string Text="";public bool IsReadOnly,AcceptsReturn;public object? FontFamily;}class PasswordBox{public string Header="",Password="synthetic-password";}class Button{public string Name="";public Func<Task> Action=()=>Task.CompletedTask;}
namespace Microsoft.UI.Xaml.Media{class FontFamily{public FontFamily(string value){}}}
class Caps{public long Limit(string key,long fallback,long maximum)=>maximum;}
class ApiStub{public Caps Capabilities=new();public TaskCompletionSource<JsonNode> Codes=new();public TaskCompletionSource<(byte[] Bytes,string Sha256,string ArchiveSha256)> Receipt=new();public Task<JsonNode> Send(string path,HttpMethod method,JsonObject body)=>Codes.Task;public Task<(byte[] Bytes,string Sha256,string ArchiveSha256)> DownloadBounded(string path,int maximum)=>Receipt.Task;public string CompanyPath(string cid,string path)=>cid+path;}
static class CompleteBackupTransfer{public static void VerifyHash(byte[] bytes,string expected){if(Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant()!=expected)throw new Exception("Checksum mismatch");}}
static class ApexFiles{public static int Saves;public static Task<bool> Save(byte[] bytes,string name,Action verify){verify();Saves++;return Task.FromResult(true);}}
class Retry{public bool Unresolved=false;}
class Model{public int epoch;public ApiStub Api=new();public event Action? ReadAccessInvalidated;public Panel? View;public TaskCompletionSource Opened=new();public TaskCompletionSource<bool> Closed=new();public string cid="a";public Retry retry=new();public JsonObject item=new(){["id"]="r",["filename"]="synthetic.pdf",["size_bytes"]="2",["sha256"]=Convert.ToHexString(SHA256.HashData(new byte[]{1,2})).ToLowerInvariant()};public Action exportAccess;
 public Model(){exportAccess=CaptureFileSaveAccess();}Action CaptureFileSaveAccess(){var original=epoch;return()=>{if(original!=epoch)throw new InvalidOperationException("Access changed");};}bool Current()=>true;Panel Stack()=>new();string Text(string value)=>value;void Error(Exception e){}Button AsyncButton(string name,Func<Task> action,Action<Exception> error)=>new(){Name=name,Action=action};
 async Task<bool> Dialog(string title,Panel panel,Func<Task> save,string action){if(title=="Generate recovery codes"){await save();return true;}View=panel;Opened.TrySetResult();return await Closed.Task;}
 public void Deny(){epoch++;ReadAccessInvalidated?.Invoke();}public Task Open()=>RecoveryCodes();public async Task Download(){DOWNLOAD}
 RECOVERY
}
static class Program{static JsonObject Codes()=>new(){["codes"]=new JsonArray("SYNTHETIC-ONE")};static async Task Main(){
 foreach(var outcome in new[]{"current","stale","current-error","stale-error"}){var m=new Model();var task=m.Open();if(outcome.StartsWith("stale"))m.Deny();if(outcome.EndsWith("error"))m.Api.Codes.SetException(new IOException("synthetic error"));else m.Api.Codes.SetResult(Codes());if(outcome=="current"){await m.Opened.Task;var save=m.View!.Children.OfType<Button>().Single();ApexFiles.Saves=0;await save.Action();if(ApexFiles.Saves!=1)throw new Exception("Current codes not saved");m.Closed.SetResult(true);await task;await save.Action();if(ApexFiles.Saves!=1)throw new Exception("Closed codes saved");}else if(outcome=="current-error"){try{await task;throw new Exception("Error hidden");}catch(IOException){}}else{await task;if(m.View!=null)throw new Exception("Stale codes shown");}}
 {var m=new Model();var task=m.Open();m.Api.Codes.SetResult(Codes());await m.Opened.Task;var output=m.View!.Children.OfType<TextBox>().Single();var save=m.View.Children.OfType<Button>().Single();m.Deny();ApexFiles.Saves=0;await save.Action();if(output.Text!=""||ApexFiles.Saves!=0)throw new Exception("Denied codes retained/saved");m.Closed.SetResult(true);await task;}
 foreach(var outcome in new[]{"current","stale","corrupt","stale-corrupt","error","stale-error"}){var m=new Model();ApexFiles.Saves=0;var task=m.Download();if(outcome.StartsWith("stale"))m.Deny();if(outcome.EndsWith("error"))m.Api.Receipt.SetException(new IOException("synthetic"));else m.Api.Receipt.SetResult((outcome.EndsWith("corrupt")?new byte[]{9}:new byte[]{1,2},m.item.Text("sha256"),""));if(outcome is "corrupt" or "error"){try{await task;throw new InvalidOperationException("Current bad response hidden");}catch(Exception e)when(e is not InvalidOperationException){}}else await task;if(ApexFiles.Saves!=(outcome=="current"?1:0))throw new Exception("Wrong attachment save");}
 Console.WriteLine("PASS 11 actual recovery/attachment response/view/save scenarios with synthetic controls");
}}
'''.replace('RECOVERY',recovery).replace('DOWNLOAD',download)
with tempfile.TemporaryDirectory(prefix='apex-retained-read-') as temp:
 temp=Path(temp);(temp/'Proof.cs').write_text(fixture);(temp/'ScopedFileExport.cs').write_text((root/'native/windows/Services/ScopedFileExport.cs').read_text());(temp/'Proof.csproj').write_text('<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><ImplicitUsings>enable</ImplicitUsings><Nullable>enable</Nullable></PropertyGroup></Project>')
 subprocess.run([args.dotnet,'run','--project',str(temp/'Proof.csproj')],check=True,env=os.environ)
