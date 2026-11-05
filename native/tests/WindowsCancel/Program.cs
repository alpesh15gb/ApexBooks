using System.IO;
using System.Net.Http;
using System.Diagnostics;
using System.Net.Http.Headers;
using System.Reflection.Metadata;
using System.Reflection.PortableExecutable;
using System.Text;
using System.Text.Json.Nodes;
using System.Windows.Automation;
using Drawing=System.Drawing;

if(args.Length!=3)throw new ArgumentException("Usage: WindowsCancel <published-directory> <http-loopback-origin> <evidence-directory>");
var publish=Path.GetFullPath(args[0]);var origin=new Uri(args[1]);var evidence=Path.GetFullPath(args[2]);Directory.CreateDirectory(evidence);
if(origin.Scheme!="http"||origin.Host is not("127.0.0.1" or "localhost" or "::1")||origin.UserInfo!=""||origin.Query!=""||origin.Fragment!=""||origin.AbsolutePath!="/")throw new Exception("Only an explicit loopback HTTP API is allowed.");
// Inspect metadata without loading the target app or executing its module initializers.
using(var stream=File.OpenRead(Path.Combine(publish,"ApexBooks.Windows.dll")))using(var pe=new PEReader(stream)){
    var metadata=pe.GetMetadataReader();string? embeddedOrigin=null;var debug=false;
    foreach(var handle in metadata.GetAssemblyDefinition().GetCustomAttributes()){
        var attribute=metadata.GetCustomAttribute(handle);if(attribute.Constructor.Kind!=HandleKind.MemberReference)continue;
        var constructor=metadata.GetMemberReference((MemberReferenceHandle)attribute.Constructor);if(constructor.Parent.Kind!=HandleKind.TypeReference)continue;
        var type=metadata.GetTypeReference((TypeReferenceHandle)constructor.Parent);var name=metadata.GetString(type.Name);var value=metadata.GetBlobReader(attribute.Value);if(value.ReadUInt16()!=1)continue;
        if(name=="AssemblyMetadataAttribute"){var key=value.ReadSerializedString();var text=value.ReadSerializedString();if(key=="ApexApiOrigin")embeddedOrigin=text;}
        if(name=="DebuggableAttribute")debug=(value.ReadInt32()&256)!=0;
    }
    if(embeddedOrigin!=origin.GetLeftPart(UriPartial.Authority))throw new Exception("Refusing launch: Debug app must embed this exact synthetic loopback ApexApiOrigin.");
    if(!debug)throw new Exception("Refusing launch: this harness requires a Debug build.");
}
var checks=new List<string>();Process? app=null;AutomationElement? window=null;
void Check(string message,bool condition=true){if(!condition)throw new Exception("Assertion failed: "+message);checks.Add(message);Console.WriteLine("PASS "+message);}
using var http=new HttpClient(new HttpClientHandler{AllowAutoRedirect=false}){BaseAddress=origin,Timeout=TimeSpan.FromSeconds(30)};
async Task<JsonObject> Post(string path,JsonObject body){using var response=await http.PostAsync(path,new StringContent(body.ToJsonString(),Encoding.UTF8,"application/json"));var text=await response.Content.ReadAsStringAsync();if(!response.IsSuccessStatusCode)throw new Exception($"Synthetic API {path} failed ({(int)response.StatusCode}): {text}");return JsonNode.Parse(text)!.AsObject();}
async Task<JsonNode> Get(string path){using var response=await http.GetAsync(path);var text=await response.Content.ReadAsStringAsync();if(!response.IsSuccessStatusCode)throw new Exception($"Synthetic API GET {path} failed ({(int)response.StatusCode}): {text}");return JsonNode.Parse(text)!;}
async Task<JsonArray> CompanyRecords(string company)=> (await Get($"/api/companies/{company}/records?compact=true&limit=500")).AsArray();
decimal Number(JsonNode? node,string key)=>decimal.TryParse(node?[key]?.ToString(),System.Globalization.NumberStyles.Number,System.Globalization.CultureInfo.InvariantCulture,out var value)?value:0;
AutomationElement Wait(Func<AutomationElement?> find,string description,int seconds=60){var timeout=Stopwatch.StartNew();while(timeout.Elapsed.TotalSeconds<seconds){try{var element=find();if(element is not null)return element;}catch(ElementNotAvailableException){}if(app?.HasExited==true)throw new Exception($"WinUI exited with {app.ExitCode} while waiting for {description}");Thread.Sleep(250);}throw new Exception("UI timeout: "+description);}
AutomationElement? Find(string name,ControlType? type=null)=>window?.FindAll(TreeScope.Descendants,Condition.TrueCondition).Cast<AutomationElement>().FirstOrDefault(x=>x.Current.Name==name&&(type is null||x.Current.ControlType==type));
AutomationElement? ReadyButton(string label){var button=Find(label,ControlType.Button);return button is not null&&button.Current.IsEnabled&&!button.Current.IsOffscreen?button:null;}
AutomationElement? EditField(string label)
{
    if(window is null)return null;
    var edits=window.FindAll(TreeScope.Descendants,new PropertyCondition(AutomationElement.ControlTypeProperty,ControlType.Edit)).Cast<AutomationElement>().ToArray();
    var exact=edits.FirstOrDefault(e=>e.Current.Name==label||e.Current.LabeledBy?.Current.Name==label);if(exact is not null)return exact;
    var text=Find(label,ControlType.Text);if(text is null)return null;var parent=text;
    for(var level=0;level<5;level++){
        parent=TreeWalker.RawViewWalker.GetParent(parent);if(parent is null)break;
        if(parent.Current.ControlType==ControlType.Edit&&parent.TryGetCurrentPattern(ValuePattern.Pattern,out _))return parent;
        var children=parent.FindAll(TreeScope.Descendants,new PropertyCondition(AutomationElement.ControlTypeProperty,ControlType.Edit)).Cast<AutomationElement>().Where(e=>e.TryGetCurrentPattern(ValuePattern.Pattern,out _)).ToArray();
        if(children.Length==1)return children[0];
        if(children.Length>1)break;
    }
    return null;
}
string Value(AutomationElement element)=>((ValuePattern)element.GetCurrentPattern(ValuePattern.Pattern)).Current.Value;
void Invoke(AutomationElement element){if(element.TryGetCurrentPattern(InvokePattern.Pattern,out var pattern))((InvokePattern)pattern).Invoke();else if(element.TryGetCurrentPattern(SelectionItemPattern.Pattern,out pattern))((SelectionItemPattern)pattern).Select();else throw new Exception("Control has no supported Invoke/Selection pattern: "+element.Current.Name);}
void Set(AutomationElement element,string value){if(!element.TryGetCurrentPattern(ValuePattern.Pattern,out var pattern))throw new Exception("Control has no supported Value pattern: "+element.Current.Name);((ValuePattern)pattern).SetValue(value);}
void ChooseNativeFile(string title,string action,string path)
{
    var dialog=Wait(()=>window?.FindAll(TreeScope.Descendants,new PropertyCondition(AutomationElement.ControlTypeProperty,ControlType.Window)).Cast<AutomationElement>().FirstOrDefault(e=>e.Current.Name==title&&!e.Current.IsOffscreen),"owned system "+title+" picker",120);
    var field=Wait(()=>dialog.FindAll(TreeScope.Descendants,new PropertyCondition(AutomationElement.ControlTypeProperty,ControlType.Edit)).Cast<AutomationElement>().FirstOrDefault(e=>(e.Current.Name is "File name:" or "File name"||e.Current.AutomationId=="1148")&&e.TryGetCurrentPattern(ValuePattern.Pattern,out _)),title+" File name");
    if(action=="Save"){
        // ValuePattern can change the shell edit's displayed text without
        // updating its selected filename. Use genuine keyboard input and commit
        // the edit before activating Save. No retry after activation.
        field.SetFocus();Wait(()=>field.Current.HasKeyboardFocus?field:null,"Save filename keyboard focus",10);
        System.Windows.Forms.SendKeys.SendWait("^a");System.Windows.Forms.SendKeys.SendWait("{BACKSPACE}");
        Wait(()=>Value(field)==""?field:null,"Save filename cleared",10);
        var typed="";var deadline=Stopwatch.StartNew();
        foreach(var character in path){
            if(deadline.Elapsed>TimeSpan.FromSeconds(30)||!field.Current.HasKeyboardFocus)throw new Exception("Save filename lost focus or exceeded typing deadline.");
            var key=character switch{'{'=>"{{}",'}'=>"{}}",'+' or '^' or '%' or '~' or '(' or ')'=>"{"+character+"}",_=>character.ToString()};
            System.Windows.Forms.SendKeys.SendWait(key);typed+=character;
            Wait(()=>Value(field)==typed?field:null,"Save filename character "+typed.Length,5);
        }
        Check("Save filename keyboard entry matches exact destination",Value(field)==path);
        System.Windows.Forms.SendKeys.SendWait("{TAB}");
        Wait(()=>!field.Current.HasKeyboardFocus?field:null,"Save filename committed on Tab",10);
    }else Set(field,path);
    Check(title+" picker contains exact requested path",Value(field)==path);
    var confirm=Wait(()=>dialog.FindAll(TreeScope.Descendants,new PropertyCondition(AutomationElement.ControlTypeProperty,ControlType.Button)).Cast<AutomationElement>().FirstOrDefault(e=>e.Current.Name==action&&e.Current.IsEnabled),title+" "+action+" button");
    if(action=="Save"){
        // Shell Save can make outgoing COM calls. UIA Invoke dispatches a
        // synchronous input call and produced RPC_E_CANTCALLOUT_ININPUTSYNCCALL
        // on the hosted runner. Use one genuine keyboard activation instead.
        confirm.SetFocus();Wait(()=>confirm.Current.HasKeyboardFocus?confirm:null,"native Save button keyboard focus",10);
        Check("committed Save destination survives button focus",Value(field)==path);
        Snapshot("10-native-save-destination");
        System.Windows.Forms.SendKeys.SendWait(" ");
    }else Invoke(confirm);
}
void Snapshot(string name){if(window is null)return;var rectangle=window.Current.BoundingRectangle;if(rectangle.Width<1||rectangle.Height<1)throw new Exception("App has no visible capture rectangle.");using var bitmap=new Drawing.Bitmap((int)rectangle.Width,(int)rectangle.Height);using(var graphics=Drawing.Graphics.FromImage(bitmap))graphics.CopyFromScreen((int)rectangle.X,(int)rectangle.Y,0,0,bitmap.Size);bitmap.Save(Path.Combine(evidence,name+".png"),Drawing.Imaging.ImageFormat.Png);
    // Only this synthetic app window, never the desktop or credentials. Bounded diagnostic for log-only artifact readers.
    if(name=="03-invoice-form"||name=="failure-visible-app"){
        var codec=Drawing.Imaging.ImageCodecInfo.GetImageEncoders().Single(c=>c.FormatID==Drawing.Imaging.ImageFormat.Jpeg.Guid);
        using var settings=new Drawing.Imaging.EncoderParameters(1);settings.Param[0]=new Drawing.Imaging.EncoderParameter(Drawing.Imaging.Encoder.Quality,45L);
        var emitted=false;
        for(var width=Math.Min(800,bitmap.Width);width>=240;width=width*3/4){
            using var preview=new Drawing.Bitmap(bitmap,new Drawing.Size(width,Math.Max(1,bitmap.Height*width/bitmap.Width)));using var bytes=new MemoryStream();preview.Save(bytes,codec,settings);
            if(bytes.Length>75000)continue;Console.WriteLine($"Synthetic app visual: {name}, width={width}, JPEG bytes={bytes.Length}");Console.WriteLine("SYNTHETIC_APP_JPEG_BASE64 "+Convert.ToBase64String(bytes.ToArray()));emitted=true;break;
        }
        if(!emitted)Console.WriteLine("Synthetic app log preview omitted: could not meet 75KB JPEG budget; full PNG remains in artifact.");
    }}
