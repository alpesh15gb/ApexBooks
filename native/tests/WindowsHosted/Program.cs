using ApexBooks_Windows.Services;
using System.IO.Compression;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using Windows.Storage;

// Exercises the actual published client services without opening windows or using a trading company.
var apiOrigin=Environment.GetEnvironmentVariable("APEX_NATIVE_TEST_ORIGIN")??throw new Exception("Explicit local APEX_NATIVE_TEST_ORIGIN is required; hosted writes are disabled.");
var local=new Uri(apiOrigin);
if(local.Scheme!="http"||local.Host is not("127.0.0.1" or "localhost" or "::1")||local.UserInfo!=""||local.Query!=""||local.Fragment!=""||local.AbsolutePath!="/")throw new Exception("This acceptance runner only permits an isolated loopback HTTP API.");
var qaEmail=$"windows-service-{Guid.NewGuid():N}@example.invalid";
const string qaPassword="Synthetic-Windows-Service-Only-42!";
using var api=new ApexApi(apiOrigin);
if(api.RestoreSession())throw new Exception("A remembered session exists for this local origin; leaving it unchanged. Use a fresh isolated runner/origin.");
await api.Send("/api/auth/register",HttpMethod.Post,new JsonObject{["email"]=qaEmail,["password"]=qaPassword});
await api.Login(qaEmail,qaPassword,true);
var checks=new List<string>();
void Check(string name,bool condition){if(!condition)throw new Exception(name);checks.Add(name);}
using(var restored=new ApexApi(apiOrigin))Check("normal Windows vault restores synthetic QA session",restored.RestoreSession()&&restored.Email==qaEmail&&await restored.Send("/api/companies") is JsonArray);
string Gstin(string prefix){const string alphabet="0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ";int sum=0,factor=2;foreach(var ch in prefix.Reverse()){int n=alphabet.IndexOf(ch)*factor;sum+=n/36+n%36;factor=3-factor;}return prefix+alphabet[(36-sum%36)%36];}
var company=await api.Send("/api/companies",HttpMethod.Post,new JsonObject{["name"]=$"Native Windows Transport QA {DateTimeOffset.UtcNow.ToUnixTimeMilliseconds()}",["tax_mode"]="regular",["state_code"]="27",["gstin"]=Gstin("27ABCDE1234F1Z")});
var cid=company.Text("id");string PathFor(string suffix)=>api.CompanyPath(cid,suffix);
Task<JsonNode> Post(JsonObject body)=>api.SaveRecord(cid,body,Guid.NewGuid().ToString());
var item=await Post(new JsonObject{["kind"]="item",["name"]="Native Windows device adapter",["date"]="2026-11-01",["data"]=new JsonObject{["item_type"]="goods",["track_stock"]=true,["unit"]="NOS",["hsn"]="85176290",["sale_rate"]="100",["purchase_rate"]="50",["gst_rate"]="18"}});
var itemId=item.Text("id");
await api.Send(PathFor("/stock/opening"),HttpMethod.Post,new JsonObject{["item_id"]=itemId,["date"]="2026-11-01",["quantity"]="10",["unit_cost"]="50"},Guid.NewGuid().ToString());
JsonObject Body(string kind,int quantity=1,int rate=100,bool tracked=false,JsonObject? extra=null){
    bool supplier=new[]{"purchase_bill","purchase_order","debit_note","expense"}.Contains(kind);
    var line=new JsonObject{["description"]=tracked?"Native Windows device adapter":"Native Windows device service",["quantity"]=quantity,["rate"]=rate,["gst_rate"]=18,["unit"]=tracked?"NOS":"OTH",["hsn"]=tracked?"85176290":"998313",["tax_treatment"]="taxable",["itc_treatment"]="pending_review"};
    if(tracked)line["item_id"]=itemId;
    var data=new JsonObject{["lines"]=new JsonArray(line),["place_of_supply"]="27",["supplier_state"]="27"};
    if(supplier)data["party_gstin"]=Gstin("27PQRST1234L1Z");
    if(extra is not null)foreach(var (key,value)in extra)data[key]=value.Copy();
    return new JsonObject{["kind"]=kind,["name"]=supplier?"Native Windows supplier":"Native Windows buyer",["date"]="2026-11-01",["number"]="",["amount"]="0",["data"]=data};
}
var original=Body("sales_invoice",2,100,true);var retry=Guid.NewGuid().ToString();var sale=await api.SaveRecord(cid,original,retry);
Check("idempotent Windows save",(await api.SaveRecord(cid,original,retry)).Text("id")==sale.Text("id"));
foreach(var rate in new[]{110,100}){
    var edited=Body("sales_invoice",2,rate,true);edited["number"]=sale.Text("number");edited["data"]!["version"]=sale["data"]!["version"].Copy()??JsonValue.Create(0);
    sale=await api.SaveRecord(cid,edited,Guid.NewGuid().ToString(),sale);
    Check($"invoice edit at rate {rate} recalculates GST",sale.Number("amount")==2m*rate*1.18m);
}
var bill=await Post(Body("purchase_bill",10,50,true));var conversions=new Dictionary<string,JsonNode>();
foreach(var kind in new[]{"estimate","proforma","purchase_order"}){
    var draft=await Post(Body(kind));var target=kind=="purchase_order"?"purchase_bill":"sales_invoice";
    conversions[kind]=await Post(Body(target,extra:new JsonObject{["source_document_id"]=draft.Text("id")}));
    Check($"{kind} conversion links source",(await api.Records(cid)).First(r=>r.Text("id")==draft.Text("id")).Text("converted_to").Length>0);
}
await Post(Body("credit_note",1,100,true,new JsonObject{["applied_to"]=sale.Text("id"),["return_stock"]=true}));
await Post(Body("debit_note",1,50,true,new JsonObject{["applied_to"]=bill.Text("id"),["return_stock"]=true}));
JsonObject Payment(string kind,string first,string second)=>new(){["kind"]=kind,["name"]=kind=="payment_in"?"Native Windows buyer":"Native Windows supplier",["date"]="2026-11-01",["amount"]="100",["data"]=new JsonObject{["payment_account"]="cash",["allocations"]=new JsonArray(new JsonObject{["document_id"]=first,["amount"]="50"},new JsonObject{["document_id"]=second,["amount"]="50"})}};
await Post(Payment("payment_in",sale.Text("id"),conversions["estimate"].Text("id")));
await Post(Body("pos",extra:new JsonObject{["payment_account"]="cash",["tender_amount"]="118"}));
var bank=await api.Send(PathFor("/bank-accounts"),HttpMethod.Post,new JsonObject{["name"]="Windows native QA bank",["account_hint"]="0000"});
foreach(var direction in new[]{"cash_to_bank","bank_to_cash"})await Post(new JsonObject{["kind"]="bank_transfer",["name"]=$"Native Windows {direction}",["date"]="2026-11-01",["amount"]="20",["data"]=new JsonObject{["direction"]=direction,["bank_account_id"]=bank.Text("id")}});
await Post(Payment("payment_out",bill.Text("id"),conversions["purchase_order"].Text("id")));
await Post(Body("expense",extra:new JsonObject{["payment_account"]="cash"}));
var register=await api.Records(cid);
Check("receipt and credit reconcile invoice balance",register.First(r=>r.Text("id")==sale.Text("id")).Number("outstanding")==68m);
Check("payment and debit reconcile bill balance",register.First(r=>r.Text("id")==bill.Text("id")).Number("outstanding")==481m);

