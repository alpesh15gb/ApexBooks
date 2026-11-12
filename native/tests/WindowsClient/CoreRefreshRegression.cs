using ApexBooks_Windows.Services;
static class CoreRefreshRegression
{
 public static async Task Run()
 {
  foreach(var mode in new[]{"mixed","transient","stale-core","navigation","stale-navigation","success"}){
   var a=new TaskCompletionSource<int>();var b=new TaskCompletionSource<int>();var nav=new TaskCompletionSource();bool current=true,invalid=false,published=false;Exception? error=null;
   var work=ScopedCoreRefresh.Run(a.Task,b.Task,()=>current,()=>invalid=true,(x,y)=>published=true,()=>nav.Task);
   if(mode=="stale-core")current=false;
   if(mode is "mixed" or "transient" or "stale-core"){
    a.SetException(new ApiFailure(503,"synthetic transient"));b.SetException(new ApiFailure(mode=="transient"?503:404,"synthetic denial"));
   }else{a.SetResult(1);b.SetResult(2);if(mode=="stale-navigation")current=false;if(mode=="success")nav.SetResult();else nav.SetException(new ApiFailure(404,"synthetic navigation"));}
   try{await work;}catch(Exception e){error=e;}
   if(invalid!=(mode=="mixed")||published!=(mode is "navigation" or "stale-navigation" or "success"))throw new Exception("Refresh cache/draft boundary: "+mode);
   if((error!=null)!=(mode is "mixed" or "transient" or "navigation"))throw new Exception("Refresh error boundary: "+mode);
  }
  Console.WriteLine("PASS scoped refresh mixed denial, transient, stale core/navigation, current navigation and successful publish");
 }
}
