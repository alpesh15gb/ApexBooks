using ApexBooks_Windows.Services;
using System.Net;
using System.Text;
using System.Text.Json.Nodes;

if(args.Contains("--clear-qa-session"))
{
    using var saved=new ApexApi();
    if(saved.RestoreSession()&&saved.Email=="native-release-20261101@example.invalid")
    {
        saved.ForgetSession();Console.WriteLine("Cleared only the remembered synthetic QA session on this Windows account.");
    }
    else Console.WriteLine("No synthetic QA session to clear; other account sessions were left intact.");
    return;
}

var transport=new DelayedTransport();
using var api=new ApexApi("https://apex-native-client-regression.invalid",transport);
var expired=0;api.SessionExpired+=()=>expired++;
void Check(bool condition,string name){if(!condition)throw new Exception(name);Console.WriteLine("PASS "+name);}
async Task Expect401(Task task){try{await task;throw new Exception("Expected unauthorized response");}catch(ApiFailure e)when(e.Status==401){}}
await api.Login("synthetic-qa@example.invalid","test-only-password",false);
var old=api.Send("/api/slow-records");await transport.RecordsEntered.Task;
await api.Login("synthetic-qa@example.invalid","test-only-password",false);
transport.ReleaseRecords.SetResult(true);await Expect401(old);
Check(api.SignedIn&&expired==0,"old record response cannot end a newer login");
Check(transport.RecordToken=="test-session-1","record request retains the session it started with");
await Expect401(api.Send("/api/auth/change-password",HttpMethod.Post,new JsonObject()));
Check(api.SignedIn&&expired==0,"credential challenge does not discard the sign-in session");
var pdf=api.Download("/api/slow-document.pdf");await transport.PdfEntered.Task;
await api.Login("synthetic-qa@example.invalid","test-only-password",false);
transport.ReleasePdf.SetResult(true);await Expect401(pdf);
Check(api.SignedIn&&expired==0,"old PDF response cannot end a newer login");
await Expect401(api.Send("/api/expired"));
Check(!api.SignedIn&&expired==1,"current expired session ends exactly once");

sealed class DelayedTransport:HttpMessageHandler
{
    public TaskCompletionSource<bool> RecordsEntered=new(TaskCreationOptions.RunContinuationsAsynchronously),ReleaseRecords=new(TaskCreationOptions.RunContinuationsAsynchronously),PdfEntered=new(TaskCreationOptions.RunContinuationsAsynchronously),ReleasePdf=new(TaskCreationOptions.RunContinuationsAsynchronously);
    public string? RecordToken;private int logins;
    protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request,CancellationToken cancellation)
    {
        var path=request.RequestUri!.AbsolutePath;
        if(path=="/api/auth/login")return new(HttpStatusCode.OK){Content=new StringContent("{\"token\":\"test-session-"+Interlocked.Increment(ref logins)+"\"}",Encoding.UTF8,"application/json")};
        if(path=="/api/slow-records"){RecordToken=request.Headers.Authorization?.Parameter;RecordsEntered.SetResult(true);await ReleaseRecords.Task.WaitAsync(cancellation);}
        if(path=="/api/slow-document.pdf"){PdfEntered.SetResult(true);await ReleasePdf.Task.WaitAsync(cancellation);}
        return new(HttpStatusCode.Unauthorized){Content=new StringContent("{\"detail\":\"Session rejected\"}",Encoding.UTF8,"application/json")};
    }
}
