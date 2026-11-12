using ApexBooks_Windows.Services;
static class FileExportRegression
{
 public static async Task Run()
 {
  foreach(var stage in new[]{"fetch","transform"})foreach(var outcome in new[]{"current","stale","current-error","stale-error","cancel"}){
   var current=true;Action verify=()=>{if(!current)throw new InvalidOperationException("Changed workspace");};var fetch=new TaskCompletionSource<byte[]>();var transform=new TaskCompletionSource<byte[]>();var entered=new TaskCompletionSource();var saves=0;
   var task=ScopedFileExport.Download(verify,()=>fetch.Task,async bytes=>{entered.SetResult();return await transform.Task;},(bytes,guard)=>{guard();saves++;return Task.FromResult(outcome!="cancel");});
   if(stage=="transform"){fetch.SetResult(new byte[]{1});await entered.Task;}
   if(outcome.StartsWith("stale"))current=false;
   var target=stage=="fetch"?fetch:transform;
   if(outcome.EndsWith("error"))target.SetException(new IOException("Synthetic failure"));else target.SetResult(new byte[]{2});
   if(stage=="fetch"&&outcome is "current" or "cancel"){await entered.Task;transform.SetResult(new byte[]{3});}
   if(outcome=="current-error"){try{await task;throw new Exception("Current failure hidden");}catch(IOException){}}
   else {var result=await task;if(result!=(outcome.StartsWith("stale")?null:outcome!="cancel"))throw new Exception("Wrong export outcome");}
   if(saves!=(outcome is "current" or "cancel"?1:0))throw new Exception("Unexpected file side effect");
  }
  {int reads=0;var result=await ScopedFileExport.Download(()=>throw new InvalidOperationException(),()=>{reads++;return Task.FromResult(new byte[]{1});},null,(_,_)=>Task.FromResult(true));if(reads!=0||result is not null)throw new Exception("Stale export dispatched");}
  Console.WriteLine("PASS original-context export fetch/transform success, failure, cancellation and stale-entry (11 cases)");
 }
}
