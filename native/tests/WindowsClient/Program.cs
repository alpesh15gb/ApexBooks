using System.Security.Cryptography;
using ApexBooks_Windows.Services;
using System.Net;
using System.Text;
using System.Text.Json.Nodes;

CsvRegression.Run();

var returnRows=new JsonArray(new JsonObject{["quantity"]="2",["rate"]="100",["discount_amount"]="7",["return_capacity_scope"]="additional_returns",["remaining_return_quantity"]="1"},new JsonObject{["quantity"]="2",["return_capacity_scope"]="additional_returns",["remaining_return_quantity"]="0"},new JsonObject{["quantity"]="2"});
var returnDraft=SourceLineChoices.DraftLines(returnRows);
if(returnDraft.Count!=2||returnDraft[0].Text("quantity")!="1"||returnDraft[0].Text("discount_amount")!="7"||returnDraft[1].Text("quantity")!=""||returnRows[0].Text("quantity")!="2")throw new Exception("Return drafts must use remaining quantities, omit exhausted lines and preserve source prices/discounts");

// Exercise the production source gate with delayed synthetic reads.
foreach(var scenario in new[]{"failure","draft","company","closed","success"})
{
    var gate=new SourceSelectionRequest();var completion=new TaskCompletionSource<string>();var draft="original";var current=true;var applied="old";
    var pending=gate.Load(()=>completion.Task,()=>draft,()=>current,value=>applied=value);
    if(!gate.Busy||applied!="old")throw new Exception("Source fetch changed the draft before success");
    if(await gate.Load(()=>Task.FromResult("duplicate"),()=>draft,()=>current,value=>applied=value))throw new Exception("Duplicate source request accepted");
    if(scenario=="draft")draft="edited";if(scenario=="company")current=false;if(scenario=="closed")gate.Invalidate();
    if(scenario=="failure")completion.SetException(new IOException("Synthetic failed GET"));else completion.SetResult("new");
    try{var accepted=await pending;if(accepted!=(scenario=="success"))throw new Exception("Unexpected source publication");}catch(IOException)when(scenario=="failure"){}
    if(applied!=(scenario=="success"?"new":"old")||gate.Busy)throw new Exception("Draft/source state was lost");
    if(scenario=="failure"&&!await gate.Load(()=>Task.FromResult("retry"),()=>draft,()=>current,value=>applied=value))throw new Exception("Source retry failed");
}
Console.WriteLine("PASS source fetch failure/retry, single-flight and stale draft/company/closed boundaries");

var sourceChoiceRows=new[]{new JsonObject{["source_line_id"]="0:first",["remaining_return_quantity"]="0",["source_line_number"]=1,["description"]="Same service",["quantity"]="2",["itc_treatment"]="ineligible"},new JsonObject{["source_line_id"]="1:second",["source_line_number"]=2,["description"]="Same service",["quantity"]="2",["itc_treatment"]="pending_review"}};
var unselectedSourceChoices=SourceLineChoices.Build(sourceChoiceRows,"","");
if(unselectedSourceChoices.Count!=3||unselectedSourceChoices[0].Key!="")throw new Exception("New legacy row must expose matching placeholder");
var explicitSourceChoices=SourceLineChoices.Build(sourceChoiceRows,"1:second","2");
if(explicitSourceChoices.Count!=2||explicitSourceChoices.Any(choice=>choice.Key=="")||explicitSourceChoices.Select(choice=>choice.Key).Distinct().Count()!=2)throw new Exception("Explicit source choice must not offer a misleading blank selection");
if(!explicitSourceChoices[0].Label.Contains("additional return qty 0")||!explicitSourceChoices[1].Label.Contains("additional return qty needs review"))throw new Exception("Zero remaining and unknown capacity must be distinct");
var unavailableSourceChoice=SourceLineChoices.Build(Array.Empty<JsonObject>(),"1:second","2");
if(unavailableSourceChoice.Single().Label!="Saved source line 2")throw new Exception("Unavailable options must preserve readable saved selection");

