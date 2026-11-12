"""Compile actual export callbacks, isolating UI controls and transport only."""
from pathlib import Path
import argparse,tempfile,subprocess,os
root=Path(__file__).resolve().parents[3];p=argparse.ArgumentParser();p.add_argument('--dotnet',default='dotnet');args=p.parse_args()
settings=(root/'native/windows/Views/Settings.cs').read_text();cash=(root/'native/windows/Views/Accounting.cs').read_text();complete=(root/'native/windows/Views/CompleteBackups.cs').read_text()
def between(s,start,end):return s.split(start,1)[1].split(end,1)[0]
bodies={
 'Legacy':between(settings,'await Dialog("Download company backup",panel,async()=>{','},"Download backup")'),
 'Data':between(settings,'await Dialog("Export company data",panel,async()=>{','},"Export")'),
 'Cash':between(cash,'AsyncButton("Export "+fmt,async()=>{','},Error)'),
 'Complete':between(complete,'await Dialog("Complete portable backup",panel,async()=>{','},"Verify and save backup"')}
reporting=(root/'native/windows/Views/Reporting.cs').read_text()
bodies['Report']=reporting.split('            async Task Export(string format){',1)[1].split('\n',1)[0].rsplit('}',1)[0]
bodies['Party']=between(reporting,'AsyncButton("Export "+format.ToUpperInvariant(),async()=>{','},Error)')
bodies['Document']=between(reporting,'private async Task ShowDocumentPdf(JsonObject row,string template)\n    {','\n    }')
for text in (settings,cash,complete):assert 'var exportAccess=CaptureFileSaveAccess();' in text
methods='\n'.join('public async Task '+name+'(){'+body+'}' for name,body in bodies.items())
fixture=r'''
using ApexBooks_Windows.Services;
using System.Text.Json.Nodes;using System.Collections.Generic;using System;using System.IO;using System.Linq;using System.Threading.Tasks;
static class J{public static string Today=>"2026-04-01";public static string Text(this JsonNode node,string key)=>node[key]?.ToString()??"";public static bool Flag(this JsonNode? node,string key)=>false;}
class Panel{public List<object> Children=new();}
class Field{public string Value="2026-04-01";public string Password="synthetic-password";public bool? IsChecked=true;public string Text="";}
class Meta{public string Text(string key)=>"synthetic";}
class ApiStub{public TaskCompletionSource<byte[]> Pending=new();public string CompanyPath(string id,string path)=>"/companies/"+id+path;public Task<byte[]> Download(string path)=>Pending.Task;}
class Transfer(ApiStub api){public int Limit=100;public Meta Metadata=new();public async Task<MemoryStream> DownloadExport(string id,IProgress<string> progress)=>new(await api.Pending.Task);public Task Cancel(string id)=>Task.CompletedTask;}
static class CompleteBackupTransfer{public static MemoryStream Stage()=>new();}
static class Crypto{public static bool Hold,Fail;public static TaskCompletionSource Entered=new(),Release=new();public static void Transform(){if(Hold){Entered.TrySetResult();Release.Task.GetAwaiter().GetResult();}if(Fail)throw new IOException("synthetic encryption failure");}}
static class StreamingEncryptedBackup{public static void Encrypt(Stream input,Stream output,string password,int limit){Crypto.Transform();input.CopyTo(output);}}
static class ApexFiles{
 public static int Saves;public static byte[] EncryptBackup(byte[] bytes,string password){Crypto.Transform();return bytes;}
 public static Task<bool> Save(byte[] bytes,string name,Action verify){verify();Saves++;return Task.FromResult(true);}
 public static Task<bool> SaveStream(Stream bytes,string name,Action verify){verify();Saves++;return Task.FromResult(true);}
}
class Model{
 public bool Current=true;public ApiStub Api=new();public string cid="company-a",CompanyId="company-a";public int epoch=0,generation=0;public Action exportAccess;public Field password=new(),encrypt=new(),progress=new();public string kind="party",format="xlsx",fmt="xlsx";public Transfer transfer;
 public bool gst=false;public string mode="custom",ready="/report?query=1",filename="synthetic",template="";public int stamp;public Field period=new();public JsonNode? loaded;public Panel Body=new();public object results=new();public JsonObject row=new(){["id"]="record",["kind"]="sales_invoice",["number"]="INV-1"};
 Action CaptureFileSaveAccess()=>exportAccess;void Dates(){}string Path()=>ready;string Query()=>"?query=1";string Friendly(string value)=>value;Task ShowPdf(byte[] bytes,string name,JsonObject? record=null,Action? originalAccess=null){originalAccess!();ApexFiles.Saves++;return Task.CompletedTask;}
 public Model(){Body.Children.Add(results);exportAccess=()=>{if(!Current)throw new InvalidOperationException("changed workspace");};transfer=new(Api);}
 string Value(string value)=>value;string ExportPath(string extension)=>"/companies/company-a/cash-book"+extension;
 METHODS
}
static class Program{static async Task Main(){
 int cases=0;
 foreach(var flow in new[]{"Legacy","Data","Cash","Complete","Report","ReportPdf","Party","Document"})foreach(var stage in new[]{"fetch","encrypt"})foreach(var outcome in new[]{"current","stale","stale-error","current-error"}){
  if(stage=="encrypt"&&flow is not ("Legacy" or "Complete"))continue;
  Crypto.Hold=stage=="encrypt";Crypto.Fail=Crypto.Hold&&outcome.EndsWith("error");Crypto.Entered=new();Crypto.Release=new();
  var m=new Model();if(flow=="ReportPdf")m.format="pdf";ApexFiles.Saves=0;var task=flow switch{"Legacy"=>m.Legacy(),"Data"=>m.Data(),"Cash"=>m.Cash(),"Report" or "ReportPdf"=>m.Report(),"Party"=>m.Party(),"Document"=>m.Document(),_=>m.Complete()};
  if(stage=="encrypt"){m.Api.Pending.SetResult(new byte[]{1,2});await Crypto.Entered.Task.WaitAsync(TimeSpan.FromSeconds(5));}
  if(outcome.StartsWith("stale"))m.Current=false;
  if(stage=="encrypt")Crypto.Release.SetResult();else if(outcome.EndsWith("error"))m.Api.Pending.SetException(new IOException("synthetic failure"));else m.Api.Pending.SetResult(new byte[]{1,2});
  if(outcome=="current-error"){try{await task;throw new Exception("Current failure hidden");}catch(IOException){}}else await task;
  if(ApexFiles.Saves!=(outcome=="current"?1:0))throw new Exception("Incorrect file side effect "+flow+" "+stage+" "+outcome);cases++;
 }
 Console.WriteLine($"PASS {cases} actual export callback fetch/encryption cases; synthetic controls/crypto");
}}

'''.replace('METHODS',methods)
with tempfile.TemporaryDirectory(prefix='apex-export-context-') as temp:
 temp=Path(temp);(temp/'Proof.cs').write_text(fixture);(temp/'ScopedFileExport.cs').write_text((root/'native/windows/Services/ScopedFileExport.cs').read_text());(temp/'Proof.csproj').write_text('<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><ImplicitUsings>enable</ImplicitUsings><Nullable>enable</Nullable></PropertyGroup></Project>')
 subprocess.run([args.dotnet,'run','--project',str(temp/'Proof.csproj')],check=True,env=os.environ)
