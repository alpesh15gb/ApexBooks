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
var submission = new RetrySubmission();
var original = new JsonObject { ["amount"] = "100" };
submission.Body(original); original["amount"] = "200";
submission.Failed(new ApiFailure(0,"timeout"));
Check(submission.Unresolved && submission.Body(original).Text("amount")=="100", "uncertain write retries original payload after edits");
submission.Failed(new ApiFailure(422,"invalid"));
Check(!submission.Unresolved && submission.Body(original).Text("amount")=="200", "definitive validation permits correction");
submission.Succeeded();
Check(!submission.Unresolved,"successful write clears pending payload");
foreach(var status in new[]{0,408,409,500,502,503,504})
{
    var pending = new RetrySubmission();pending.Body(new JsonObject{["amount"]="100"});pending.Failed(new ApiFailure(status,"unknown outcome"));
    Check(pending.Unresolved && pending.Body(new JsonObject{["amount"]="999"}).Text("amount")=="100",$"unknown outcome {status} blocks discard until recovered");
    pending.Succeeded();Check(!pending.Unresolved,$"recovered outcome {status} permits dismissal");
}
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

transport.DelayLogin=true;
var cancelledLogin=api.Login("synthetic-qa@example.invalid","test-only-password",false);
await transport.LoginEntered.Task;
api.ForgetSession();
transport.ReleaseLogin.SetResult(true);
try{await cancelledLogin;throw new Exception("Expected cancelled login");}catch(OperationCanceledException){}
Check(!api.SignedIn,"signout invalidates an in-flight login response");

Check(WorkflowMasterValues.PaymentTerms(" ") is null && WorkflowMasterValues.LowStockThreshold("") is null,"blank workflow defaults disable suggestions");
Check(WorkflowMasterValues.PaymentTerms("0")!.GetValue<int>()==0&&WorkflowMasterValues.PaymentTerms("3650")!.GetValue<int>()==3650,"payment terms boundary days accepted");
Check(WorkflowMasterValues.LowStockThreshold("1.0000")!.GetValue<string>()=="1"&&WorkflowMasterValues.LowStockThreshold("0.1230")!.GetValue<string>()=="0.123","threshold accepts only mathematically equivalent trailing zeroes");
Check(WorkflowMasterValues.LowStockThreshold("0")!.GetValue<string>()=="0"&&WorkflowMasterValues.LowStockThreshold("999999999999.999")!.GetValue<string>()=="999999999999.999","threshold boundaries preserve exact decimal text");
foreach(var invalid in new[]{"-1","3651","1.5","+1","1e2","NaN"}){try{WorkflowMasterValues.PaymentTerms(invalid);throw new Exception("Invalid terms accepted");}catch(FormatException){}Check(true,$"invalid payment terms {invalid} rejected locally");}
foreach(var invalid in new[]{"-1","1000000000000","0.0001","1e2","NaN","1,000"}){try{WorkflowMasterValues.LowStockThreshold(invalid);throw new Exception("Invalid threshold accepted");}catch(FormatException){}Check(true,$"invalid threshold {invalid} rejected locally");}

Check(WorkflowMasterValues.IsActive(new JsonObject{["data"]=new JsonObject()})&&!WorkflowMasterValues.IsActive(new JsonObject{["data"]=new JsonObject{["is_active"]=false}})&&WorkflowMasterValues.IsActive(new JsonObject{["data"]=new JsonObject{["is_active"]=true}}),"legacy active and explicit archive/reactivation states");
Check(WorkflowMasterValues.ShippingAddress(new JsonObject{["address"]="Billing"})=="Billing"&&WorkflowMasterValues.ShippingAddress(new JsonObject{["address"]="Billing",["shipping_address"]="Delivery"})=="Delivery","saved shipping default or billing fallback");