if(args.Length==2&&args[0]=="--local-complete-backup"){await CompleteTransferSmoke.Run(args[1]);return;}

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
var summaryRecords=new[]{
    new JsonObject{["posted"]=true,["date"]="2026-11-01",["amount"]="100"},
    new JsonObject{["posted"]=true,["cancelled"]=true,["date"]="2026-11-01",["amount"]="200"},
    new JsonObject{["posted"]=false,["date"]="2026-11-01",["amount"]="300"},
    new JsonObject{["posted"]=true,["date"]="2026-12-01",["amount"]="400"}
};
Check(summaryRecords.Where(r=>WorkflowMasterValues.IsPostedRecord(r)).Sum(r=>r.Number("amount"))==500,"register financial totals exclude cancelled and unposted documents");
Check(summaryRecords.Where(r=>WorkflowMasterValues.IsPostedRecord(r,"2026-11-12")).Sum(r=>r.Number("amount"))==100,"dashboard financial totals also exclude future entries");
var shareRow=new JsonObject{["name"]="Same name",["data"]=new JsonObject{["party_id"]="linked",["party_phone"]="9000000003"}};
var shareParties=new[]{new JsonObject{["kind"]="party",["id"]="other",["name"]="Same name",["data"]=new JsonObject{["phone"]="9000000001"}},new JsonObject{["kind"]="party",["id"]="linked",["name"]="Renamed party",["data"]=new JsonObject{["phone"]="9000000002"}}};
Check(WhatsAppShare.PartyPhone(shareRow,shareParties)=="9000000002","sharing uses the linked party before a same-name match");
Check(WhatsAppShare.PartyPhone(shareRow,shareParties.Take(1))=="9000000003","missing linked party falls back to the document phone");
shareParties[1]["data"]!["phone"]="";
Check(WhatsAppShare.PartyPhone(shareRow,shareParties)=="9000000003","blank master phone falls back to document snapshot");
shareRow["data"]!.AsObject().Remove("party_id");
Check(WhatsAppShare.PartyPhone(shareRow,shareParties)=="9000000001","legacy document may find party by name");
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
var apiIdentity=ClientCapabilities.Parse(new JsonObject{["capabilities_version"]=1,["supported_features"]=new JsonArray(),["api_version"]="1.5.0",["build_revision"]=new string('A',40)});Check(apiIdentity.ApiVersion=="1.5.0"&&apiIdentity.BuildRevision==new string('a',40),"connected API identity uses validated cached capability metadata");Check(ClientCapabilities.Unavailable.ApiVersion=="unknown"&&ClientCapabilities.Unavailable.BuildRevision=="unknown","missing API identity never guesses client build metadata");
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

