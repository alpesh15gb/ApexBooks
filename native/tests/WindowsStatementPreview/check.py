"""Compile the actual statement-preview callback with delayed synthetic requests."""
from pathlib import Path
import argparse, tempfile, subprocess, os
root=Path(__file__).resolve().parents[3]
p=argparse.ArgumentParser();p.add_argument('--dotnet',default='dotnet');args=p.parse_args()
s=(root/'native/windows/Views/StatementImport.cs').read_text()
callback=s.split('AsyncButton("Validate and preview",async()=>{',1)[1].split('},Error,true)',1)[0]
fixture=r'''
using System.Text.Json.Nodes;using System.Net.Http;using ApexBooks_Windows.Services;
static class J{public static JsonArray Array(this JsonNode? n)=>n as JsonArray??new();public static JsonNode? Copy(this JsonNode? n)=>n?.DeepClone();}
class Panel{public List<object> Children=new();}
class Transport{public int calls;public TaskCompletionSource<JsonNode> response=new();public string CompanyPath(string c,string p)=>c+p;public Task<JsonNode> Send(string p,HttpMethod m,JsonObject b){calls++;return response.Task;}}
class Flow{public bool validating,closed,denied;public int revision,renders;public string reviewed="",cid="a";public Panel preview=new();public Transport Api=new();void Verify(){if(closed||denied)throw new InvalidOperationException("Stale");}JsonObject Build(){Verify();return new(){["lines"]=new JsonArray(new JsonObject{["amount"]="1"})};}void RenderReport(Panel p,JsonNode r,string t){renders++;}void Table(Panel p,JsonArray a,string t){}public async Task Preview(){CALLBACK}}
class Program{static async Task Main(){foreach(var mode in new[]{"current","mapping","denied","closed","error","stale-error","duplicate"}){var f=new Flow();var task=f.Preview();if(mode=="duplicate")await f.Preview();if(mode is "mapping" or "stale-error")f.revision++;if(mode=="denied")f.denied=true;if(mode=="closed")f.closed=true;if(mode.EndsWith("error"))f.Api.response.SetException(new IOException("Synthetic"));else f.Api.response.SetResult(new JsonObject());if(mode=="error"){try{await task;throw new Exception("Current failure hidden");}catch(IOException){}}else await task;bool current=mode is "current" or "duplicate";if(f.Api.calls!=1||f.validating||f.renders!=(current?1:0)||(f.reviewed!="")!=current)throw new Exception("Bad preview outcome: "+mode);}Console.WriteLine("PASS seven actual preview callback cases: current, changed mapping, denied, closed, errors and duplicate clicks");}}
'''.replace('CALLBACK',callback)
with tempfile.TemporaryDirectory(prefix='apex-statement-preview-') as d:
 d=Path(d);(d/'Proof.cs').write_text(fixture);(d/'ScopedFileExport.cs').write_text((root/'native/windows/Services/ScopedFileExport.cs').read_text());(d/'Proof.csproj').write_text('<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><ImplicitUsings>enable</ImplicitUsings><Nullable>enable</Nullable></PropertyGroup></Project>')
 subprocess.run([args.dotnet,'run','--project',str(d/'Proof.csproj')],check=True,env=os.environ)