var fixture=await StorageFile.GetFileFromPathAsync(Path.GetFullPath(args[0]));
var logo=await ApexFiles.Image(fixture,900,240000);
await api.Send(PathFor("/document-branding"),HttpMethod.Patch,new JsonObject{["logo"]=logo,["phone"]="0000000000"});
var branding=await api.Send(PathFor("/document-branding"),HttpMethod.Put,new JsonObject{["bank_name"]="Synthetic native bank"});
Check("Windows PATCH and partial PUT preserve logo",branding.Text("logo")==logo);
var folder=Path.GetDirectoryName(Path.GetFullPath(args[1]))!;Directory.CreateDirectory(folder);
var pdf=await api.Download(PathFor($"/documents/{sale.Text("id")}.pdf"));
Check("native Windows document PDF downloads",Encoding.ASCII.GetString(pdf,0,5)=="%PDF-");await File.WriteAllBytesAsync(Path.Combine(folder,"windows-native-logo-document.pdf"),pdf);
const string query="?from_date=2026-11-01&to_date=2026-11-30";
var financial=await api.Send(PathFor("/reports/financial"+query));
Check("native Windows ledger balances",financial.Number("balance_difference")==0);
var controls=financial["accounts"].Array().ToDictionary(r=>r.Text("code"),r=>r.Number("closing_balance"));
foreach(var (code,value)in new Dictionary<string,decimal>{{"SYS-AR",254},{"SYS-AP",549},{"SYS-INVENTORY",900},{"SYS-CASH",0},{"SYS-COGS",50},{"SYS-SALES",400},{"SYS-IN-CGST",58.50m},{"SYS-IN-SGST",58.50m},{"SYS-OUT-CGST",36},{"SYS-OUT-SGST",36}})Check($"ledger control {code}",controls[code]==value);
Check("profit includes stock cost, returns and expenses",financial.Number("net_profit")==150);
var stock=await api.Send(PathFor("/reports/stock"+query));var tracked=stock["rows"].Array().First(r=>r.Text("item_id")==itemId);
Check("stock quantity reconciles both returns",tracked.Number("closing_quantity")==18);
Check("stock valuation reconciles",tracked.Number("closing_value")==900);
var summary=await api.Send(PathFor("/reports/summary"+query));
Check("net posted sales excludes converted drafts",summary.Number("sales")==472);
Check("net posted purchases excludes converted drafts",summary.Number("purchases")==649);
foreach(var kind in new[]{"gstr1","gstr2a","gstr3b"}){
    await api.Send(PathFor($"/gst-returns/{kind}"+query));
    foreach(var format in new[]{"pdf","xlsx"}){
        var bytes=await api.Download(PathFor($"/gst-returns/{kind}.{format}"+query));
        Check($"{kind} {format} download",format=="pdf"?Encoding.ASCII.GetString(bytes,0,5)=="%PDF-":bytes[0]==80&&bytes[1]==75);
        if(format=="xlsx"){
            using var zip=new ZipArchive(new MemoryStream(bytes));using var reader=new StreamReader(zip.GetEntry("xl/workbook.xml")!.Open());
            Check($"{kind} contains worksheet schedules",(await reader.ReadToEndAsync()).Contains("<sheet "));
        }
        await File.WriteAllBytesAsync(Path.Combine(folder,$"windows-native-{kind}.{format}"),bytes);
    }
}
var json=await api.Send(PathFor("/gst-returns/gstr1.json"+query));
Check("GSTR-1 draft JSON contains GSTIN and consumer schedules",json.Text("gstin")==company.Text("gstin")&&json["b2cs"].Array().Count>0);
var result=new JsonObject{["all_pass"]=true,["client"]=$"published Windows {typeof(ApexApi).Assembly.GetName().Version?.ToString(3)} ApexApi and ApexFiles",["company_id"]=cid,["logo_bytes"]=Convert.FromBase64String(logo.Split(',',2)[1]).Length,["checks"]=JsonSerializer.SerializeToNode(checks),["financial"]=financial,["stock"]=stock,["summary"]=summary};
result["api_origin"]=api.Origin;
await File.WriteAllTextAsync(args[1],result.ToJsonString(new JsonSerializerOptions{WriteIndented=true}));
api.ForgetSession();
Console.WriteLine($"PASS: {checks.Count} published Windows service checks; evidence: {args[1]}");