var slowFeatures=new CapabilityTransport{DelayMilliseconds=2000};using(var client=new ApexApi("https://synthetic-cold-capabilities.invalid",slowFeatures)){
 await client.Login("metadata@example.invalid","synthetic",false);var clock=System.Diagnostics.Stopwatch.StartNew();var core=client.LoadCompanyCore("cold-company");Check(await Task.WhenAny(core,Task.Delay(1000))==core,"core company load completes independently of2second capability response");await core;var coreMs=clock.ElapsedMilliseconds;Check(client.Capabilities.Pending&&!client.Capabilities.Supports("party_credit_limits"),"pending metadata is labelled checking and optional features fail closed");await client.EnsureCapabilities();Check(client.Capabilities.Supports("party_credit_limits")&&slowFeatures.CapabilityCalls==1,"slow successful capability response enables features without another request");Console.WriteLine($"COLD_CAPABILITIES core_ms={coreMs} capability_ms={clock.ElapsedMilliseconds} requests={slowFeatures.CapabilityCalls}");
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

Check(BuildIdentity.Version=="1.5.0"&&BuildIdentity.Normalize(new string('A',40))==new string('a',40)&&BuildIdentity.Normalize(new string('b',64))==new string('b',64),"build identity accepts full40/64hex revisions and current1.5.0 version");foreach(var invalid in new string?[]{null,"","main","1234567",new string('a',39),new string('a',41),new string('g',40),new string('a',40)+"\n"," "+new string('a',40)})Check(BuildIdentity.Normalize(invalid)=="unknown","invalid or missing build revision is unknown");

var fixedDiscount=new LineDiscountState(new JsonObject{["discount_amount"]="10",["discount_percent"]="0"});var fixedLine=new JsonObject{["quantity"]="1",["rate"]="100"};fixedDiscount.WriteTo(fixedLine);Check(fixedDiscount.Mode=="amount"&&fixedLine.Text("discount_amount")=="10"&&!fixedLine.ContainsKey("discount_percent"),"reopened fixed discount preserves10 and serializes only fixed key");fixedLine["quantity"]="0.5";fixedDiscount.WriteTo(fixedLine);Check(fixedLine.Text("discount_amount")=="10","quantity change never silently prorates fixed line discount");fixedDiscount.Select("percent");fixedDiscount.WriteTo(fixedLine);Check(fixedDiscount.Value=="0"&&!fixedLine.ContainsKey("discount_amount")&&fixedLine.Text("discount_percent")=="0","switching fixed to percent clears previous fixed discount");fixedDiscount.Value="15";fixedDiscount.Select("amount");fixedDiscount.WriteTo(fixedLine);Check(fixedDiscount.Value=="0"&&!fixedLine.ContainsKey("discount_percent"),"switching percent to fixed clears previous percentage");var percentDiscount=new LineDiscountState(new JsonObject{["discount_percent"]="12.5"});percentDiscount.WriteTo(fixedLine);Check(percentDiscount.Mode=="percent"&&fixedLine.Text("discount_percent")=="12.5"&&!fixedLine.ContainsKey("discount_amount"),"percentage-only legacy lines remain percentage discounts");

Check(new LineDiscountState(new JsonObject{["discount_amount"]="0",["discount_percent"]="0"}).Mode=="amount","explicit zero fixed discount retains fixed mode on reopen");
var discountReview=new FixedDiscountReview();var returnedLine=new JsonObject{["quantity"]="1",["discount_amount"]="10"};Check(FixedDiscountReview.Needed(true,new[]{returnedLine})&&!FixedDiscountReview.Needed(false,new[]{returnedLine})&&!FixedDiscountReview.Needed(true,new[]{new JsonObject{["discount_amount"]="0"}}),"only linked returns with positive fixed discounts require explicit review");Check(!discountReview.IsAcknowledged("line:0:1:10"),"new linked return starts unacknowledged");discountReview.Acknowledge("line:0:1:10");Check(discountReview.IsAcknowledged("line:0:1:10")&&!discountReview.IsAcknowledged("line:1:0.5:10")&&!discountReview.IsAcknowledged("line:2:1:10"),"quantity change and change-back revisions both invalidate fixed-discount acknowledgement");Check(!discountReview.IsAcknowledged("line:1:1:5"),"fixed amount edit invalidates return review");discountReview.Acknowledge("historical:0:1:10");Check(discountReview.IsAcknowledged("historical:0:1:10"),"unchanged historical note may retain its initial reviewed signature");

var backupTransport=new BackupTransport();using(var client=new ApexApi("https://synthetic-transfer.invalid",backupTransport)){
 await client.Login("transfer@example.invalid","synthetic",false);var transfer=new CompleteBackupTransfer(client);using var plaintext=new MemoryStream(backupTransport.Archive);
 try{await transfer.UploadAndPreview(plaintext,"Restored synthetic");throw new Exception("Expected interrupted creation");}catch(ApiFailure e)when(e.Status==0){}Check(transfer.Pending,"unknown upload creation retains recovery state");
 var preview=await transfer.UploadAndPreview(plaintext,"Restored synthetic");Check(!transfer.Pending&&preview.Text("digest")==CompleteBackupTransfer.Hash(backupTransport.Archive),"same upload key recovers and verifies complete preview digest");Check(backupTransport.CreateKeys.Distinct().Count()==1&&backupTransport.Uploaded.SequenceEqual(new[]{1}),"resumed upload skips acknowledged chunk zero");
 try{await transfer.Commit();throw new Exception("Expected interrupted commit");}catch(ApiFailure e)when(e.Status==0){}Check(transfer.Pending,"unknown restore commit remains unresolved");var committed=await transfer.Commit();Check(committed.Text("company_id")=="restored-company"&&!transfer.Pending&&backupTransport.CommitDigests.Distinct().Count()==1,"commit retries exact stage and digest without duplicate company");
 var export=new CompleteBackupTransfer(client);using(var archive=await export.DownloadExport("company"))Check(archive.Length==backupTransport.Archive.Length&&SHA256.HashData(archive).SequenceEqual(SHA256.HashData(backupTransport.Archive)),"complete export verifies every chunk and whole archive");
 backupTransport.Tamper=true;try{using var archive=await export.DownloadExport("company");throw new Exception("Tampered chunk accepted");}catch(InvalidDataException){}Check(true,"tampered complete export is rejected before save");
 var resume=new CompleteBackupTransfer(client,transfer.Metadata);using var different=new MemoryStream(new byte[backupTransport.Archive.Length]);try{await resume.UploadAndPreview(different,"Restored synthetic");throw new Exception("Different resume payload accepted");}catch(InvalidOperationException){}Check(true,"resume refuses a different file before further chunk writes");
 try{await client.DownloadBounded("/api/companies/company/backup-exports/export-id/chunks/0",10);throw new Exception("Oversized download accepted");}catch(InvalidDataException){}Check(true,"binary transport rejects oversized response before materializing it");
 var oldSession=new CompleteBackupTransfer(client);await client.Login("another@example.invalid","synthetic",false);try{await oldSession.StartExport("company");throw new Exception("Old session transfer continued");}catch(OperationCanceledException){}Check(true,"transfer cannot continue under a replacement account session");

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
 public int DelayMilliseconds=20;public string Failure="";public int CapabilityCalls;public bool SentAuthorization,Hold;public TaskCompletionSource<bool> Entered=new(TaskCreationOptions.RunContinuationsAsynchronously),Release=new(TaskCreationOptions.RunContinuationsAsynchronously);
 protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request,CancellationToken cancellation){
  if(request.RequestUri!.AbsolutePath=="/api/capabilities"){Interlocked.Increment(ref CapabilityCalls);SentAuthorization|=request.Headers.Authorization is not null;if(Hold){Entered.SetResult(true);await Release.Task.WaitAsync(cancellation);}await Task.Delay(DelayMilliseconds,cancellation);if(Failure=="network")throw new HttpRequestException("synthetic offline");if(Failure=="timeout")throw new TaskCanceledException("synthetic timeout");if(Failure is "503" or "404")return new((HttpStatusCode)int.Parse(Failure)){Content=new StringContent("{}")};if(Failure=="invalid")return new(HttpStatusCode.OK){Content=new StringContent("not json")};return new(HttpStatusCode.OK){Content=new StringContent("{\"capabilities_version\":1,\"supported_features\":[\"party_credit_limits\"]}")};}
  if(request.RequestUri!.AbsolutePath.Contains("/companies/"))return new(HttpStatusCode.OK){Content=new StringContent("[]")};
  return new(HttpStatusCode.OK){Content=new StringContent("{\"token\":\"synthetic-metadata-session\"}")};
 }
}

