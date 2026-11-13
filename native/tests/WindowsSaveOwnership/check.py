"""Compile actual Windows file-save methods with synthetic picker/storage types."""
from pathlib import Path
import argparse,subprocess,tempfile,os
root=Path(__file__).resolve().parents[3]
p=argparse.ArgumentParser();p.add_argument('--dotnet',default='dotnet');args=p.parse_args()
s=(root/'native/windows/Services/ApexFiles.cs').read_text(encoding="utf-8");methods=s[s.index('    public static async Task<bool> Save('):s.index('    public static async Task<byte[]> Read(')]
app=(root/'native/windows/MainPage.xaml.cs').read_text(encoding="utf-8");wiring=app[app.index('    private Action CaptureFileSaveAccess()'):app.index('    private Action CaptureOwnerImportAccess()')]
assert 'ApexFiles.CaptureSaveAccess=CaptureFileSaveAccess;' in app
assert 'saveAccessEpoch++;Records=new();Banks=new();recordsReady=false;' in app
fixture=r'''
using System;
using System.IO;
using System.Linq;
using System.Collections.Generic;
using System.Threading.Tasks;
using Windows.Storage;
using Windows.Storage.Pickers;
static class App {public static IntPtr WindowHandle=>IntPtr.Zero;}
static class ApexFiles {
 public static Func<Action>? CaptureSaveAccess;
 METHODS
}
class ApiStub{public bool SignedIn=true;public int SessionGeneration;}
class Model{public ApiStub Api=new();public string CompanyId="a";public int workspaceGeneration,saveAccessEpoch;public bool recordsReady=true;
 WIRING
 public Action Capture()=>CaptureFileSaveAccess();
}
static class Program {
 static async Task Main(){
  foreach(var kind in new[]{"bytes","stream"})foreach(var stale in new[]{false,true}){
   var epoch=0;ApexFiles.CaptureSaveAccess=()=>{var stamp=epoch;return()=>{if(stamp!=epoch)throw new InvalidOperationException("Workspace changed");};};
   FileSavePicker.Pending=new();var file=new StorageFile();using var input=new MemoryStream(new byte[]{1,2,3});
   var pending=kind=="bytes"?ApexFiles.Save(new byte[]{1,2,3},"test.bin"):ApexFiles.SaveStream(input,"test.bin");
   if(stale)epoch++;FileSavePicker.Pending.SetResult(file);
   if(stale){try{await pending;throw new Exception("Stale picker wrote "+kind);}catch(InvalidOperationException){if(file.Writes!=0||file.Opens!=0||file.Deleted)throw new Exception("Stale save touched destination");}}
   else if(!await pending||!file.Data.ToArray().SequenceEqual(new byte[]{1,2,3}))throw new Exception("Current save failed");
  }
  foreach(var change in new[]{"none","session","company","workspace","denied","recovered","signed-out"}){
   var model=new Model();var verify=model.Capture();switch(change){case "session":model.Api.SessionGeneration++;break;case "company":model.CompanyId="b";break;case "workspace":model.workspaceGeneration++;break;case "denied":model.recordsReady=false;break;case "recovered":model.saveAccessEpoch++;break;case "signed-out":model.Api.SignedIn=false;break;}
   bool rejected=false;try{verify();}catch(InvalidOperationException){rejected=true;}if(rejected==(change=="none"))throw new Exception("Incorrect scope: "+change);
  }
  foreach(var kind in new[]{"bytes","stream"}){ApexFiles.CaptureSaveAccess=()=>()=>{};FileSavePicker.Pending=new();using var input=new MemoryStream();var pending=kind=="bytes"?ApexFiles.Save(new byte[]{1},"x.bin"):ApexFiles.SaveStream(input,"x.bin");FileSavePicker.Pending.SetResult(null);if(await pending)throw new Exception("Cancellation reported saved");}
  {var epoch=0;ApexFiles.CaptureSaveAccess=()=>{var stamp=epoch;return()=>{if(epoch!=stamp)throw new InvalidOperationException();};};FileSavePicker.Pending=new();var file=new StorageFile{OnOpen=()=>epoch++};file.Data.WriteByte(9);using var input=new MemoryStream(new byte[]{1});var pending=ApexFiles.SaveStream(input,"x.bin");FileSavePicker.Pending.SetResult(file);try{await pending;throw new Exception("Stale open accepted");}catch(InvalidOperationException){}if(file.Deleted||!file.Data.ToArray().SequenceEqual(new byte[]{9}))throw new Exception("Stale open damaged selected file");}
  Console.WriteLine("PASS actual MainPage ownership capture, cancellation and delayed-open preservation");
  Console.WriteLine("PASS actual Windows byte/stream picker ownership");
 }
}
namespace Windows.Storage {
 class StorageFile {public Action? OnOpen;public int Opens,Writes;public bool Deleted;public MemoryStream Data=new();public Task<Stream> OpenStreamForWriteAsync(){Opens++;OnOpen?.Invoke();return Task.FromResult<Stream>(Data);}public Task DeleteAsync(){Deleted=true;return Task.CompletedTask;}}
 static class FileIO {public static Task WriteBytesAsync(StorageFile file,byte[] bytes){file.Writes++;file.Data.Write(bytes);return Task.CompletedTask;}}
}
namespace Windows.Storage.Pickers {
 class FileSavePicker {public static TaskCompletionSource<StorageFile?> Pending=new();public string SuggestedFileName{get;set;}="";public Dictionary<string,List<string>> FileTypeChoices=new();public Task<StorageFile?> PickSaveFileAsync()=>Pending.Task;}
}
namespace WinRT.Interop {static class InitializeWithWindow{public static void Initialize(object picker,IntPtr handle){}}}
'''.replace('METHODS',methods).replace('WIRING',wiring)
with tempfile.TemporaryDirectory(prefix='apex-windows-save-') as temp:
 temp=Path(temp);(temp/'Proof.cs').write_text(fixture, encoding="utf-8");(temp/'Proof.csproj').write_text('<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><ImplicitUsings>enable</ImplicitUsings><Nullable>enable</Nullable></PropertyGroup></Project>', encoding="utf-8")
 subprocess.run([args.dotnet,'run','--project',str(temp/'Proof.csproj')],check=True,env=os.environ)