Check(WorkflowMasterValues.CreditLimit(" ") is null&&WorkflowMasterValues.CreditLimit("0")!.GetValue<string>()=="0","credit limits distinguish disabled from zero");
Check(WorkflowMasterValues.CreditLimit("9999999999999.99")!.GetValue<string>()=="9999999999999.99"&&WorkflowMasterValues.CreditLimit("12.3400")!.GetValue<string>()=="12.34","credit limits enforce maximum and normalize meaningful decimals");
foreach(var invalid in new[]{"-1","10000000000000","0.001","NaN","1e2","1,000"}){try{WorkflowMasterValues.CreditLimit(invalid);throw new Exception("Invalid credit limit accepted");}catch(FormatException){}Check(true,$"invalid credit limit {invalid} rejected locally");}
Check(new[]{"sales_invoice","estimate","proforma","sales_order"}.All(k=>WorkflowMasterValues.CreditProjectionApplies(k,false))&&!WorkflowMasterValues.CreditProjectionApplies("sales_invoice",true)&&!WorkflowMasterValues.CreditProjectionApplies("pos",false)&&!WorkflowMasterValues.CreditProjectionApplies("purchase_bill",false),"credit projections limited to new customer invoices and drafts, not amendments or paid POS");
Check(WorkflowMasterValues.CreditStatusText(new JsonObject{["as_of"]="2026-11-02",["current_exposure"]="100"},false).Contains("Current exposure"),"party exposure remains visible with disabled credit limit");
var creditMessage=WorkflowMasterValues.CreditStatusText(new JsonObject{["as_of"]="2026-11-02",["credit_limit"]="0",["current_exposure"]="0",["proposed_amount"]="100",["projected_exposure"]="100",["remaining_credit"]="-100",["exceeded"]=true},true);
Check(creditMessage.Contains("2026-11-02")&&creditMessage.Contains("Credit limit exceeded")&&creditMessage.Contains("saving is not blocked")&&creditMessage.Contains("not credit approval"),"credit warning labels as-of, exceeded state and nonblocking meaning");

Check(WorkflowMasterValues.RecurringInterval("1")==1&&WorkflowMasterValues.RecurringInterval("12")==12,"recurring interval boundaries accepted");
foreach(var invalid in new[]{"0","13","-1","1.5","","1e1"}){try{WorkflowMasterValues.RecurringInterval(invalid);throw new Exception("Invalid recurring interval accepted");}catch(FormatException){}Check(true,$"invalid recurring interval {invalid} rejected");}
Check(WorkflowMasterValues.RecurringOccurrenceAllowed(true,"2026-11-02","2026-11-02")&&WorkflowMasterValues.RecurringOccurrenceAllowed(true,"2026-10-31","2026-11-02")&&!WorkflowMasterValues.RecurringOccurrenceAllowed(false,"2026-10-31","2026-11-02")&&!WorkflowMasterValues.RecurringOccurrenceAllowed(true,"2026-11-03","2026-11-02")&&!WorkflowMasterValues.RecurringOccurrenceAllowed(true,"","2026-11-02"),"recurring generation only active due or overdue dates, never paused/future/completed");
Check(WorkflowMasterValues.RecurringOccurrenceAllowed(true,"2026-11-03","2026-11-03")&&!WorkflowMasterValues.RecurringOccurrenceAllowed(true,"2026-11-03","2026-11-02")&&!WorkflowMasterValues.RecurringOccurrenceAllowed(true,"2026-11-03",""),"recurring eligibility follows supplied server business date and fails closed without it");
var recurringRetry=new RetrySubmission();recurringRetry.Body(new JsonObject{["occurrence_date"]="2026-10-31"});WorkflowMasterValues.RecurringWriteFailed(recurringRetry,new ApiFailure(0,"timeout"));Check(recurringRetry.Unresolved&&recurringRetry.Body(new JsonObject{["occurrence_date"]="2026-11-30"}).Text("occurrence_date")=="2026-10-31","uncertain recurring write retains original occurrence date");WorkflowMasterValues.RecurringWriteFailed(recurringRetry,new ApiFailure(409,"definitive stale version"));Check(!recurringRetry.Unresolved,"recurring API definitive conflict permits close and reload");

