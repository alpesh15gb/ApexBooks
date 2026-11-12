using System.Net;
using System.Text;
using System.Text.Json.Nodes;
using ApexBooks_Windows.Services;

static class ResponseSessionRegression
{
 public static async Task Run()
 {
  foreach(var route in new[]{"json","download","upload","bounded"})
  foreach(var delay in new[]{"headers","body"})
  foreach(var change in new[]{"same","logout","replacement","replacement-same-token"})
  {
   using var transport=new SuccessfulDelayedTransport(delay=="body",change=="replacement-same-token");using var api=new ApexApi("https://session-response.invalid",transport);
   await api.Login("first@example.invalid","synthetic",false);
   Task work=route switch {
    "json"=>api.Send("/api/held",HttpMethod.Post,new JsonObject{["amount"]="100"},"same-retry-key"),
    "download"=>api.Download("/api/held"),
    "upload"=>api.SendBytes("/api/held",HttpMethod.Post,new byte[]{1},"application/octet-stream"),
    _=>api.DownloadBounded("/api/held",100)
   };
   await transport.Entered.Task;
   if(change=="logout")api.ForgetSession();
   if(change.StartsWith("replacement"))await api.Login("second@example.invalid","synthetic",false);
   transport.Release.SetResult(true);
   if(change=="same")await work;
   else {try {await work;throw new Exception($"Stale successful {route} response escaped after {change} at {delay}");}catch(ApiFailure error)when(error.Status==0){}}
   if(api.SignedIn!=(change!="logout"))throw new Exception("Response changed current sign-in");
   if(transport.HeldWrites!=1)throw new Exception("Unexpected duplicate request");
  }
  foreach(var scenario in new[]{"logout","401"}){
   using var transport=new SuccessfulDelayedTransport(false,true,scenario=="401"?HttpStatusCode.Unauthorized:HttpStatusCode.OK);using var api=new ApexApi("https://session-response.invalid",transport);
   await api.Login("first@example.invalid","synthetic",false);int expired=0;api.SessionExpired+=()=>expired++;
   var pending=scenario=="logout"?api.Logout():api.Send("/api/held");await transport.Entered.Task;
   await api.Login("second@example.invalid","synthetic",false);transport.Release.SetResult(true);
   try{await pending;}catch(ApiFailure error)when(error.Status==(scenario=="logout"?0:401)){}
   if(!api.SignedIn||api.Email!="second@example.invalid"||expired!=0)throw new Exception($"Old {scenario} cleared same-token replacement session");
  }
  Console.WriteLine("PASS same-token replacement survives old logout and 401");
  Console.WriteLine("PASS successful JSON/file/upload/bounded responses retain session ownership (32 cases)");
 }
 sealed class HeldStream(byte[] bytes,TaskCompletionSource<bool> entered,TaskCompletionSource<bool> release):MemoryStream(bytes)
 {
  public override async ValueTask<int> ReadAsync(Memory<byte> buffer,CancellationToken cancellation=default){entered.TrySetResult(true);await release.Task.WaitAsync(cancellation);return await base.ReadAsync(buffer,cancellation);}
  public override async Task<int> ReadAsync(byte[] buffer,int offset,int count,CancellationToken cancellation){entered.TrySetResult(true);await release.Task.WaitAsync(cancellation);return await base.ReadAsync(buffer,offset,count,cancellation);}
  public override async Task CopyToAsync(Stream destination,int bufferSize,CancellationToken cancellation){entered.TrySetResult(true);await release.Task.WaitAsync(cancellation);await base.CopyToAsync(destination,bufferSize,cancellation);}
 }
 sealed class SuccessfulDelayedTransport(bool bodyDelay,bool repeatToken,HttpStatusCode status=HttpStatusCode.OK):HttpMessageHandler
 {
  public TaskCompletionSource<bool> Entered=new(TaskCreationOptions.RunContinuationsAsynchronously),Release=new(TaskCreationOptions.RunContinuationsAsynchronously);
  public int HeldWrites;int logins;
  protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request,CancellationToken cancellation)
  {
   if(request.RequestUri!.AbsolutePath=="/api/auth/login")return new(HttpStatusCode.OK){Content=new StringContent("{\"token\":\"synthetic-"+(repeatToken?1:++logins)+"\"}")};
   HeldWrites++;
   if(bodyDelay)return new(HttpStatusCode.OK){Content=new StreamContent(new HeldStream(Encoding.UTF8.GetBytes("{\"value\":\"private\"}"),Entered,Release))};
   Entered.TrySetResult(true);await Release.Task.WaitAsync(cancellation);
   return new(status){Content=new StringContent("{\"value\":\"private\"}",Encoding.UTF8,"application/json")};
  }
 }
}