sealed class BackupTransport:HttpMessageHandler
{
 public byte[] Archive=Enumerable.Range(0,524301).Select(i=>(byte)(i%251)).ToArray();public List<string> CreateKeys=[],CommitDigests=[];public List<int> Uploaded=[];public bool Tamper;bool created,committed;
 JsonObject Metadata(bool export=false)=>new(){[export?"export_id":"upload_id"]=export?"export-id":"upload-id",["state"]=export?"ready":"uploading",["target_company_name"]="Restored synthetic",["byte_count"]=Archive.Length,["sha256"]=CompleteBackupTransfer.Hash(Archive),["chunk_size"]=524288,["chunk_count"]=2,["received_indices"]=new JsonArray(0),["chunks"]=new JsonArray(Enumerable.Range(0,2).Select(i=>(JsonNode)new JsonObject{["index"]=i,["size_bytes"]=Part(i).Length,["sha256"]=CompleteBackupTransfer.Hash(Part(i))}).ToArray())};
 byte[] Part(int index)=>Archive.Skip(index*524288).Take(524288).ToArray();HttpResponseMessage Json(JsonNode value)=>new(HttpStatusCode.OK){Content=new StringContent(value.ToJsonString())};
 protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request,CancellationToken cancellation){var path=request.RequestUri!.AbsolutePath;
 if(path=="/api/auth/login")return Json(new JsonObject{["token"]="transfer-test-session"});
 if(path=="/api/backups/uploads"){CreateKeys.Add(request.Headers.GetValues("Idempotency-Key").Single());if(!created){created=true;throw new HttpRequestException("synthetic response lost after creation");}return Json(Metadata());}
 if(path.EndsWith("/preview"))return Json(new JsonObject{["digest"]=CompleteBackupTransfer.Hash(Archive)});
 if(path.EndsWith("/commit")){CommitDigests.Add(JsonNode.Parse(await request.Content!.ReadAsStringAsync())!.Text("digest"));if(!committed){committed=true;throw new HttpRequestException("synthetic response lost after commit");}return Json(new JsonObject{["company_id"]="restored-company",["digest"]=CompleteBackupTransfer.Hash(Archive),["already_restored"]=true});}
 if(path.Contains("/chunks/")){var index=int.Parse(path.Split('/').Last());if(request.Method==HttpMethod.Put){var data=await request.Content!.ReadAsByteArrayAsync();Uploaded.Add(index);return Json(new JsonObject{["index"]=index,["size_bytes"]=data.Length,["sha256"]=CompleteBackupTransfer.Hash(data),["received"]=true});}var part=Part(index);var hash=CompleteBackupTransfer.Hash(part);if(Tamper)part[0]^=1;var result=new HttpResponseMessage(HttpStatusCode.OK){Content=new ByteArrayContent(part)};result.Headers.Add("X-Chunk-SHA256",hash);result.Headers.Add("X-Archive-SHA256",CompleteBackupTransfer.Hash(Archive));return result;}
 return Json(Metadata(path.Contains("backup-exports")));
 }
}