var unsupported=ClientCapabilities.Parse(new JsonObject{["capabilities_version"]=2,["supported_features"]=new JsonArray("party_credit_limits")});
Check(!unsupported.Supports("party_credit_limits")&&!ClientCapabilities.Parse(null).Supports("recurring_drafts")&&!ClientCapabilities.Parse(new JsonObject{["capabilities_version"]="1",["supported_features"]=new JsonArray("recurring_drafts")}).Supports("recurring_drafts"),"missing or unknown capability versions fail closed");
var supported=ClientCapabilities.Parse(new JsonObject{["capabilities_version"]=1,["supported_features"]=new JsonArray("party_credit_limits","party_shipping_address","company_book_labels","unknown_future_feature")});
Check(supported.Supports("party_credit_limits")&&!supported.Supports("party_payment_terms")&&!supported.Supports("unknown_future_feature"),"only advertised known features are enabled");
var masterMetadata=new JsonObject{["phone"]="123",["credit_limit"]="0",["shipping_address"]="Delivery",["is_active"]=false,["payment_terms_days"]=30,["low_stock_threshold"]="10"};var filtered=supported.MasterData(masterMetadata);
Check(filtered.ContainsKey("credit_limit")&&filtered.ContainsKey("shipping_address")&&!filtered.ContainsKey("is_active")&&!filtered.ContainsKey("payment_terms_days")&&!filtered.ContainsKey("low_stock_threshold")&&filtered["phone"]!.GetValue<string>()=="123"&&masterMetadata.ContainsKey("is_active"),"unsupported master metadata omitted without mutating draft or core fields");
ClientCapabilities.Unavailable.RequireMasterEditsSupported(new JsonObject(),new JsonObject{["is_active"]=true,["credit_limit"]=""});Check(true,"legacy untouched master defaults remain savable");
try{ClientCapabilities.Unavailable.RequireMasterEditsSupported(new JsonObject(),new JsonObject{["credit_limit"]="0"});throw new Exception("Unsupported credit input silently discarded");}catch(InvalidOperationException){}Check(true,"changed unsupported master input rejected rather than silently dropped");
try{ClientCapabilities.Unavailable.RequireBookLabelSupported("","Entered label");throw new Exception("Unsupported label silently discarded");}catch(InvalidOperationException){}Check(true,"changed unsupported book label rejected rather than silently dropped");
Check(ClientCapabilities.CompanyLabel(new JsonObject{["name"]="Legal Name",["book_label"]="Retail"})=="Legal Name · Retail"&&ClientCapabilities.CompanyLabel(new JsonObject{["name"]="Legal Name"})=="Legal Name","company labels supplement rather than replace legal names");
Check(ClientCapabilities.BookLabel(new string('x',80)).Length==80,"book label maximum length accepted");try{ClientCapabilities.BookLabel(new string('x',81));throw new Exception("Overlong label accepted");}catch(FormatException){}Check(true,"overlong book label rejected");
Check(BusinessCalendar.IndiaDate(DateTimeOffset.Parse("2026-12-31T18:30:00Z"))==new DateTime(2027,1,1)&&BusinessCalendar.IndiaDate(DateTimeOffset.Parse("2026-12-31T18:29:59Z"))==new DateTime(2026,12,31),"default business date follows IST midnight independent of device timezone");
Check(BusinessCalendar.FinancialStart(DateTimeOffset.Parse("2026-03-31T18:29:59Z"))=="2025-04-01"&&BusinessCalendar.FinancialStart(DateTimeOffset.Parse("2026-03-31T18:30:00Z"))=="2026-04-01","financial year changes at IST April1 boundary");
var capabilityTransport=new CapabilityTransport();using(var client=new ApexApi("https://synthetic-capabilities.invalid",capabilityTransport)){
 await client.Login("metadata@example.invalid","synthetic",false);await Task.WhenAll(Enumerable.Range(0,10).Select(_=>client.EnsureCapabilities()));Check(capabilityTransport.CapabilityCalls==1&&!capabilityTransport.SentAuthorization&&client.Capabilities.Supports("party_credit_limits"),"public capabilities requested once across concurrent callers per session");
 await client.Login("metadata@example.invalid","synthetic",false);Check(!client.Capabilities.Supports("party_credit_limits"),"new session immediately invalidates old capabilities");await client.EnsureCapabilities();Check(capabilityTransport.CapabilityCalls==2,"new sign-in refreshes capabilities once");client.ForgetSession();Check(!client.Capabilities.Supports("party_credit_limits"),"signout clears capability state");
}

