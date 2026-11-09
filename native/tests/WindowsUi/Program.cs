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

if(args.Length!=3)throw new ArgumentException("Usage: WindowsUi <published-directory> <http-loopback-origin> <evidence-directory>");
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
try{
    if(!Environment.UserInteractive)throw new Exception("Runner has no interactive Windows desktop. UI smoke requires an already configured interactive runner; no desktop/security settings will be changed.");
    var email=$"windows-ui-{Guid.NewGuid():N}@example.invalid";var password="Synthetic-Windows-Ui-Only-42!";
    await Post("/api/auth/register",new(){["email"]=email,["password"]=password});var login=await Post("/api/auth/login",new(){["email"]=email,["password"]=password});http.DefaultRequestHeaders.Authorization=new AuthenticationHeaderValue("Bearer",login["token"]!.GetValue<string>());
    var first=await Post("/api/companies",new(){["name"]="Windows UI Alpha",["tax_mode"]="unregistered",["state_code"]="27"});var second=await Post("/api/companies",new(){["name"]="Windows UI Beta",["tax_mode"]="unregistered",["state_code"]="27"});
    var cid=second["id"]!.GetValue<string>();var date=DateTimeOffset.UtcNow.ToOffset(TimeSpan.FromMinutes(330)).ToString("yyyy-MM-dd");
    var invoice=await Post($"/api/companies/{cid}/records",new(){["kind"]="sales_invoice",["name"]="Synthetic UI Buyer",["date"]=date,["data"]=new JsonObject{["lines"]=new JsonArray(new JsonObject{["description"]="Synthetic UI service",["quantity"]="1",["rate"]="100",["gst_rate"]="0"})}});
    var evidenceBill=await Post($"/api/companies/{cid}/records",new(){["kind"]="purchase_bill",["name"]="Synthetic UI Evidence Supplier",["date"]=date,["data"]=new JsonObject{["lines"]=new JsonArray(new JsonObject{["description"]="Receipt evidence fixture",["quantity"]="1",["rate"]="75",["gst_rate"]="0"})}});
    var evidenceBytes=Encoding.ASCII.GetBytes("%PDF-1.4\n% Deliberately synthetic Windows UI receipt\n%%EOF\n");var evidenceFile=Path.Combine(evidence,"synthetic-ui-receipt.pdf");await File.WriteAllBytesAsync(evidenceFile,evidenceBytes);
    Check("synthetic loopback companies and invoice seeded");
    var start=new ProcessStartInfo(Path.Combine(publish,"ApexBooks.Windows.exe")){WorkingDirectory=publish,UseShellExecute=false};start.Environment["APEX_BOOKS_API_ORIGIN"]=origin.GetLeftPart(UriPartial.Authority);app=Process.Start(start)??throw new Exception("Could not launch unpackaged WinUI executable.");
    window=Wait(()=>AutomationElement.RootElement.FindFirst(TreeScope.Children,new PropertyCondition(AutomationElement.ProcessIdProperty,app.Id)),"WinUI app window");Check("actual unpackaged Debug WinUI window launched");
    var emailBox=Wait(()=>window.FindAll(TreeScope.Descendants,new PropertyCondition(AutomationElement.ControlTypeProperty,ControlType.Edit)).Cast<AutomationElement>().FirstOrDefault(x=>!x.Current.IsPassword),"email input");
    var passwordBox=Wait(()=>window.FindAll(TreeScope.Descendants,new PropertyCondition(AutomationElement.ControlTypeProperty,ControlType.Edit)).Cast<AutomationElement>().FirstOrDefault(x=>x.Current.IsPassword),"password input");
    Set(emailBox,email);Set(passwordBox,password);Invoke(Wait(()=>Find("Sign in",ControlType.Button),"Sign in button"));
    Wait(()=>Find("Business overview"),"authenticated dashboard");Check("real login controls completed sign-in");
    var combo=Wait(()=>window.FindFirst(TreeScope.Descendants,new PropertyCondition(AutomationElement.ControlTypeProperty,ControlType.ComboBox)),"company picker");
    void SelectCompany(string name){((ExpandCollapsePattern)combo.GetCurrentPattern(ExpandCollapsePattern.Pattern)).Expand();var choice=Wait(()=>window.FindAll(TreeScope.Descendants,Condition.TrueCondition).Cast<AutomationElement>().FirstOrDefault(x=>x.Current.Name.StartsWith(name+" ·",StringComparison.Ordinal)&&x.TryGetCurrentPattern(SelectionItemPattern.Pattern,out _)),name+" picker item");Invoke(choice);}
    SelectCompany("Windows UI Alpha");Thread.Sleep(500);SelectCompany("Windows UI Beta");
    Wait(()=>Find("Windows UI Beta"),"Beta workspace heading after company switch");
    Wait(()=>Find("Sales & collections  ↗",ControlType.Button),"company dashboard ready");Snapshot("01-company-dashboard");Check("company picker selected synthetic Beta workspace");
    // Resize the genuine app window; browser emulation cannot verify native reflow.
    var originalBounds=window.Current.BoundingRectangle;
    Check("native window supports standard resize automation",window.TryGetCurrentPattern(TransformPattern.Pattern,out var resizePattern)&&((TransformPattern)resizePattern).Current.CanResize);
    var transform=(TransformPattern)resizePattern;
    try{
        transform.Resize(800,800);
        var narrowCreate=Wait(()=>ReadyButton("+  Create"),"visible Create action in narrow window");
        var narrowSearch=Wait(()=>Find("Search all records and sections"),"search in narrow window");
        var bounds=window.Current.BoundingRectangle;
        Check("narrow header controls stay within the app window",new[]{narrowCreate,narrowSearch}.All(control=>!control.Current.IsOffscreen&&control.Current.BoundingRectangle.Left>=bounds.Left&&control.Current.BoundingRectangle.Right<=bounds.Right));
        Snapshot("01b-narrow-dashboard");
    }finally{transform.Resize(originalBounds.Width,originalBounds.Height);}
    Invoke(Wait(()=>Find("Sales & collections  ↗",ControlType.Button),"sales register shortcut"));var number=invoice["number"]!.GetValue<string>();Invoke(Wait(()=>Find(number,ControlType.Button),"seeded invoice in register"));
    Wait(()=>Find("Synthetic UI Buyer"),"invoice detail buyer");Wait(()=>Find("Record payment received",ControlType.Button),"invoice collection context action");Snapshot("02-invoice-detail");Dump();Check("real register opened invoice detail with collection action");
    Invoke(Wait(()=>Find("Done",ControlType.Button),"close seeded invoice detail"));
    Invoke(Wait(()=>Find("Add sales invoice",ControlType.Button),"create invoice from register"));
    var reference="UI"+Guid.NewGuid().ToString("N")[..8].ToUpperInvariant();const string createdBuyer="UI Created Partial-Payment Buyer";
    Set(Wait(()=>EditField("Customer / supplier"),"invoice customer"),createdBuyer);
    Set(Wait(()=>EditField("Reference number"),"invoice reference"),reference);
    var itemSelector=Wait(()=>EditField("Item / service"),"visible invoice item selector");
    // Confirm keyboard ownership and acknowledge each visible edit before sending more.
    // Never blindly repeat a whole string after uncertain keyboard delivery.
    bool ItemHasFocus()=>itemSelector.Current.HasKeyboardFocus||itemSelector.FindFirst(TreeScope.Descendants,new PropertyCondition(AutomationElement.HasKeyboardFocusProperty,true)) is not null;
    var typingDeadline=Stopwatch.StartNew();
    void AwaitItemValue(string expected,string phase)
    {
        while(typingDeadline.Elapsed<TimeSpan.FromSeconds(30)){
            if(Value(itemSelector)==expected)return;
            if(!ItemHasFocus())throw new Exception($"Item selector lost keyboard focus during {phase}; observed synthetic value: '{Value(itemSelector)}'");
            Thread.Sleep(25);
        }
        throw new Exception($"Item selector keyboard timeout during {phase}; expected '{expected}', observed '{Value(itemSelector)}'");
    }
    itemSelector.SetFocus();Wait(()=>ItemHasFocus()?itemSelector:null,"item selector owns keyboard focus",10);
    System.Windows.Forms.SendKeys.SendWait("^a");System.Windows.Forms.SendKeys.SendWait("{BACKSPACE}");AwaitItemValue("","clear");
    const string itemDescription="Invoice created through Windows UI";var entered="";
    foreach(var character in itemDescription){
        if(!ItemHasFocus())throw new Exception("Item selector lost keyboard focus before next character; refusing to type into another control.");
        System.Windows.Forms.SendKeys.SendWait(character.ToString());entered+=character;AwaitItemValue(entered,"character "+entered.Length);
    }
    Check("item selector contains the exact complete text before Tab",Value(itemSelector)==itemDescription);
    // A second, continuous burst is mandatory: paced entry must not hide dropped
    // fast typing or an application control replacement during TextChanged.
    var originalItemRuntimeId=itemSelector.GetRuntimeId();typingDeadline.Restart();
    System.Windows.Forms.SendKeys.SendWait("^a");System.Windows.Forms.SendKeys.SendWait("{BACKSPACE}");AwaitItemValue("","rapid-entry clear");
    if(!ItemHasFocus())throw new Exception("Item selector lost focus before rapid typing.");
    System.Windows.Forms.SendKeys.SendWait(itemDescription);AwaitItemValue(itemDescription,"continuous rapid typing");
    var currentItem=Wait(()=>EditField("Item / service"),"same item selector after rapid typing");
    Check("rapid typing retains exact text, keyboard focus and control identity",Value(currentItem)==itemDescription&&ItemHasFocus()&&originalItemRuntimeId.SequenceEqual(currentItem.GetRuntimeId()));
    System.Windows.Forms.SendKeys.SendWait("{TAB}");
    Wait(()=>!ItemHasFocus()?itemSelector:null,"item selector commits on Tab",10);
    Check("visible item selector accepted genuine user text",Value(itemSelector)==itemDescription);
    Set(Wait(()=>EditField("Quantity"),"invoice line quantity"),"1");
    Set(Wait(()=>EditField("Rate (₹)"),"invoice line rate"),"250");
    Wait(()=>window.FindAll(TreeScope.Descendants,new PropertyCondition(AutomationElement.ControlTypeProperty,ControlType.Text)).Cast<AutomationElement>().FirstOrDefault(e=>e.Current.Name.StartsWith("Subtotal ",StringComparison.Ordinal)&&e.Current.Name.Contains("Total ",StringComparison.Ordinal)),"server-calculated invoice preview");
    Snapshot("03-invoice-form");Invoke(Wait(()=>Find("Save invoice",ControlType.Button),"save invoice button"));
    Wait(()=>Find("Save invoice",ControlType.Button) is null?window:null,"invoice form saved and closed");
    // Saving a new customer document opens its detail automatically. Close the
    // foreground dialog before invoking a register row through UI Automation.
    Wait(()=>Find("Transaction details"),"post-save transaction detail");
    Invoke(Wait(()=>ReadyButton("Done"),"return from post-save detail"));
    Wait(()=>Find("Transaction details") is null?window:null,"post-save detail closed");
    var createdRows=await CompanyRecords(cid);var created=createdRows.OfType<JsonObject>().SingleOrDefault(r=>r["number"]?.ToString()==reference)??throw new Exception("UI invoice did not appear in canonical records.");
    var createdId=created["id"]!.GetValue<string>();
    Check("invoice was created through the real form exactly once",createdRows.OfType<JsonObject>().Count(r=>r["number"]?.ToString()==reference)==1&&created["name"]?.ToString()==createdBuyer&&Number(created,"amount")==250&&Number(created,"outstanding")==250);
    Invoke(Wait(()=>Find(reference,ControlType.Button),"UI-created invoice register row"));Wait(()=>Find(createdBuyer),"UI-created invoice detail");
    Invoke(Wait(()=>Find("Record payment received",ControlType.Button),"collect partial invoice payment"));
    Set(Wait(()=>EditField("Amount (₹)"),"receipt amount"),"100");
    Set(Wait(()=>EditField("Allocated (₹)"),"invoice allocation amount"),"100");
    Snapshot("04-partial-collection-form");Invoke(Wait(()=>Find("Post payment",ControlType.Button),"post partial receipt"));
    Wait(()=>Find("Post payment",ControlType.Button) is null?window:null,"receipt form saved and closed");
    var detail=await Get($"/api/companies/{cid}/records/{createdId}");var afterReceipt=await CompanyRecords(cid);var receipts=afterReceipt.OfType<JsonObject>().Where(r=>r["kind"]?.ToString()=="payment_in"&&r["name"]?.ToString()==createdBuyer).ToArray();
    Check("partial collection has one receipt and exact canonical balance",receipts.Length==1&&Number(receipts[0],"amount")==100&&Number(detail,"amount")==250&&Number(detail,"outstanding")==150);
    var receipt=await Get($"/api/companies/{cid}/records/{receipts[0]["id"]!.GetValue<string>()}");var allocations=(receipt["allocations"] as JsonArray)??(receipt["data"]?["allocations"] as JsonArray)??new JsonArray();
    Check("receipt is allocated to the UI-created invoice exactly once",allocations.Count==1&&allocations[0]?["document_id"]?.ToString()==createdId&&Number(allocations[0],"amount")==100);
    Invoke(Wait(()=>Find(reference,ControlType.Button),"part-paid invoice in refreshed register"));Wait(()=>Find(createdBuyer),"part-paid invoice detail");Snapshot("05-part-paid-detail");Invoke(Wait(()=>Find("Done",ControlType.Button),"close part-paid detail"));
    Invoke(Wait(()=>Find("Add sales invoice",ControlType.Button),"new invoice for dirty draft test"));
    const string discardedBuyer="UI Discarded Draft Must Not Post";Set(Wait(()=>EditField("Customer / supplier"),"dirty draft customer"),discardedBuyer);
    Invoke(Wait(()=>Find("Cancel",ControlType.Button),"cancel dirty invoice"));Wait(()=>Find("Discard unsaved changes?"),"dirty-draft confirmation");Snapshot("06-dirty-draft-guard");
    Invoke(Wait(()=>Find("Keep editing",ControlType.Button),"keep dirty draft"));
    Check("Keep editing preserves the unsaved customer",Value(Wait(()=>EditField("Customer / supplier"),"retained draft customer"))==discardedBuyer);
    Invoke(Wait(()=>Find("Cancel",ControlType.Button),"cancel dirty invoice again"));Invoke(Wait(()=>Find("Discard draft",ControlType.Button),"confirm discard"));
    Wait(()=>Find("Save invoice",ControlType.Button) is null?window:null,"discarded invoice editor closed");
    var finalRecords=await CompanyRecords(cid);
    Check("discarded UI draft created no accounting record",!finalRecords.OfType<JsonObject>().Any(r=>r["name"]?.ToString()==discardedBuyer));
    await File.WriteAllTextAsync(Path.Combine(evidence,"canonical-verification.json"),new JsonObject{["invoice_id"]=createdId,["invoice_number"]=reference,["amount"]=Number(detail,"amount"),["outstanding"]=Number(detail,"outstanding"),["payment_count"]=receipts.Length,["allocated_amount"]=Number(allocations[0],"amount"),["discarded_record_count"]=0}.ToJsonString());
    AutomationElement NavigationItem(string label)=>Wait(()=>window.FindAll(TreeScope.Descendants,Condition.TrueCondition).Cast<AutomationElement>().FirstOrDefault(e=>e.Current.Name==label&&(e.TryGetCurrentPattern(SelectionItemPattern.Pattern,out _)||e.TryGetCurrentPattern(InvokePattern.Pattern,out _))),label+" navigation");
    Invoke(NavigationItem("Dashboard"));Invoke(Wait(()=>Find("Purchases  ↗",ControlType.Button),"purchase register shortcut"));
    Invoke(Wait(()=>Find(evidenceBill["number"]!.GetValue<string>(),ControlType.Button),"synthetic purchase bill row"));Invoke(Wait(()=>Find("Retained receipts",ControlType.Button),"purchase bill retained evidence action"));
    Wait(()=>Find("No retained receipts. Upload original evidence to keep it with this transaction."),"empty receipt panel");Invoke(Wait(()=>Find("Choose receipt and upload",ControlType.Button),"native receipt upload action"));
    // Genuine system picker interaction; no hidden app state or direct upload API substitution.
    // Hosted Windows evidence shows this owned dialog nested beneath the app, not a desktop child.
    var picker=Wait(()=>window.FindAll(TreeScope.Descendants,new PropertyCondition(AutomationElement.ControlTypeProperty,ControlType.Window)).Cast<AutomationElement>().FirstOrDefault(e=>e.Current.Name=="Open"&&!e.Current.IsOffscreen),"owned system Open file picker inside app UIA tree");
    var filename=Wait(()=>picker.FindAll(TreeScope.Descendants,new PropertyCondition(AutomationElement.ControlTypeProperty,ControlType.Edit)).Cast<AutomationElement>().FirstOrDefault(e=>(e.Current.Name is "File name:" or "File name"||e.Current.AutomationId=="1148")&&e.TryGetCurrentPattern(ValuePattern.Pattern,out _)),"system picker File name field");Set(filename,evidenceFile);
    Invoke(Wait(()=>picker.FindAll(TreeScope.Descendants,new PropertyCondition(AutomationElement.ControlTypeProperty,ControlType.Button)).Cast<AutomationElement>().FirstOrDefault(e=>e.Current.Name=="Open"&&e.Current.IsEnabled),"system picker Open button"));
    Wait(()=>Find("Archive retained receipt",ControlType.Button),"receipt uploaded through system picker");Snapshot("07-retained-receipt");
    var evidencePath=$"/api/companies/{cid}/records/{evidenceBill["id"]!.GetValue<string>()}/attachments";var uploaded=(await Get(evidencePath))["attachments"]!.AsArray();var expectedSha=Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(evidenceBytes)).ToLowerInvariant();
    Check("real receipt picker uploaded exactly one matching retained file",uploaded.Count==1&&uploaded[0]?["sha256"]?.ToString()==expectedSha&&Number(uploaded[0],"size_bytes")==evidenceBytes.Length);
    Invoke(Wait(()=>Find("Archive retained receipt",ControlType.Button),"archive receipt through UI"));Wait(()=>Find("Reactivate retained receipt",ControlType.Button),"archived receipt UI state");var archived=(await Get(evidencePath))["attachments"]!.AsArray();Check("archive UI retains the original evidence bytes and lineage",archived.Count==1&&archived[0]?["is_archived"]?.GetValue<bool>()==true&&archived[0]?["sha256"]?.ToString()==expectedSha);Snapshot("08-archived-receipt");
    Invoke(Wait(()=>Find("Done",ControlType.Button),"close retained receipt panel"));Invoke(NavigationItem("Settings"));Set(Wait(()=>EditField("Find a setting, for example logo, Vyapar or prefixes"),"Settings search"),"Download backup");Invoke(Wait(()=>ReadyButton("Download backup"),"settings complete backup entry"));Wait(()=>Find("Complete portable backup"),"complete backup dialog");Wait(()=>ReadyButton("Verify and save backup"),"complete backup explicit save action");Snapshot("09-complete-backup-entry");Check("complete backup is discoverable after retaining receipt evidence");
    var reportQuery=$"?from_date={date}&to_date={date}";
    var sourceSummary=await Get($"/api/companies/{cid}/reports/summary{reportQuery}");
    var sourceFinancial=await Get($"/api/companies/{cid}/reports/financial{reportQuery}");
    var sourceRecords=await CompanyRecords(cid);var sourceCompanies=(await Get("/api/companies")).AsArray();
    const string backupPassword="Synthetic-UI-Backup-Only-42!";
    var backupPath=Path.Combine(evidence,"synthetic-encrypted-roundtrip.apexbackup");
    Check("backup destination is fresh",!File.Exists(backupPath));
    var encryption=Wait(()=>Find("Encrypt portable backup locally (recommended)",ControlType.CheckBox),"local encryption option");
    Check("local encryption is selected by default",((TogglePattern)encryption.GetCurrentPattern(TogglePattern.Pattern)).Current.ToggleState==ToggleState.On);
    Set(Wait(()=>EditField("Backup password · at least 12 characters"),"export password"),backupPassword);
    Invoke(Wait(()=>ReadyButton("Verify and save backup"),"verified encrypted export"));
    ChooseNativeFile("Save As","Save",backupPath);
    Wait(()=>Find("Verify and save backup",ControlType.Button) is null&&File.Exists(backupPath)?window:null,"encrypted backup saved and dialog closed",120);
    var envelope=JsonNode.Parse(await File.ReadAllTextAsync(backupPath))!.AsObject();
    Check("actual Save picker produced encrypted v1 envelope",envelope["format"]?.ToString()=="apex-encrypted-backup"&&Number(envelope,"version")==1&&envelope["ciphertext"] is JsonValue);
    Snapshot("10-encrypted-export-saved");
    Set(Wait(()=>EditField("Find a setting, for example logo, Vyapar or prefixes"),"Settings search after export"),"Restore company backup");
    Invoke(Wait(()=>ReadyButton("Restore company backup"),"restore from Settings"));
    ChooseNativeFile("Open","Open",backupPath);
    Wait(()=>Find("Restore complete backup into a new company"),"restore encrypted backup dialog");
    var restoredName="Windows UI Restored "+Guid.NewGuid().ToString("N")[..8];
    Set(Wait(()=>EditField("Name for the NEW restored company"),"new restored company name"),restoredName);
    Set(Wait(()=>EditField("Encrypted backup passphrase"),"restore passphrase"),backupPassword);
    var encryptedImport=Wait(()=>Find("This file uses Apex encrypted-backup v1",ControlType.CheckBox),"encrypted import mode");
    Check("encrypted file is recognized without plaintext fallback",((TogglePattern)encryptedImport.GetCurrentPattern(TogglePattern.Pattern)).Current.ToggleState==ToggleState.On);
    Invoke(Wait(()=>ReadyButton("Validate / resume and preview"),"authenticate upload and preview"));
    Wait(()=>window.FindAll(TreeScope.Descendants,new PropertyCondition(AutomationElement.ControlTypeProperty,ControlType.Text)).Cast<AutomationElement>().FirstOrDefault(e=>e.Current.Name.Contains("Complete SHA256 verified. Review below",StringComparison.Ordinal)),"authenticated immutable preview",120);
    Check("preview has not created a company",(await Get("/api/companies")).AsArray().Count==sourceCompanies.Count);
    Snapshot("11-restore-reviewed-preview");
    Invoke(Wait(()=>ReadyButton("Restore reviewed backup"),"explicit new-company restore"));
    Wait(()=>Find("Restore reviewed backup",ControlType.Button) is null?Find(restoredName):null,"restore dialog closed and new company loaded",120);Invoke(NavigationItem("Dashboard"));Wait(()=>Find("Business overview"),"restored dashboard");Wait(()=>ReadyButton("Sales & collections  ↗"),"restored company data ready",120);Snapshot("12-restored-company-dashboard");
    var companiesAfter=(await Get("/api/companies")).AsArray();var restoredCompany=companiesAfter.OfType<JsonObject>().Single(c=>c["name"]?.ToString()==restoredName);var restoredCid=restoredCompany["id"]!.GetValue<string>();
    Check("explicit restore created exactly one distinct company",companiesAfter.Count==sourceCompanies.Count+1&&restoredCid!=cid);
    var restoredSummary=await Get($"/api/companies/{restoredCid}/reports/summary{reportQuery}");var restoredFinancial=await Get($"/api/companies/{restoredCid}/reports/financial{reportQuery}");
    Check("restored canonical summary and financial accounts match source",JsonNode.DeepEquals(sourceSummary,restoredSummary)&&JsonNode.DeepEquals(sourceFinancial,restoredFinancial));
    var restoredRecords=await CompanyRecords(restoredCid);var restoredInvoice=restoredRecords.OfType<JsonObject>().Single(r=>r["number"]?.ToString()==reference);
    Check("restored invoice retains partial settlement",Number(restoredInvoice,"amount")==250&&Number(restoredInvoice,"outstanding")==150);
    var restoredBill=restoredRecords.OfType<JsonObject>().Single(r=>r["kind"]?.ToString()=="purchase_bill"&&r["number"]?.ToString()==evidenceBill["number"]?.ToString());
    var restoredAttachments=(await Get($"/api/companies/{restoredCid}/records/{restoredBill["id"]}/attachments"))["attachments"]!.AsArray();var retained=restoredAttachments.Single()!;
    Check("restored archived receipt preserves metadata",retained["is_archived"]?.GetValue<bool>()==true&&retained["sha256"]?.ToString()==expectedSha&&Number(retained,"size_bytes")==evidenceBytes.Length);
    using(var download=await http.GetAsync($"/api/companies/{restoredCid}/attachments/{retained["id"]}/download")){
        download.EnsureSuccessStatusCode();var bytes=await download.Content.ReadAsByteArrayAsync();Check("restored retained receipt bytes match original",bytes.SequenceEqual(evidenceBytes)&&Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(bytes)).ToLowerInvariant()==expectedSha);
    }
    Check("original company records and reports remain unchanged",JsonNode.DeepEquals(sourceRecords,await CompanyRecords(cid))&&JsonNode.DeepEquals(sourceSummary,await Get($"/api/companies/{cid}/reports/summary{reportQuery}"))&&JsonNode.DeepEquals(sourceFinancial,await Get($"/api/companies/{cid}/reports/financial{reportQuery}")));
    Check("original archived receipt remains unchanged",JsonNode.DeepEquals(archived,(await Get(evidencePath))["attachments"]));
    await File.WriteAllTextAsync(Path.Combine(evidence,"backup-roundtrip-verification.json"),new JsonObject{["source_company_id"]=cid,["restored_company_id"]=restoredCid,["encrypted_v1"]=true,["native_save_and_open_pickers"]=true,["summary"]=restoredSummary.DeepClone(),["financial"]=restoredFinancial.DeepClone(),["receipt_sha256"]=expectedSha,["receipt_bytes"]=evidenceBytes.Length,["original_unchanged"]=true}.ToJsonString());
    await File.WriteAllTextAsync(Path.Combine(evidence,"receipt-verification.json"),new JsonObject{["record_id"]=evidenceBill["id"]!.DeepClone(),["attachment_id"]=archived[0]?["id"]?.DeepClone(),["sha256"]=expectedSha,["is_archived"]=true,["ui_file_picker_used"]=true}.ToJsonString());
    Dump();
    await File.WriteAllTextAsync(Path.Combine(evidence,"result.json"),new JsonObject{["passed"]=true,["api_origin"]=origin.ToString(),["checks"]=new JsonArray(checks.Select(x=>(JsonNode)JsonValue.Create(x)!).ToArray())}.ToJsonString());
}catch(Exception e){try{Dump();Snapshot("failure-visible-app");}catch{}await File.WriteAllTextAsync(Path.Combine(evidence,"failure.txt"),e.ToString());throw;}
finally{if(app is not null&&!app.HasExited){app.Kill(entireProcessTree:true);app.WaitForExit(10000);}}
