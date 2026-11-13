"""Compile production transfer service with fake transport and delayed ownership changes."""
from pathlib import Path
import argparse,tempfile,subprocess,os
root=Path(__file__).resolve().parents[3];p=argparse.ArgumentParser();p.add_argument('--dotnet',default='dotnet');args=p.parse_args()
fixture=r'''
using System.Text.Json.Nodes;using System.Net.Http;using ApexBooks_Windows.Services;
namespace ApexBooks_Windows.Services {
public class ApiFailure:Exception{public int Status=>500;}
public class Caps{public long Limit(string key,long fallback,long maximum)=>maximum;}
public static class J{public static string Text(this JsonNode? n,string k)=>n?[k]?.ToString()??"";public static decimal Number(this JsonNode? n,string k)=>decimal.TryParse(n.Text(k),out var v)?v:0;public static bool Flag(this JsonNode? n,string k)=>n.Text(k)=="true";public static JsonObject Object(this JsonNode? n)=>n as JsonObject??new();public static JsonArray Array(this JsonNode? n)=>n as JsonArray??new();public static JsonNode? Copy(this JsonNode? n)=>n?.DeepClone();}
public record Download(byte[] Bytes,string Sha256,string ArchiveSha256);
public class ApexApi {
 public int SessionGeneration=1;public bool SignedIn=true;public Caps Capabilities=new();public JsonObject metadata=new();public int creates,reads,chunks,previews;public Action? afterCreate,afterChunk,afterPreview;public string CompanyPath(string c,string p)=>c+p;
 public Task<JsonNode> Send(string path,HttpMethod? method=null,JsonObject? body=null,string? key=null){
  if(path=="/api/backups/uploads"){creates++;metadata=new(){["upload_id"]="u",["byte_count"]=body!["byte_count"].Copy(),["sha256"]=body["sha256"].Copy(),["target_company_name"]=body["company_name"].Copy(),["chunk_size"]=524288,["chunk_count"]=2,["chunks"]=new JsonArray()};afterCreate?.Invoke();return Task.FromResult<JsonNode>(metadata.DeepClone());}
  if(path.EndsWith("/preview")){previews++;afterPreview?.Invoke();return Task.FromResult<JsonNode>(new JsonObject{["digest"]=metadata["sha256"].Copy()});}
  reads++;return Task.FromResult<JsonNode>(metadata.DeepClone());
 }
 public async Task<JsonNode> SendBytes(string path,HttpMethod method,byte[] part,string mime){chunks++;await Task.Yield();afterChunk?.Invoke();return new JsonObject{["index"]=int.Parse(path.Split('/').Last()),["size_bytes"]=part.Length,["received"]=true,["sha256"]=CompleteBackupTransfer.Hash(part)};}
 public Task<Download> DownloadBounded(string path,int size)=>throw new NotSupportedException();
}
}
class ChangedStream(byte[] bytes,Action callback):MemoryStream(bytes){bool changed;public override async ValueTask<int> ReadAsync(Memory<byte> buffer,CancellationToken token=default){await Task.Yield();if(!changed){changed=true;callback();}return await base.ReadAsync(buffer,token);}}
class Program{static async Task Main(){foreach(var mode in new[]{"current","hash","create","chunk","chunk-recover","preview"}){
 int epoch=0;bool allowed=true;var api=new ApexApi();void change(){epoch++;allowed=false;if(mode=="chunk-recover")allowed=true;}void guard(){if(!allowed||epoch!=0)throw new InvalidOperationException("Original owner lost");}
 if(mode=="create")api.afterCreate=change;if(mode.StartsWith("chunk"))api.afterChunk=change;if(mode=="preview")api.afterPreview=change;
 var transfer=new CompleteBackupTransfer(api,null,guard);using Stream input=mode=="hash"?new ChangedStream(new byte[600000],change):new MemoryStream(new byte[600000]);
 bool rejected=false;try{await transfer.UploadAndPreview(input,"Synthetic restored company");}catch(InvalidOperationException){rejected=true;}
 if(rejected!=(mode!="current"))throw new Exception("Wrong outcome "+mode);
 if(mode=="hash"&&api.creates!=0||mode=="create"&&(api.reads!=0||api.chunks!=0)||mode.StartsWith("chunk")&&(api.chunks!=1||api.previews!=0)||mode=="preview"&&transfer.Preview is not null||mode=="current"&&(api.chunks!=2||api.previews!=1))throw new Exception("Stale side effect "+mode);
 Console.WriteLine("PASS production upload ownership: "+mode);
}}}
'''
with tempfile.TemporaryDirectory(prefix='apex-upload-owner-') as folder:
 d=Path(folder);(d/'Program.cs').write_text(fixture, encoding="utf-8")
 includes=''.join('<Compile Include="'+str(root/'native/windows/Services'/name)+'" />' for name in ['CompleteBackupTransfer.cs','RetrySubmission.cs'])
 (d/'Proof.csproj').write_text('<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><ImplicitUsings>enable</ImplicitUsings><Nullable>enable</Nullable></PropertyGroup><ItemGroup>'+includes+'</ItemGroup></Project>', encoding="utf-8")
 subprocess.run([args.dotnet,'run','--project',str(d/'Proof.csproj')],check=True,env={**os.environ,'DOTNET_CLI_TELEMETRY_OPTOUT':'1','DOTNET_GENERATE_ASPNET_CERTIFICATE':'false','DOTNET_CLI_HOME':str(d/'home')})