var staleMetadata=new CapabilityTransport{Hold=true};using(var client=new ApexApi("https://synthetic-stale-metadata.invalid",staleMetadata)){
 await client.Login("metadata@example.invalid","synthetic",false);var pending=client.EnsureCapabilities();await staleMetadata.Entered.Task;client.ForgetSession();staleMetadata.Release.SetResult(true);await pending;Check(!client.Capabilities.Supports("party_credit_limits"),"late capability response cannot restore state after signout");
}

foreach(var failure in new[]{"network","timeout","503","404","invalid"}){
 var transient=new CapabilityTransport{Failure=failure};using var client=new ApexApi("https://synthetic-retry.invalid",transient);await client.Login("metadata@example.invalid","synthetic",false);await client.EnsureCapabilities();var retryable=failure is "network" or "timeout" or "503";
 Check(client.Capabilities.Retryable==retryable&&!client.Capabilities.Supports("party_credit_limits"),$"capability {failure} is classified and fails closed");await client.EnsureCapabilities();Check(transient.CapabilityCalls==1,$"capability {failure} does not automatically refetch");
 transient.Failure="";await Task.WhenAll(Enumerable.Range(0,10).Select(_=>client.RetryCapabilities()));Check(transient.CapabilityCalls==(retryable?2:1)&&client.Capabilities.Supports("party_credit_limits")==retryable,$"explicit capability retry {failure} is deduplicated and recovers only transient failures");
}

var staleRetry=new CapabilityTransport{Failure="network"};using(var client=new ApexApi("https://synthetic-stale-retry.invalid",staleRetry)){
 await client.Login("metadata@example.invalid","synthetic",false);await client.EnsureCapabilities();staleRetry.Failure="";staleRetry.Hold=true;var retry=client.RetryCapabilities();await staleRetry.Entered.Task;client.ForgetSession();staleRetry.Release.SetResult(true);await retry;Check(!client.Capabilities.Valid&&!client.Capabilities.Retryable,"late explicit capability retry cannot restore metadata after signout");
}

var paging=new PagingTransport();using var pagingApi=new ApexApi("https://synthetic-paging.invalid",paging);
var timer=System.Diagnostics.Stopwatch.StartNew();for(var offset=0;offset<1250;offset+=100)await pagingApi.Send(pagingApi.CompanyPath("test",$"/records?compact=true&limit=100&offset={offset}"));var baselineMs=timer.ElapsedMilliseconds;
Check(paging.Calls==13,"baseline 1250 records uses 13 small-page requests");paging.Calls=0;timer.Restart();var allRows=await pagingApi.Records("test");var improvedMs=timer.ElapsedMilliseconds;
Check(paging.Calls==3&&allRows.Count==1250&&allRows.Select(r=>r.Text("id")).Distinct().Count()==1250,"company load returns all1250 unique records in3 compact requests");
Console.WriteLine($"COMPANY_LOAD_SYNTHETIC rows=1250 latency=20ms old_requests=13 new_requests=3 old_ms={baselineMs} new_ms={improvedMs}");

