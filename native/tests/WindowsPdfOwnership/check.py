"""Compile actual retained PDF preview method with synthetic WinUI/rendering boundaries."""
from pathlib import Path
import argparse,tempfile,subprocess,os
root=Path(__file__).resolve().parents[3];p=argparse.ArgumentParser();p.add_argument('--dotnet',default='dotnet');p.add_argument('--baseline');args=p.parse_args()
s=subprocess.check_output(['git','show',args.baseline+':native/windows/Views/Reporting.cs'],cwd=root,text=True) if args.baseline else (root/'native/windows/Views/Reporting.cs').read_text();method=s[s.index('    private async Task ShowPdf('):s.rfind('\n}')]
fixture=r'''
using System;using System.IO;using System.Linq;using System.Collections.Generic;using System.Threading;using System.Threading.Tasks;using System.Text.Json.Nodes;using ApexBooks_Windows.Services;
class Control{public bool IsEnabled=true;}
class Panel:Control{public List<object> Children=new();public double MinWidth;public Orientation Orientation;public int Spacing;}
class StackPanel:Panel{}
enum Orientation{Horizontal}enum Stretch{Uniform}
class Image:Control{public object? Source;public int Width;public Stretch Stretch;}
class Caption:Control{public string Text="";}
class Button:Control{public string Name="";public Func<Task> Action=()=>Task.CompletedTask;public Task Click()=>Action();}
class Combo:Control{int selected;public int SelectedIndex{get=>selected;set{selected=value;SelectionChanged?.Invoke(this,EventArgs.Empty);}}public event EventHandler? SelectionChanged;}
class InMemoryRandomAccessStream:IDisposable{public void Seek(int n){}public void Dispose(){}}
class DataWriter:IDisposable{public DataWriter(object stream){}public void WriteBytes(byte[] bytes){}public Task StoreAsync()=>Task.CompletedTask;public void DetachStream(){}public void Dispose(){}}
class BitmapImage{public Task SetSourceAsync(object stream)=>Task.CompletedTask;}
static class J{public static string Text(this JsonNode node,string key)=>node[key]?.ToString()??"";}
static class ApexPrinter{public static int Prints;public static Task<int> PageCount(byte[] bytes)=>Task.FromResult(1);public static Task<List<byte[]>> Raster(byte[] bytes,uint width,int page)=>Task.FromResult(new List<byte[]>{bytes});public static Task Print(byte[] bytes,string name,Action? verify=null){verify?.Invoke();Prints++;return Task.CompletedTask;}}
static class ApexShare{public static int Shares;public static Task Show(byte[] bytes,string name,Action? verify=null){verify?.Invoke();Shares++;return Task.CompletedTask;}}
static class ApexFiles{public static int Saves;public static byte[]? Bytes;public static Task<bool> Save(byte[] bytes,string name,Action? verify=null){verify?.Invoke();Saves++;Bytes=bytes;return Task.FromResult(true);}}
class ApiStub{public TaskCompletionSource<byte[]> Pending=new();public Task<byte[]> Download(string path)=>Pending.Task;public string CompanyPath(string id,string path)=>id+path;}
class Model{
 public string CompanyId="a";public int generation;public int epoch;public ApiStub Api=new();public event Action? ReadAccessInvalidated;public Panel? OpenPanel;public TaskCompletionSource Opened=new(),Closed=new();public string ErrorText="";
 Action CaptureFileSaveAccess(){var captured=epoch;return()=>{if(captured!=epoch)throw new InvalidOperationException("Access changed");};}
 Panel Stack()=>new();Caption Text(string text)=>new(){Text=text};Button AsyncButton(string name,Func<Task> action,Action<Exception> error)=>new(){Name=name,Action=action};Button Button(string name,Action action)=>new(){Name=name,Action=()=>{action();return Task.CompletedTask;}};Combo Select(string title,(string,string)[] values)=>new();string Value(Combo combo)=>combo.SelectedIndex.ToString();void Error(Exception e){ErrorText=e.Message;}
 async Task Dialog(string title,Panel panel,Func<Task> action,string button){OpenPanel=panel;Opened.SetResult();await Closed.Task;}void CloseDialog()=>Closed.TrySetResult();
 public void Deny(){epoch++;ReadAccessInvalidated?.Invoke();}public Task Open()=>ShowPdf(new byte[]{1},"synthetic.pdf",new JsonObject{["id"]="r1"});
 METHOD
}
class AsyncEvents:SynchronizationContext{public TaskCompletionSource Done=new(TaskCreationOptions.RunContinuationsAsynchronously);public override void OperationCompleted()=>Done.TrySetResult();public override void Post(SendOrPostCallback callback,object? state)=>ThreadPool.QueueUserWorkItem(_=>callback(state));}
static class Program{static Button Find(Model m,string name)=>m.OpenPanel!.Children.OfType<StackPanel>().SelectMany(p=>p.Children).OfType<Button>().Single(b=>b.Name==name);
 static async Task Main(){
  foreach(var stale in new[]{false,true}){ApexFiles.Saves=0;var m=new Model();var open=m.Open();await m.Opened.Task;var save=Find(m,"Save PDF");var image=m.OpenPanel!.Children.OfType<Image>().Single();if(stale){m.Deny();if(image.Source!=null||!m.OpenPanel.Children.OfType<Caption>().Any(c=>c.Text.Contains("access removed")))throw new Exception("Retained PDF not cleared");}await save.Click();if(ApexFiles.Saves!=(stale?0:1))throw new Exception("Stale PDF saved");m.Closed.SetResult();await open;}
  foreach(var outcome in new[]{"success","failure","denied","closed"}){ApexFiles.Saves=0;var m=new Model();var open=m.Open();await m.Opened.Task;var combo=m.OpenPanel!.Children.OfType<Combo>().Single();var save=Find(m,"Save PDF");var events=new AsyncEvents();SynchronizationContext.SetSynchronizationContext(events);combo.SelectedIndex=2;SynchronizationContext.SetSynchronizationContext(null);if(save.IsEnabled)throw new Exception("Format load left save enabled");if(outcome=="denied")m.Deny();if(outcome=="closed"){m.Closed.SetResult();await open;}if(outcome=="failure")m.Api.Pending.SetException(new IOException("format failed"));else m.Api.Pending.SetResult(new byte[]{2});await events.Done.Task.WaitAsync(TimeSpan.FromSeconds(5));if(outcome=="failure"&&(combo.SelectedIndex!=0||m.ErrorText!="format failed"))throw new Exception("Format failure label mismatch");if(outcome is "success" or "failure"){await save.Click();if(ApexFiles.Bytes![0]!=(outcome=="success"?2:1))throw new Exception("Format/bytes mismatch");}else if(ApexFiles.Saves!=0||m.ErrorText!="")throw new Exception("Stale format side effect");if(outcome!="closed"){m.Closed.SetResult();await open;}else {await save.Click();if(ApexFiles.Saves!=0)throw new Exception("Closed preview saved retained bytes");}}
  Console.WriteLine("PASS actual retained PDF denial, format failure/retry ownership and closed-preview cases (6)");
 }
}
'''.replace('METHOD',method)
with tempfile.TemporaryDirectory(prefix='apex-pdf-ownership-') as temp:
 temp=Path(temp);(temp/'Proof.cs').write_text(fixture);(temp/'ScopedFileExport.cs').write_text((root/'native/windows/Services/ScopedFileExport.cs').read_text());(temp/'Proof.csproj').write_text('<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><ImplicitUsings>enable</ImplicitUsings><Nullable>enable</Nullable></PropertyGroup></Project>')
 subprocess.run([args.dotnet,'run','--project',str(temp/'Proof.csproj')],check=True,env=os.environ)
