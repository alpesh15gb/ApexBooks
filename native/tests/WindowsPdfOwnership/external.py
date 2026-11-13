"""Compile actual share/print preparation with memory filesystem and fake launchers."""
from pathlib import Path
import argparse,tempfile,subprocess,os
root=Path(__file__).resolve().parents[3];p=argparse.ArgumentParser();p.add_argument('--dotnet',default='dotnet');args=p.parse_args()
share=(root/'native/windows/Services/ApexShare.cs').read_text(encoding="utf-8");share=share[share.index('    public static async Task Show('):share.rfind('\n}')]
printer=(root/'native/windows/Services/ApexPrinter.cs').read_text(encoding="utf-8");printer=printer[printer.index('    public static async Task Print('):printer.rfind('\n}')]
fixture=r'''
using System;using System.IO;using System.Linq;using System.Collections.Generic;using System.Threading.Tasks;using System.Diagnostics;
using File=MemoryFile;using Directory=MemoryDirectory;using Process=FakeProcess;
static class App{public static IntPtr WindowHandle=>IntPtr.Zero;}
static class MemoryFile{public static int Deletes;public static TaskCompletionSource Entered=new(),Release=new();public static Task WriteAllBytesAsync(string path,byte[] bytes){Entered.TrySetResult();return Release.Task;}public static void Delete(string path){Deletes++;}}
static class MemoryDirectory{public static int Deletes;public static void CreateDirectory(string path){}public static void Delete(string path){Deletes++;}}
class FakeProcess:IDisposable{public static int Launches;public static FakeProcess Start(ProcessStartInfo info){Launches++;return new();}public void Dispose(){}}
static class Share{
 SHARE
}
static class Printer{public static TaskCompletionSource<List<byte[]>> Pages=new();public static Task<List<byte[]>> Raster(byte[] bytes)=>Pages.Task;
 PRINT
}
namespace ApexBooks.NativePrinting{static class NativePrintBridge{public static int Launches;public static void Print(IReadOnlyList<byte[]> pages,string title,IntPtr handle){Launches++;}}}
static class Program{static async Task Main(){foreach(var kind in new[]{"share","print"})foreach(var stale in new[]{false,true}){
 bool current=true;Action verify=()=>{if(!current)throw new InvalidOperationException("Access changed");};FakeProcess.Launches=0;ApexBooks.NativePrinting.NativePrintBridge.Launches=0;MemoryFile.Deletes=0;MemoryDirectory.Deletes=0;MemoryFile.Entered=new();MemoryFile.Release=new();Printer.Pages=new();
 var task=kind=="share"?Share.Show(new byte[]{1},"synthetic.pdf",verify):Printer.Print(new byte[]{1},"synthetic",verify);if(kind=="share")await MemoryFile.Entered.Task;if(stale)current=false;if(kind=="share")MemoryFile.Release.SetResult();else Printer.Pages.SetResult(new List<byte[]>{new byte[]{1}});
 if(stale){try{await task;throw new Exception("Stale external launch");}catch(InvalidOperationException){}}else await task;
 if(FakeProcess.Launches+ApexBooks.NativePrinting.NativePrintBridge.Launches!=(stale?0:1))throw new Exception("Wrong external launch count");
 if(kind=="share"&&stale&&(MemoryFile.Deletes!=1||MemoryDirectory.Deletes!=1))throw new Exception("Private stale share staging retained");
 }Console.WriteLine("PASS actual share/print post-preparation checks with fake launchers (4 cases)");}}
'''.replace('SHARE',share).replace('PRINT',printer)
with tempfile.TemporaryDirectory(prefix='apex-pdf-external-') as temp:
 temp=Path(temp);(temp/'Proof.cs').write_text(fixture, encoding="utf-8");(temp/'Proof.csproj').write_text('<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><ImplicitUsings>enable</ImplicitUsings><Nullable>enable</Nullable></PropertyGroup></Project>', encoding="utf-8")
 subprocess.run([args.dotnet,'run','--project',str(temp/'Proof.csproj')],check=True,env=os.environ)