sealed class PagingTransport:HttpMessageHandler
{
    public int Calls;
    protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request,CancellationToken cancellation)
    {
        Calls++;await Task.Delay(20,cancellation);var query=request.RequestUri!.Query.TrimStart('?').Split('&').Select(p=>p.Split('=')).ToDictionary(p=>p[0],p=>p[1]);
        var offset=int.Parse(query["offset"]);var limit=int.Parse(query["limit"]);var rows=new JsonArray();for(var i=offset;i<Math.Min(offset+limit,1250);i++)rows.Add(new JsonObject{["id"]=$"row-{i}",["kind"]="party",["name"]=$"Synthetic {i}"});
        return new(HttpStatusCode.OK){Content=new StringContent(rows.ToJsonString(),Encoding.UTF8,"application/json")};
    }
}

sealed class DelayedTransport:HttpMessageHandler
{
    public TaskCompletionSource<bool> RecordsEntered=new(TaskCreationOptions.RunContinuationsAsynchronously),ReleaseRecords=new(TaskCreationOptions.RunContinuationsAsynchronously),PdfEntered=new(TaskCreationOptions.RunContinuationsAsynchronously),ReleasePdf=new(TaskCreationOptions.RunContinuationsAsynchronously);
    public bool DelayLogin;
    public TaskCompletionSource<bool> LoginEntered=new(TaskCreationOptions.RunContinuationsAsynchronously),ReleaseLogin=new(TaskCreationOptions.RunContinuationsAsynchronously);
    public string? RecordToken;private int logins;
    protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request,CancellationToken cancellation)
    {
        var path=request.RequestUri!.AbsolutePath;
        if(path=="/api/auth/login"&&DelayLogin){LoginEntered.SetResult(true);await ReleaseLogin.Task.WaitAsync(cancellation);}
        if(path=="/api/auth/login")return new(HttpStatusCode.OK){Content=new StringContent("{\"token\":\"test-session-"+Interlocked.Increment(ref logins)+"\"}",Encoding.UTF8,"application/json")};
        if(path=="/api/slow-records"){RecordToken=request.Headers.Authorization?.Parameter;RecordsEntered.SetResult(true);await ReleaseRecords.Task.WaitAsync(cancellation);}
        if(path=="/api/slow-document.pdf"){PdfEntered.SetResult(true);await ReleasePdf.Task.WaitAsync(cancellation);}
        return new(HttpStatusCode.Unauthorized){Content=new StringContent("{\"detail\":\"Session rejected\"}",Encoding.UTF8,"application/json")};
    }
}

sealed class CapabilityTransport:HttpMessageHandler
{
 public string Failure="";public int CapabilityCalls;public bool SentAuthorization,Hold;public TaskCompletionSource<bool> Entered=new(TaskCreationOptions.RunContinuationsAsynchronously),Release=new(TaskCreationOptions.RunContinuationsAsynchronously);
 protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request,CancellationToken cancellation){
  if(request.RequestUri!.AbsolutePath=="/api/capabilities"){Interlocked.Increment(ref CapabilityCalls);SentAuthorization|=request.Headers.Authorization is not null;if(Hold){Entered.SetResult(true);await Release.Task.WaitAsync(cancellation);}await Task.Delay(20,cancellation);if(Failure=="network")throw new HttpRequestException("synthetic offline");if(Failure=="timeout")throw new TaskCanceledException("synthetic timeout");if(Failure is "503" or "404")return new((HttpStatusCode)int.Parse(Failure)){Content=new StringContent("{}")};if(Failure=="invalid")return new(HttpStatusCode.OK){Content=new StringContent("not json")};return new(HttpStatusCode.OK){Content=new StringContent("{\"capabilities_version\":1,\"supported_features\":[\"party_credit_limits\"]}")};}
  return new(HttpStatusCode.OK){Content=new StringContent("{\"token\":\"synthetic-metadata-session\"}")};
 }
}