void Dump(){if(window is null)return;var rows=window.FindAll(TreeScope.Descendants,Condition.TrueCondition).Cast<AutomationElement>().Select(x=>new{type=x.Current.ControlType.ProgrammaticName,name=x.Current.Name,password=x.Current.IsPassword}).ToArray();File.WriteAllText(Path.Combine(evidence,"uia-tree.json"),System.Text.Json.JsonSerializer.Serialize(rows,new System.Text.Json.JsonSerializerOptions{WriteIndented=true}));}
AutomationElement? FindContains(string text)=>window?.FindAll(TreeScope.Descendants,Condition.TrueCondition).Cast<AutomationElement>().FirstOrDefault(x=>x.Current.Name.Contains(text,StringComparison.Ordinal));
void Toggle(AutomationElement element){if(!element.TryGetCurrentPattern(TogglePattern.Pattern,out var pattern))throw new Exception("No Toggle pattern: "+element.Current.Name);var toggle=(TogglePattern)pattern;if(toggle.Current.ToggleState!=ToggleState.On)toggle.Toggle();}
async Task<JsonObject> Record(string cid,string id)=>(JsonObject)(await Get($"/api/companies/{cid}/records/{id}"))!;
AutomationElement? ButtonNamed(string name)=>window?.FindAll(TreeScope.Descendants,new PropertyCondition(AutomationElement.ControlTypeProperty,ControlType.Button)).Cast<AutomationElement>().FirstOrDefault(e=>e.Current.Name==name&&e.Current.IsEnabled);
void LedgerStep(){
    // 4. Party statement reads as a Tally-style ledger
    var closeDetail=ButtonNamed("Done");if(closeDetail is not null)Invoke(closeDetail);Thread.Sleep(800);
    Invoke(Wait(()=>Find("Parties"),"Parties navigation"));
    Invoke(Wait(()=>Find("Paid Buyer",ControlType.Button)??Find("Paid Buyer"),"party row"));
    Wait(()=>Find("Closing balance"),"ledger closing balance row");
    Check("ledger shows Tally columns",new[]{"Particulars","Vch Type","Vch No.","Debit","Credit","Opening balance","Current total"}.All(x=>Find(x) is not null));
    Check("ledger shows debit and receipt entries",Find("To Sales") is not null&&Find("By Cash") is not null);
    Check("ledger closes at the party balance",Find("460.00 Dr") is not null);
    foreach(var scroller in window!.FindAll(TreeScope.Descendants,Condition.TrueCondition).Cast<AutomationElement>().Where(e=>e.TryGetCurrentPattern(ScrollPattern.Pattern,out _))){var pattern=(ScrollPattern)scroller.GetCurrentPattern(ScrollPattern.Pattern);if(pattern.Current.VerticallyScrollable)pattern.SetScrollPercent(ScrollPattern.NoScroll,100);}Thread.Sleep(800);
    Snapshot("05-party-ledger");
}
try{
    if(!Environment.UserInteractive)throw new Exception("No interactive desktop.");
    var email=$"windows-cancel-{Guid.NewGuid():N}@example.invalid";var password="Synthetic-Windows-Ui-Only-42!";
    await Post("/api/auth/register",new(){["email"]=email,["password"]=password});var login=await Post("/api/auth/login",new(){["email"]=email,["password"]=password});http.DefaultRequestHeaders.Authorization=new AuthenticationHeaderValue("Bearer",login["token"]!.GetValue<string>());
    var company=await Post("/api/companies",new(){["name"]="Windows Cancel QA",["tax_mode"]="unregistered",["state_code"]="27"});var cid=company["id"]!.GetValue<string>();var date=DateTimeOffset.UtcNow.ToOffset(TimeSpan.FromMinutes(330)).ToString("yyyy-MM-dd");
    JsonObject Line(string description,string rate)=>new(){["lines"]=new JsonArray(new JsonObject{["description"]=description,["quantity"]="1",["rate"]=rate,["gst_rate"]="0"})};
    var paidInvoice=await Post($"/api/companies/{cid}/records",new(){["kind"]="sales_invoice",["name"]="Paid Buyer",["date"]=date,["data"]=Line("Paid service","500")});
    var receipt=await Post($"/api/companies/{cid}/records",new(){["kind"]="payment_in",["name"]="Paid Buyer",["date"]=date,["amount"]="40",["data"]=new JsonObject{["applied_to"]=paidInvoice["id"]!.GetValue<string>()}});
    var plainInvoice=await Post($"/api/companies/{cid}/records",new(){["kind"]="sales_invoice",["name"]="Plain Buyer",["date"]=date,["data"]=Line("Plain service","150")});
    await Post($"/api/companies/{cid}/records",new(){["kind"]="party",["name"]="Paid Buyer",["date"]=date,["data"]=new JsonObject()});
    Check("synthetic company, paid invoice and plain invoice seeded");
    var start=new ProcessStartInfo(Path.Combine(publish,"ApexBooks.Windows.exe")){WorkingDirectory=publish,UseShellExecute=false};start.Environment["APEX_BOOKS_API_ORIGIN"]=origin.GetLeftPart(UriPartial.Authority);app=Process.Start(start)??throw new Exception("launch failed");
    window=Wait(()=>AutomationElement.RootElement.FindFirst(TreeScope.Children,new PropertyCondition(AutomationElement.ProcessIdProperty,app.Id)),"app window");
    var emailBox=Wait(()=>window.FindAll(TreeScope.Descendants,new PropertyCondition(AutomationElement.ControlTypeProperty,ControlType.Edit)).Cast<AutomationElement>().FirstOrDefault(x=>!x.Current.IsPassword),"email input");
    var passwordBox=Wait(()=>window.FindAll(TreeScope.Descendants,new PropertyCondition(AutomationElement.ControlTypeProperty,ControlType.Edit)).Cast<AutomationElement>().FirstOrDefault(x=>x.Current.IsPassword),"password input");
    Set(emailBox,email);Set(passwordBox,password);Invoke(Wait(()=>Find("Sign in",ControlType.Button),"Sign in"));
    Wait(()=>Find("Business overview"),"dashboard");Check("signed in");Snapshot("01-dashboard");Thread.Sleep(4000); // optional server capabilities load in the background after sign-in
    // This path sends no keyboard input, so it cannot type into another window when the app is not in front.
    if(Environment.GetEnvironmentVariable("APEX_HARNESS_ONLY")=="ledger"){LedgerStep();Dump();await File.WriteAllTextAsync(Path.Combine(evidence,"result.json"),new JsonObject{["passed"]=true,["checks"]=new JsonArray(checks.Select(x=>(JsonNode)JsonValue.Create(x)!).ToArray())}.ToJsonString());return;}
    Invoke(Wait(()=>Find("Sales & collections  ↗",ControlType.Button),"sales register shortcut"));

    // 1. Received now through the real form
    Invoke(Wait(()=>Find("Add sales invoice",ControlType.Button),"add invoice"));
    var reference="PN"+Guid.NewGuid().ToString("N")[..8].ToUpperInvariant();
    Set(Wait(()=>EditField("Customer / supplier"),"customer"),"Pay Now Buyer");
    Set(Wait(()=>EditField("Reference number"),"reference"),reference);
    var item=Wait(()=>EditField("Item / service"),"item selector");
    item.SetFocus();Thread.Sleep(300);System.Windows.Forms.SendKeys.SendWait("^a");System.Windows.Forms.SendKeys.SendWait("{BACKSPACE}");Thread.Sleep(200);
    foreach(var character in "Pay now service"){System.Windows.Forms.SendKeys.SendWait(character.ToString());Thread.Sleep(40);}
    System.Windows.Forms.SendKeys.SendWait("{TAB}");Thread.Sleep(300);
    Set(Wait(()=>EditField("Quantity"),"quantity"),"1");Set(Wait(()=>EditField("Rate (₹)"),"rate"),"300");
    Wait(()=>window.FindAll(TreeScope.Descendants,new PropertyCondition(AutomationElement.ControlTypeProperty,ControlType.Text)).Cast<AutomationElement>().FirstOrDefault(e=>e.Current.Name.Contains("Total ",StringComparison.Ordinal)&&e.Current.Name.StartsWith("Subtotal ",StringComparison.Ordinal)),"server preview total");
    var payBox=Wait(()=>window.FindAll(TreeScope.Descendants,new PropertyCondition(AutomationElement.ControlTypeProperty,ControlType.CheckBox)).Cast<AutomationElement>().FirstOrDefault(e=>e.Current.Name.Contains("Received now",StringComparison.Ordinal)),"Received now checkbox");Toggle(payBox);Check("Received now section is present and toggles");
    Invoke(Wait(()=>Find("Full amount",ControlType.Button),"Full amount button"));
    var amountField=Wait(()=>EditField("Amount (₹)"),"payment amount");Check("Full amount fills the document total",Value(amountField).StartsWith("300"));
    Set(amountField,"100");Snapshot("02-pay-now-form");
    Invoke(Wait(()=>Find("Save invoice",ControlType.Button),"save invoice"));
    Wait(()=>Find("Save invoice",ControlType.Button) is null?window:null,"form closed");
    var rows=await CompanyRecords(cid);var created=rows.OfType<JsonObject>().SingleOrDefault(r=>r["number"]?.ToString()==reference)??throw new Exception("UI invoice missing");
    var receipts=rows.OfType<JsonObject>().Where(r=>r["kind"]?.ToString()=="payment_in"&&r["name"]?.ToString()=="Pay Now Buyer").ToList();
    Check("invoice posted with exactly one linked receipt",receipts.Count==1&&Number(receipts[0],"amount")==100&&Number(created,"amount")==300&&Number(created,"outstanding")==200);
    // 1b. Like Vyapar / Swipe, a newly saved invoice opens ready to share; close it before continuing.
    Wait(()=>Find("Share on WhatsApp",ControlType.Button),"saved invoice opens ready to share");Check("saved invoice opens ready to share");Snapshot("03-saved-ready-to-share");
    Invoke(Wait(()=>ButtonNamed("Done"),"close saved invoice"));Wait(()=>Find("Share on WhatsApp",ControlType.Button) is null?window:null,"saved invoice closed");

    // 2. Cancel refused while a payment exists
    Invoke(Wait(()=>Find(paidInvoice["number"]!.GetValue<string>(),ControlType.Button),"paid invoice row"));
    Invoke(Wait(()=>Find("Cancel this document",ControlType.Button),"Cancel this document"));
    Set(Wait(()=>EditField("Reason (required)"),"reason field"),"Entered twice");
    Invoke(Wait(()=>ButtonNamed("Cancel document"),"confirm cancel"));
    var refusal=Wait(()=>FindContains("is already received or paid against it"),"server refusal message shown");
    Check("refusal explains the dependent payment",refusal.Current.Name.Contains("Cannot cancel"));Snapshot("03-cancel-refused");
    Check("paid invoice stayed posted",(await Record(cid,paidInvoice["id"]!.GetValue<string>()))["cancelled"]?.GetValue<bool>()!=true);
    var close=ButtonNamed("Cancel");if(close is not null)Invoke(close);
    Thread.Sleep(600);var done=ButtonNamed("Done");if(done is not null)Invoke(done);Thread.Sleep(600);

    // 3. Cancel succeeds on an unpaid invoice
    Invoke(Wait(()=>Find(plainInvoice["number"]!.GetValue<string>(),ControlType.Button),"plain invoice row"));
    Invoke(Wait(()=>Find("Cancel this document",ControlType.Button),"Cancel this document"));
    Set(Wait(()=>EditField("Reason (required)"),"reason"),"Duplicate invoice");
    Invoke(Wait(()=>ButtonNamed("Cancel document"),"confirm cancel"));
    Wait(()=>FindContains("stays in your records"),"cancelled banner after refresh",30);Thread.Sleep(800);Snapshot("04-cancelled");
    var plain=await Record(cid,plainInvoice["id"]!.GetValue<string>());
    Check("plain invoice cancelled on the server",plain["cancelled"]?.GetValue<bool>()==true&&plain["posted"]?.GetValue<bool>()==false);
    Check("detail offers no Cancel or Edit for a cancelled document",Find("Cancel this document",ControlType.Button) is null&&Find("PDF / print / share",ControlType.Button) is not null);
    var financial=await Get($"/api/companies/{cid}/reports/financial?from_date=2000-01-01&to_date=2100-01-01");
    Check("books still balance",Number(financial,"balance_difference")==0);
    LedgerStep();
    Dump();
    await File.WriteAllTextAsync(Path.Combine(evidence,"result.json"),new JsonObject{["passed"]=true,["checks"]=new JsonArray(checks.Select(x=>(JsonNode)JsonValue.Create(x)!).ToArray())}.ToJsonString());
}catch(Exception e){try{Dump();Snapshot("failure-visible-app");}catch{}await File.WriteAllTextAsync(Path.Combine(evidence,"failure.txt"),e.ToString());Console.WriteLine(e);throw;}
finally{if(app is not null&&!app.HasExited){app.Kill(entireProcessTree:true);app.WaitForExit(10000);}}
