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

if(args.Length is <3 or >4||args.Length==4&&args[3] is not ("--navigation-only" or "--workspace-only" or "--pos-only" or "--pos-split-only" or "--warehouse-only" or "--receiving-only" or "--inventory-only"))throw new ArgumentException("Usage: WindowsUi <published-directory> <http-loopback-origin> <evidence-directory> [--navigation-only|--workspace-only|--pos-only|--pos-split-only|--warehouse-only|--receiving-only|--inventory-only]");
var navigationOnly=args.Length==4&&args[3]=="--navigation-only";
var workspaceOnly=args.Length==4&&args[3]=="--workspace-only";
var posOnly=args.Length==4&&args[3] is "--pos-only" or "--pos-split-only";
var splitOnly=args.Length==4&&args[3]=="--pos-split-only";
var warehouseOnly=args.Length==4&&args[3]=="--warehouse-only";
var receivingOnly=args.Length==4&&args[3]=="--receiving-only";
var inventoryOnly=args.Length==4&&args[3]=="--inventory-only";
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
AutomationElement? Find(string name,ControlType? type=null){
    if(window is null)return null;
    foreach(AutomationElement element in window.FindAll(TreeScope.Descendants,Condition.TrueCondition)){
        // Closing a native dialog can dispose descendants after FindAll returns.
        // Re-query on the next wait iteration rather than retaining those nodes.
        try{if(element.Current.Name==name&&(type is null||element.Current.ControlType==type))return element;}
        catch(ElementNotAvailableException){}
    }
    return null;
}
AutomationElement? ReadyButton(string label){try{var button=Find(label,ControlType.Button);return button is not null&&button.Current.IsEnabled&&!button.Current.IsOffscreen?button:null;}catch(ElementNotAvailableException){return null;}}
AutomationElement? RevealButton(string label){
    var button=Find(label,ControlType.Button);if(button is null||!button.Current.IsEnabled)return null;
    if(button.Current.IsOffscreen){
        if(button.TryGetCurrentPattern(ScrollItemPattern.Pattern,out var scroll))((ScrollItemPattern)scroll).ScrollIntoView();
        else button.SetFocus();
    }
    return !button.Current.IsOffscreen?button:null;
}
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
void PressKeys(string keys)
{
    var previous = SynchronizationContext.Current;
    try { System.Windows.Forms.SendKeys.SendWait(keys); }
    finally { SynchronizationContext.SetSynchronizationContext(previous); }
}
// Preserve the user's lock-key state while sending the exact synthetic text.
string KeyboardLiteral(string value){
    var caps=System.Windows.Forms.Control.IsKeyLocked(System.Windows.Forms.Keys.CapsLock);
    return string.Concat(value.Select(c=>{
        if(caps && c is >= 'a' and <= 'z')c=char.ToUpperInvariant(c);
        else if(caps && c is >= 'A' and <= 'Z')c=char.ToLowerInvariant(c);
        return c switch{'{'=>"{{}",'}'=>"{}}",'+' or '^' or '%' or '~' or '(' or ')'=>"{"+c+"}",_=>c.ToString()};
    }));
}
void ChooseNativeFile(string title,string action,string path)
{
    var dialog=Wait(()=>window?.FindAll(TreeScope.Descendants,new PropertyCondition(AutomationElement.ControlTypeProperty,ControlType.Window)).Cast<AutomationElement>().FirstOrDefault(e=>e.Current.Name==title&&!e.Current.IsOffscreen),"owned system "+title+" picker",120);
    var field=Wait(()=>dialog.FindAll(TreeScope.Descendants,new PropertyCondition(AutomationElement.ControlTypeProperty,ControlType.Edit)).Cast<AutomationElement>().FirstOrDefault(e=>(e.Current.Name is "File name:" or "File name"||e.Current.AutomationId=="1148")&&e.TryGetCurrentPattern(ValuePattern.Pattern,out _)),title+" File name");
    if(action=="Save"){
        // ValuePattern can change the shell edit's displayed text without
        // updating its selected filename. Use genuine keyboard input and commit
        // the edit before activating Save. No retry after activation.
        field.SetFocus();Wait(()=>field.Current.HasKeyboardFocus?field:null,"Save filename keyboard focus",10);
        PressKeys("^a");PressKeys("{BACKSPACE}");
        Wait(()=>Value(field)==""?field:null,"Save filename cleared",10);
        var typed="";var deadline=Stopwatch.StartNew();
        foreach(var character in path){
            if(deadline.Elapsed>TimeSpan.FromSeconds(30)||!field.Current.HasKeyboardFocus)throw new Exception("Save filename lost focus or exceeded typing deadline.");
            var key=KeyboardLiteral(character.ToString());
            PressKeys(key);typed+=character;
            Wait(()=>Value(field)==typed?field:null,"Save filename character "+typed.Length,5);
        }
        Check("Save filename keyboard entry matches exact destination",Value(field)==path);
        PressKeys("{TAB}");
        Wait(()=>!field.Current.HasKeyboardFocus?field:null,"Save filename committed on Tab",10);
    }else Set(field,path);
    Check(title+" picker contains exact requested path",Value(field)==path);
    if(action=="Open"){
        field.SetFocus();Wait(()=>field.Current.HasKeyboardFocus?field:null,"Open filename keyboard focus",10);
        PressKeys("{ENTER}");return;
    }
    var confirm=Wait(()=>dialog.FindAll(TreeScope.Descendants,new PropertyCondition(AutomationElement.ControlTypeProperty,ControlType.Button)).Cast<AutomationElement>().FirstOrDefault(e=>e.Current.Name==action&&e.Current.IsEnabled),title+" "+action+" button");
    if(action=="Save"){
        // Shell Save can make outgoing COM calls. UIA Invoke dispatches a
        // synchronous input call and produced RPC_E_CANTCALLOUT_ININPUTSYNCCALL
        // on the hosted runner. Use one genuine keyboard activation instead.
        confirm.SetFocus();Wait(()=>confirm.Current.HasKeyboardFocus?confirm:null,"native Save button keyboard focus",10);
        Check("committed Save destination survives button focus",Value(field)==path);
        Snapshot("10-native-save-destination");
        PressKeys(" ");
    }else Invoke(confirm);
}
void Snapshot(string name){if(window is null)return;var handle=new IntPtr(window.Current.NativeWindowHandle);
    if(workspaceOnly||posOnly||warehouseOnly||receivingOnly||inventoryOnly){
        NativeWindowCapture.SetForegroundWindow(handle);
        NativeWindowCapture.DwmFlush();
        Thread.Sleep(300);
    }
    var rectangle=window.Current.BoundingRectangle;if(rectangle.Width<1||rectangle.Height<1)throw new Exception("App has no visible capture rectangle.");using var bitmap=new Drawing.Bitmap((int)rectangle.Width,(int)rectangle.Height);using(var graphics=Drawing.Graphics.FromImage(bitmap)){
        var dc=graphics.GetHdc();
        try{if(!NativeWindowCapture.PrintWindow(handle,dc,2)){Console.WriteLine("App-window capture unavailable: "+name);return;}}
        finally{graphics.ReleaseHdc(dc);}
    }bitmap.Save(Path.Combine(evidence,name+".png"),Drawing.Imaging.ImageFormat.Png);
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
    const string posBarcode="01234567890";
    var storefrontItemId="";
    JsonObject? purchaseOrder=null;
    if(workspaceOnly||posOnly||warehouseOnly||receivingOnly)
    {
        var product=await Post($"/api/companies/{cid}/records",new(){["kind"]="item",["name"]="Storefront oats",
            ["data"]=new JsonObject{["barcode"]=posBarcode,["sale_rate"]="125",["track_stock"]=true,["unit"]="pack"}});
        storefrontItemId=product["id"]!.ToString();
        await Post($"/api/companies/{cid}/stock/opening",new(){["item_id"]=storefrontItemId,
            ["date"]=date,["quantity"]="2",["unit_cost"]="50"});
        if(receivingOnly)
            purchaseOrder=await Post($"/api/companies/{cid}/records",new(){["kind"]="purchase_order",["name"]="Storefront supplier",
                ["date"]=date,["data"]=new JsonObject{["place_of_supply"]="27",["supplier_state"]="27",["lines"]=new JsonArray(
                    new JsonObject{["description"]="Storefront oats",["item_id"]=storefrontItemId,["quantity"]="3",
                        ["unit"]="pack",["rate"]="50",["gst_rate"]="0"})}});
    }
    if(inventoryOnly)
    {
        using var setupResponse=await http.PutAsync($"/api/companies/{cid}/inventory-setup",new StringContent(new JsonObject{["version"]=0,["automobile_enabled"]=true,
            ["locations"]=new JsonArray(new JsonObject{["name"]="Rack 1",["active"]=true},new JsonObject{["name"]="Rack 2",["active"]=true}),
            ["vehicle_added"]=new JsonArray(),["vehicle_hidden_makes"]=new JsonArray(),["vehicle_hidden_models"]=new JsonArray()}.ToJsonString(),Encoding.UTF8,"application/json"));
        if(!setupResponse.IsSuccessStatusCode)throw new Exception("Synthetic inventory setup failed: "+await setupResponse.Content.ReadAsStringAsync());
        var setupBody=JsonNode.Parse(await setupResponse.Content.ReadAsStringAsync())!;var rack=setupBody["locations"]![0]!["id"]!.ToString();
        await Post($"/api/companies/{cid}/records",new(){["kind"]="item",["name"]="Brake pad set front",["data"]=new JsonObject{["sale_rate"]="1450",["location_ids"]=new JsonArray(rack),
            ["oem_number"]="55810-M68K00",["part_brand"]="Bosch",["part_grade"]="aftermarket",["vehicle_fitment"]=new JsonArray(new JsonObject{["make"]="Maruti Suzuki",["model"]="Swift",["year_from"]=2011,["year_to"]=2017})}});
    }
    var invoice=await Post($"/api/companies/{cid}/records",new(){["kind"]="sales_invoice",["name"]="Synthetic UI Buyer",["date"]=date,["data"]=new JsonObject{["lines"]=new JsonArray(new JsonObject{["description"]="Synthetic UI service",["quantity"]="1",["rate"]="100",["gst_rate"]="0"})}});
    var evidenceBill=await Post($"/api/companies/{cid}/records",new(){["kind"]="purchase_bill",["name"]="Synthetic UI Evidence Supplier",["date"]=date,["data"]=new JsonObject{["lines"]=new JsonArray(new JsonObject{["description"]="Receipt evidence fixture",["quantity"]="1",["rate"]="75",["gst_rate"]="0"})}});
    var evidenceBytes=Encoding.ASCII.GetBytes("%PDF-1.4\n% Deliberately synthetic Windows UI receipt\n%%EOF\n");var evidenceFile=Path.Combine(evidence,"synthetic-ui-receipt.pdf");await File.WriteAllBytesAsync(evidenceFile,evidenceBytes);
    var quotationFixture=JsonNode.Parse(await File.ReadAllTextAsync(Path.Combine(AppContext.BaseDirectory,"quotation-nine-lines.json")))!.AsObject();
    var quoteCompany=await Post("/api/companies",new(){["name"]="Windows UI Quotation",["tax_mode"]="regular",["gstin"]="27AAAAA0000A1Z2",["state_code"]="27"});var quoteCid=quoteCompany["id"]!.ToString();
    var quoteBody=quotationFixture.DeepClone().AsObject();quoteBody.Remove("expected");quoteBody["kind"]="estimate";quoteBody["date"]=date;
    var seededQuote=await Post($"/api/companies/{quoteCid}/records",quoteBody);
    Check("synthetic loopback companies and invoice seeded");
    var start=new ProcessStartInfo(Path.Combine(publish,"ApexBooks.Windows.exe")){WorkingDirectory=publish,UseShellExecute=false};start.Environment["APEX_BOOKS_API_ORIGIN"]=origin.GetLeftPart(UriPartial.Authority);app=Process.Start(start)??throw new Exception("Could not launch unpackaged WinUI executable.");
    window=Wait(()=>AutomationElement.RootElement.FindFirst(TreeScope.Children,new PropertyCondition(AutomationElement.ProcessIdProperty,app.Id)),"WinUI app window");Check("actual unpackaged Debug WinUI window launched");
    var landing = Wait(() => Find("Sign in",ControlType.Button) ?? Find("Business overview"),"loopback sign-in or restored synthetic dashboard");
    if(landing.Current.Name=="Business overview")
    {
        var openPreviousNavigation=ReadyButton("Open Navigation");
        if(openPreviousNavigation is not null) Invoke(openPreviousNavigation);
        Invoke(Wait(()=>Find("Sign out"),"sign out the previous synthetic session"));
        Wait(()=>Find("Sign in",ControlType.Button),"fresh loopback sign-in");
    }
    var emailBox=Wait(()=>window.FindAll(TreeScope.Descendants,new PropertyCondition(AutomationElement.ControlTypeProperty,ControlType.Edit)).Cast<AutomationElement>().FirstOrDefault(x=>!x.Current.IsPassword),"email input");
    var passwordBox=Wait(()=>window.FindAll(TreeScope.Descendants,new PropertyCondition(AutomationElement.ControlTypeProperty,ControlType.Edit)).Cast<AutomationElement>().FirstOrDefault(x=>x.Current.IsPassword),"password input");
    Set(emailBox,email);Set(passwordBox,password);Invoke(Wait(()=>Find("Sign in",ControlType.Button),"Sign in button"));
    Wait(()=>Find("Business overview"),"authenticated dashboard");Check("real login controls completed sign-in");
    var openNavigation=ReadyButton("Open Navigation");if(openNavigation is not null)Invoke(openNavigation);
    var combo=Wait(()=>Find("Choose company",ControlType.ComboBox),"company picker in the visible navigation pane");
    void SelectCompany(string name){((ExpandCollapsePattern)combo.GetCurrentPattern(ExpandCollapsePattern.Pattern)).Expand();var choice=Wait(()=>window.FindAll(TreeScope.Descendants,Condition.TrueCondition).Cast<AutomationElement>().FirstOrDefault(x=>x.Current.Name.StartsWith(name+" ·",StringComparison.Ordinal)&&x.TryGetCurrentPattern(SelectionItemPattern.Pattern,out _)),name+" picker item");Invoke(choice);}
    SelectCompany("Windows UI Alpha");Thread.Sleep(500);SelectCompany("Windows UI Beta");
    var closeNavigation=ReadyButton("Close Navigation");if(closeNavigation is not null)Invoke(closeNavigation);
    Wait(()=>Find("Windows UI Beta"),"Beta workspace heading after company switch");
    Wait(()=>Find("Sales & collections  ↗",ControlType.Button),"company dashboard ready");Snapshot("01-company-dashboard");Check("company picker selected synthetic Beta workspace");
    // Resize the genuine app window; browser emulation cannot verify native reflow.
    if(window.TryGetCurrentPattern(WindowPattern.Pattern,out var windowPattern)){
        var frame=(WindowPattern)windowPattern;
        Console.WriteLine("Native window state before resize: "+frame.Current.WindowVisualState+" / "+frame.Current.WindowInteractionState);
        if(frame.Current.WindowVisualState!=WindowVisualState.Normal)frame.SetWindowVisualState(WindowVisualState.Normal);
    }
    Wait(()=>window.TryGetCurrentPattern(TransformPattern.Pattern,out var pattern)&&((TransformPattern)pattern).Current.CanResize?window:null,"resizable normal app window after navigation closes");
    var originalBounds=window.Current.BoundingRectangle;
    var transform=(TransformPattern)window.GetCurrentPattern(TransformPattern.Pattern);
    Check("native window supports standard resize automation",transform.Current.CanResize);
    try{
        transform.Resize(800,800);
        var narrowCreate=Wait(()=>ReadyButton("+  Create"),"visible Create action in narrow window");
        var narrowSearch=Wait(()=>Find("Search all records and sections"),"search in narrow window");
        var bounds=window.Current.BoundingRectangle;
        Check("narrow header controls stay within the app window",new[]{narrowCreate,narrowSearch}.All(control=>!control.Current.IsOffscreen&&control.Current.BoundingRectangle.Left>=bounds.Left&&control.Current.BoundingRectangle.Right<=bounds.Right));
        if(workspaceOnly)
        {
            var narrowPos=Wait(()=>ReadyButton("Open POS"),"POS shortcut visible without scrolling at 800px");
            var narrowStock=Wait(()=>ReadyButton("Review stock"),"stock shortcut visible without scrolling at 800px");
            var salesMetric=Wait(()=>Find("Net sales",ControlType.Text),"net sales dashboard metric");
            Check("narrow dashboard shows POS and stock before financial metrics",new[]{narrowPos,narrowStock}.All(control=>control.Current.BoundingRectangle.Bottom<salesMetric.Current.BoundingRectangle.Top));
        }
        Snapshot("01b-narrow-dashboard");
        if(navigationOnly){
            var toggle=Wait(()=>ReadyButton("Open Navigation"),"compact navigation toggle");
            var companyHeading=Wait(()=>Find("Windows UI Beta",ControlType.Text),"compact company heading");
            var toggleBounds=toggle.Current.BoundingRectangle;var companyBounds=companyHeading.Current.BoundingRectangle;
            Check("compact toggle has separate space from company title",toggleBounds.Right<=companyBounds.Left||toggleBounds.Bottom<=companyBounds.Top);
            toggle.SetFocus();PressKeys(" ");
            var close=Wait(()=>ReadyButton("Close Navigation"),"keyboard opened compact navigation");
            Check("keyboard opens company navigation",!Find("Choose company",ControlType.ComboBox)!.Current.IsOffscreen);
            close.SetFocus();PressKeys(" ");
            Wait(()=>ReadyButton("Open Navigation"),"keyboard closed compact navigation");
            Wait(()=>Find("Choose company",ControlType.ComboBox) is not { Current.IsOffscreen:false }?window:null,"company navigation is hidden after closing");
            Check("keyboard closes compact navigation");Thread.Sleep(350);Snapshot("01c-compact-toggle-verified");
        }
    }finally{transform.Resize(originalBounds.Width,originalBounds.Height);}
    if(navigationOnly){
        var handle=new IntPtr(window.Current.NativeWindowHandle);var scale=Math.Max(1d,NativeWindowCapture.GetDpiForWindow(handle)/96d);
        try{
            NativeWindowCapture.SetWindowPos(handle,IntPtr.Zero,0,0,(int)Math.Round(1280*scale),(int)Math.Round(900*scale),0x16);
            Thread.Sleep(750);Console.WriteLine("Requested logical desktop size 1280x900; actual physical bounds "+window.Current.BoundingRectangle);Snapshot("01d-desktop-dashboard");
        }finally{transform.Resize(originalBounds.Width,originalBounds.Height);}
        await File.WriteAllTextAsync(Path.Combine(evidence,"result.json"),new JsonObject{["passed"]=true,["scope"]="navigation-only",["checks"]=new JsonArray(checks.Select(x=>(JsonNode)JsonValue.Create(x)!).ToArray())}.ToJsonString());return;
    }
    if(workspaceOnly)
    {
        var open=ReadyButton("Open Navigation");if(open is not null)Invoke(open);
        var sales=Find("Sales");
        if(sales?.TryGetCurrentPattern(ExpandCollapsePattern.Pattern,out var expandable)==true)
            ((ExpandCollapsePattern)expandable).Collapse();
        var pos=Wait(()=>window.FindAll(TreeScope.Descendants,Condition.TrueCondition).Cast<AutomationElement>()
            .FirstOrDefault(element=>element.Current.Name=="POS"&&element.TryGetCurrentPattern(SelectionItemPattern.Pattern,out _)),"POS without expanding Sales");
        Invoke(pos);
        var close=ReadyButton("Close Navigation");if(close is not null)Invoke(close);
        Wait(()=>EditField("Search products / scan barcode"),"POS scanner field");
        Check("top-level POS opens directly with Sales collapsed");
        Invoke(NavigationItem("Dashboard"));
        Invoke(Wait(()=>RevealButton("Review stock"),"dashboard stock shortcut"));
        Wait(()=>ReadyButton("Add item"),"item register from dashboard");
        var itemSearch=Wait(()=>EditField("Search items"),"item register search");
        Set(itemSearch,posBarcode);
        Wait(()=>Find("Storefront oats",ControlType.Button),"seeded stock item found by barcode");
        Check("item register finds a stocked item by barcode");
        Set(itemSearch,"");
        transform.Resize(800,800);
        try
        {
            var add=Wait(()=>ReadyButton("Add item"),"visible Add item at 800px");
            var bounds=window.Current.BoundingRectangle;
            Check("narrow register keeps search and Add item inside the window",new[]{itemSearch,add}.All(control=>!control.Current.IsOffscreen&&control.Current.BoundingRectangle.Left>=bounds.Left&&control.Current.BoundingRectangle.Right<=bounds.Right));
            Snapshot("02-narrow-item-register");
        }
        finally{transform.Resize(originalBounds.Width,originalBounds.Height);}
        Invoke(NavigationItem("Dashboard"));
        Invoke(Wait(()=>RevealButton("Sales & collections  ↗"),"dashboard sales register shortcut"));
        var invoiceNumber=invoice["number"]!.GetValue<string>();
        var search=Wait(()=>EditField("Search documents"),"invoice register search");
        Set(search,"no synthetic invoice matches this");
        Wait(()=>Find("No records match these filters."),"invoice register filtered to empty");
        var filters=Wait(()=>Find("Filter documents") is { } candidate&&candidate.TryGetCurrentPattern(ExpandCollapsePattern.Pattern,out _)?candidate:null,"document filter panel");
        ((ExpandCollapsePattern)filters.GetCurrentPattern(ExpandCollapsePattern.Pattern)).Expand();
        Invoke(Wait(()=>RevealButton("Clear filters"),"clear invoice filters"));
        Invoke(Wait(()=>RevealButton(invoiceNumber),"seeded invoice restored by Clear filters"));
        Wait(()=>Find("Document total",ControlType.Text),"labeled transaction total");
        Wait(()=>ReadyButton("Record payment received"),"prominent payment action above the transaction items");
        Check("invoice search, reset and transaction payment entry work");
        Snapshot("03-transaction-detail");
        await File.WriteAllTextAsync(Path.Combine(evidence,"result.json"),new JsonObject{["passed"]=true,["scope"]="workspace-only",["checks"]=new JsonArray(checks.Select(x=>(JsonNode)JsonValue.Create(x)!).ToArray())}.ToJsonString());return;
    }
    if(posOnly)
    {
        var openPosNavigation = ReadyButton("Open Navigation");
        if(openPosNavigation is not null) Invoke(openPosNavigation);
        var group = Find("Sales");
        if(group?.TryGetCurrentPattern(ExpandCollapsePattern.Pattern, out var salesGroup)==true)
            ((ExpandCollapsePattern)salesGroup).Expand();
        var pos = Wait(() => window.FindAll(TreeScope.Descendants, Condition.TrueCondition).Cast<AutomationElement>()
            .FirstOrDefault(row => row.Current.Name.Equals("POS", StringComparison.OrdinalIgnoreCase)
                && (row.TryGetCurrentPattern(InvokePattern.Pattern,out _) || row.TryGetCurrentPattern(SelectionItemPattern.Pattern,out _))), "Point of sale navigation");
        Invoke(pos);
        var closePosNavigation = ReadyButton("Close Navigation");
        if(closePosNavigation is not null) Invoke(closePosNavigation);
        var search = Wait(() => EditField("Search products / scan barcode"), "scanner field");
        var liveStock=await Get("/api/capabilities");
        var showBookStock=liveStock["supported_features"]!.AsArray().Any(value=>value?.ToString()=="pos_stock_summary");
        if(showBookStock) Wait(()=>Find("Book on hand 2 pack"),"current book stock on the product card");
        AutomationElement? StorefrontProduct()=>window.FindAll(TreeScope.Descendants,Condition.TrueCondition).Cast<AutomationElement>()
            .FirstOrDefault(row=>row.Current.ControlType==ControlType.Button&&row.Current.Name.StartsWith("Add Storefront oats · ",StringComparison.Ordinal));
        search.SetFocus();
        Wait(() => search.Current.HasKeyboardFocus ? search : null, "scanner owns keyboard focus");
        var scannerInput=true;
        try
        {
            PressKeys(posBarcode);
            Wait(() => Value(search) == posBarcode ? search : null, "barcode received intact");
            PressKeys("{ENTER}");
        }
        catch(System.ComponentModel.Win32Exception error)
        {
            scannerInput=false;
            Console.WriteLine($"Keyboard injection unavailable ({error.ErrorCode:X8}). Continuing through visible barcode search.");
            if(EditField("Quantity for Storefront oats") is null)
            {
                Set(search,posBarcode);
                Invoke(Wait(StorefrontProduct,"barcode-filtered catalogue result"));
            }
        }
        var quantity = Wait(() => EditField("Quantity for Storefront oats"), "scanned item in cart");
        Check(scannerInput?"barcode scan added one item and retained scanner focus":"barcode search added one item and returned focus to scanner",
            Value(quantity)=="1"&&Value(search)==""&&search.Current.HasKeyboardFocus);
        var paymentMethod=Wait(()=>Find("Payment method",ControlType.ComboBox),"payment method choice");
        var choices=(ExpandCollapsePattern)paymentMethod.GetCurrentPattern(ExpandCollapsePattern.Pattern);
        choices.Expand();
        Wait(()=>Find("Cash + bank / UPI / card"),"split tender option from server capability");
        choices.Collapse();
        Check("capable Windows registers expose split tender");
        async Task PostSplit(int expectedStock)
        {
            var method=Wait(()=>Find("Payment method",ControlType.ComboBox),"split payment choice");
            ((ExpandCollapsePattern)method.GetCurrentPattern(ExpandCollapsePattern.Pattern)).Expand();
            Invoke(Wait(()=>Find("Cash + bank / UPI / card",ControlType.ListItem),"choose split tender"));
            Set(Wait(()=>EditField("Paid by bank / UPI / card (₹)"),"split bank portion"),"40");
            Set(Wait(()=>EditField("Cash received (₹)"),"split cash received"),"100");
            Wait(()=>Find("Confirm that the bank, UPI or card payment was received."),"split confirmation before posting");
            Check("split tender requires bank confirmation",!Find("Complete sale",ControlType.Button)!.Current.IsEnabled);
            var received=Wait(()=>Find("Bank, UPI or card payment confirmed",ControlType.CheckBox),"confirm bank payment");
            ((TogglePattern)received.GetCurrentPattern(TogglePattern.Pattern)).Toggle();
            Wait(()=>Find("Cash share ₹85.00 · Change ₹15.00"),"split cash due and change");
            var complete=Wait(()=>RevealButton("Complete sale"),"post split tender");
            Snapshot("pos-split-ready");
            Invoke(complete);
            Wait(()=>Find("Sale completed"),"split checkout complete");
            Check("Windows POS confirmed the split sale");
            if(showBookStock) Wait(()=>Find($"Book on hand {expectedStock} pack"),"book stock refreshed after split tender");
            var split=(await CompanyRecords(cid)).OfType<JsonObject>()
                .Single(row=>row["kind"]?.ToString()=="pos"&&row["data"]?["payment_account"]?.ToString()=="split");
            Check("Windows split tender posted exact cash, bank and change shares",
                Number(split["data"],"cash_amount")==85&&Number(split["data"],"bank_amount")==40&&Number(split["data"],"change_amount")==15);
        }
        if (splitOnly)
        {
            await PostSplit(1);
            await File.WriteAllTextAsync(Path.Combine(evidence,"result.json"),new JsonObject{
                ["passed"]=true,["scope"]="pos-split-only",
                ["checks"]=new JsonArray(checks.Select(value=>(JsonNode)JsonValue.Create(value)!).ToArray()),
            }.ToJsonString());
            return;
        }
        var cash = Wait(() => EditField("Cash received (₹)"), "cash received");
        Set(cash,"100");
        Wait(() => Find("Cash still due ₹25.00"), "underpayment feedback");
        Check("underpayment disables posting",!Find("Complete sale",ControlType.Button)!.Current.IsEnabled);
        Set(cash,"200");
        Wait(() => Find("Change ₹75.00"), "cash change");
        var handle = new IntPtr(window.Current.NativeWindowHandle);
        var dpi = Math.Max(1d, NativeWindowCapture.GetDpiForWindow(handle)/96d);
        Exception? desktopLayoutFailure=null;
        try
        {
            NativeWindowCapture.SetWindowPos(handle,IntPtr.Zero,0,0,(int)Math.Round(1280*dpi),(int)Math.Round(900*dpi),0x14);
            Thread.Sleep(650);
            Console.WriteLine("POS desktop window bounds " + window.Current.BoundingRectangle);
            search.SetFocus();
            try
            {
                var desktopSubmit = Wait(() => ReadyButton("Complete sale"), "desktop scan and checkout controls visible together", 15);
                Check("desktop cashier can reach sale completion without scrolling the scanner away",
                    !search.Current.IsOffscreen&&desktopSubmit.Current.BoundingRectangle.Bottom<=window.Current.BoundingRectangle.Bottom);
            }
            catch(Exception error)
            {
                desktopLayoutFailure=error;
                Console.WriteLine("Desktop layout check failed: "+error.Message+". Continuing amount and stock assertions at constrained width.");
            }
            Snapshot("pos-desktop-ready");
            transform.Resize(800,800);
            Thread.Sleep(500);
            search.SetFocus();
            Wait(() => !search.Current.IsOffscreen ? search : null, "scanner visible at constrained width");
            Check("scanner remains inside constrained frame",search.Current.BoundingRectangle.Right<=window.Current.BoundingRectangle.Right);
            Snapshot("pos-narrow-scanner");
            var submit=Wait(() => RevealButton("Complete sale"), "visible checkout action at constrained width");
            Check("checkout action remains inside constrained frame",submit.Current.BoundingRectangle.Right<=window.Current.BoundingRectangle.Right);
            Snapshot("pos-narrow-payment");
            Invoke(submit);
            Wait(() => Find("Sale completed"), "receipt confirmation");
            var posted=(await CompanyRecords(cid)).Where(row=>row?["kind"]?.ToString()=="pos").ToArray();
            Check("one completed POS transaction posted at the quoted total",posted.Length==1&&Number(posted[0],"amount")==125);
            Check("Windows checkout submitted server-enforced stock verification",
                posted[0]?["data"]?["require_available_stock"]?.GetValue<bool>()==true);
            var stock=(await Get($"/api/companies/{cid}/reports/stock?from_date={date}&to_date={date}"))["rows"]!.AsArray();
            Check("checkout consumed one inventory unit",Number(stock.Single(),"closing_quantity")==1);
            if(showBookStock)
            {
                Wait(()=>Find("Book on hand 1 pack"),"book stock refreshed after checkout");
                Check("POS catalogue shows updated book stock after posting");
            }
            var thermal=Wait(() => RevealButton("80 mm receipt"), "thermal receipt action");
            Invoke(thermal);
            Wait(() => Find("Page 1 of 1"), "thermal PDF preview");
            Snapshot("pos-thermal-receipt");
            Check("80 mm receipt opens in the native PDF preview");
            Invoke(Wait(()=>ReadyButton("Done"),"close receipt preview"));
            Wait(()=>Find("Page 1 of 1") is null?window:null,"return to POS checkout");
            var addLast=Wait(StorefrontProduct,"catalogue item for split checkout");
            Invoke(addLast);
            await PostSplit(0);
        }
        finally { transform.Resize(originalBounds.Width,originalBounds.Height); }
        await File.WriteAllTextAsync(Path.Combine(evidence,"result.json"),new JsonObject{
            ["passed"]=desktopLayoutFailure is null,["scope"]="pos-only",["desktop_layout_error"]=desktopLayoutFailure?.Message,
            ["checks"]=new JsonArray(checks.Select(value=>(JsonNode)JsonValue.Create(value)!).ToArray()),
        }.ToJsonString());
        if(desktopLayoutFailure is not null)Environment.ExitCode=1;
        return;
    }
    if(warehouseOnly)
    {
        Invoke(NavigationItem("Items"));
        var closeItemsNavigation=ReadyButton("Close Navigation");
        if(closeItemsNavigation is not null) Invoke(closeItemsNavigation);
        Invoke(Wait(()=>RevealButton("Count stock"),"Items physical stock count"));
        var scanner=Wait(()=>EditField("Scan item barcode"),"stock count barcode input");
        scanner.SetFocus();
        Wait(()=>scanner.Current.HasKeyboardFocus?scanner:null,"stock count scanner owns keyboard focus");
        Set(scanner,posBarcode);
        Wait(()=>Value(scanner)==posBarcode?scanner:null,"stock count barcode reaches input");
        Invoke(Wait(()=>ReadyButton("Find barcode"),"visible barcode lookup"));
        Wait(()=>Find("2 pack",ControlType.Text),"scanned item on-hand snapshot");
        var count=Wait(()=>EditField("Counted quantity"),"counted quantity field");
        Check("scanned product opens on-hand quantity and clears barcode",Value(scanner)=="");
        Set(count,"1");
        Wait(()=>Find("Decrease by 1 pack"),"one-unit count variance");
        Set(Wait(()=>EditField("Reason for difference"),"count discrepancy reason"),"Synthetic shelf count");
        Snapshot("warehouse-count-variance");

        await Post($"/api/companies/{cid}/stock/adjustments",new(){["item_id"]=storefrontItemId,
            ["date"]=date,["direction"]="increase",["quantity"]="1",["unit_cost"]="50",
            ["reason"]="Synthetic movement after shelf count began"});
        Invoke(Wait(()=>ReadyButton("Post count"),"initial stock count action"));
        Wait(()=>Find("Refresh and count again"),"stale stock snapshot rejected");
        Check("stale count clears quantity and disables posting",Value(count)==""&&!Find("Post count",ControlType.Button)!.Current.IsEnabled);
        Snapshot("warehouse-stale-count");
        transform.Resize(800,800);
        Invoke(Wait(()=>RevealButton("Refresh on hand"),"refresh stock at constrained width"));
        Wait(()=>Find("3 pack",ControlType.Text),"refreshed on-hand quantity");
        count=Wait(()=>EditField("Counted quantity"),"fresh count input");
        Set(count,"1");
        Wait(()=>Find("Decrease by 2 pack"),"recomputed physical difference");
        var submit=Wait(()=>ReadyButton("Post count"),"reviewed physical count at constrained width");
        Check("new stock count can be reviewed and posted at constrained width",
            submit.Current.BoundingRectangle.Right<=window.Current.BoundingRectangle.Right);
        Snapshot("warehouse-recount-ready");
        Invoke(submit);
        Wait(()=>Find("Physical stock count") is null?window:null,"warehouse count closed after confirmed post");
        var counts=(await CompanyRecords(cid)).Where(row=>row?["kind"]?.ToString()=="stock_adjustment"
            && row?["data"]?["stock_count"] is not null).ToArray();
        Check("one stock count posted against the refreshed snapshot",counts.Length==1
            && Number(counts[0]?["data"]?["stock_count"],"on_hand_before")==3
            && Number(counts[0]?["data"]?["stock_count"],"counted_quantity")==1);
        var stock=(await Get($"/api/companies/{cid}/reports/stock?from_date={date}&to_date={date}"))["rows"]!.AsArray();
        Check("inventory reflects the accepted physical count",Number(stock.Single(),"closing_quantity")==1);
        await File.WriteAllTextAsync(Path.Combine(evidence,"result.json"),new JsonObject{
            ["passed"]=true,["scope"]="warehouse-only",["checks"]=new JsonArray(checks.Select(value=>(JsonNode)JsonValue.Create(value)!).ToArray()),
        }.ToJsonString());
        return;
    }
    if(inventoryOnly)
    {
        AutomationElement? Containing(string text){try{return window!.FindAll(TreeScope.Descendants,Condition.TrueCondition).Cast<AutomationElement>().FirstOrDefault(x=>{try{return !x.Current.IsOffscreen&&x.Current.Name.Contains(text,StringComparison.Ordinal);}catch(ElementNotAvailableException){return false;}});}catch(ElementNotAvailableException){return null;}}
        var openItems=ReadyButton("Open Navigation");if(openItems is not null)Invoke(openItems);
        Invoke(Wait(()=>Find("Items",ControlType.ListItem),"Items navigation"));
        var closeItems=ReadyButton("Close Navigation");if(closeItems is not null)Invoke(closeItems);
        Wait(()=>Containing("Rack 1"),"item row shows where the item is kept");
        Check("item register shows location, part and fitment",Wait(()=>Containing("55810-M68K00"),"part number in item row") is not null&&Wait(()=>Containing("Maruti Suzuki Swift 2011–2017"),"fitment in item row") is not null);
        Snapshot("inventory-items");
        Invoke(Wait(()=>RevealButton("Brake pad set front"),"open item"));
        Wait(()=>Find("Where it is kept"),"item form location section");Wait(()=>Find("Vehicle details"),"item form vehicle section");
        Snapshot("inventory-item-form");
        Check("item form offers locations and vehicle fitment",Find("Add vehicle",ControlType.Button) is not null);
        Invoke(Wait(()=>Find("Cancel",ControlType.Button),"close item form"));
        var openSettings=ReadyButton("Open Navigation");if(openSettings is not null)Invoke(openSettings);
        Invoke(Wait(()=>Find("Settings",ControlType.ListItem),"Settings navigation"));
        var closeSettings=ReadyButton("Close Navigation");if(closeSettings is not null)Invoke(closeSettings);
        Invoke(Wait(()=>RevealButton("Locations and Automobile module"),"open stock settings"));
        Wait(()=>Find("Automobile module"),"stock settings dialog");
        Snapshot("inventory-settings");
        await File.WriteAllTextAsync(Path.Combine(evidence,"result.json"),new JsonObject{
            ["passed"]=true,["scope"]="inventory-only",["checks"]=new JsonArray(checks.Select(value=>(JsonNode)JsonValue.Create(value)!).ToArray()),
        }.ToJsonString());
        return;
    }
    if(receivingOnly)
    {
        var openPurchases=ReadyButton("Open Navigation");
        if(openPurchases is not null) Invoke(openPurchases);
        var group=Find("Purchases",ControlType.ListItem);
        if(group?.TryGetCurrentPattern(ExpandCollapsePattern.Pattern,out var purchasesGroup)==true)
            ((ExpandCollapsePattern)purchasesGroup).Expand();
        Invoke(Wait(()=>Find("Purchase orders",ControlType.ListItem),"Purchase orders navigation"));
        var closePurchases=ReadyButton("Close Navigation");
        if(closePurchases is not null) Invoke(closePurchases);
        var orderNumber=purchaseOrder!["number"]!.ToString();
        var orderId=purchaseOrder["id"]!.ToString();
        Invoke(Wait(()=>RevealButton(orderNumber),"synthetic purchase order in register"));
        Invoke(Wait(()=>RevealButton("Receive stock"),"receive stock from purchase order details"));
        transform.Resize(800,800);
        Set(Wait(()=>EditField("Quantity received for Storefront oats"),"partial receipt quantity"),"2");
        Set(Wait(()=>EditField("Bill unit price for Storefront oats"),"supplier rate override"),"60");
        Check("supplier receipt requires total review",!Find("Post supplier bill",ControlType.Button)!.Current.IsEnabled);
        Invoke(Wait(()=>RevealButton("Review bill total"),"review supplier bill total"));
        var reviewedAmount=Wait(()=>Find("Bill total ₹120.00") is { Current.IsOffscreen:false } amount?amount:null,"visible approved purchase bill amount");
        var postBill=Wait(()=>ReadyButton("Post supplier bill"),"post reviewed supplier bill");
        var receivingBounds=window.Current.BoundingRectangle;
        Check("the reviewed supplier total and posting action stay visible at 800px",
            new[]{reviewedAmount,postBill}.All(control=>control.Current.BoundingRectangle.Bottom<=receivingBounds.Bottom));
        Snapshot("purchase-receipt-review");
        Invoke(postBill);
        Wait(()=>Find("Receive purchase order") is null ? window : null,"supplier receipt posted and closed");
        var state=await Get($"/api/companies/{cid}/purchase-orders/{orderId}/receiving");
        var remaining=state["lines"]!.AsArray().Single();
        Check("partial receipt posted two units and left one outstanding",
            state["status"]?.ToString()=="partial"&&Number(remaining,"received_quantity")==2&&Number(remaining,"remaining_quantity")==1);
        var receivedBill=state["receipts"]!.AsArray().Single();
        Check("supplier rate override posted the reviewed purchase amount",Number(receivedBill,"amount")==120);
        Invoke(Wait(()=>RevealButton(orderNumber),"updated purchase order in register"));
        Wait(()=>Find("Partially received"),"partial receipt status in native order details");
        var orderDetails=Wait(()=>Find("Transaction details",ControlType.Window),"open purchase order details dialog");
        Check("started purchase order detail hides edit and legacy conversion",
            !orderDetails.FindAll(TreeScope.Descendants,new PropertyCondition(AutomationElement.ControlTypeProperty,ControlType.Button))
                .Cast<AutomationElement>().Any(button=>button.Current.Name is "Edit" or "Convert to purchase bill"));
        var link=Wait(()=>window.FindAll(TreeScope.Descendants,Condition.TrueCondition).Cast<AutomationElement>()
            .FirstOrDefault(row=>row.Current.ControlType==ControlType.Button&&row.Current.Name.StartsWith(receivedBill!["number"]!.ToString()+" · ",StringComparison.Ordinal)),
            "linked supplier bill");
        Invoke(link);
        Wait(()=>Find("Storefront supplier",ControlType.Text),"opened linked supplier bill detail");
        Check("purchase bill links back to its source order",
            window.FindAll(TreeScope.Descendants,Condition.TrueCondition).Cast<AutomationElement>().Any(row=>
                row.Current.ControlType==ControlType.Button&&row.Current.Name.Contains(orderNumber,StringComparison.Ordinal)));
        Snapshot("purchase-receipt-linked");
        await File.WriteAllTextAsync(Path.Combine(evidence,"result.json"),new JsonObject{
            ["passed"]=true,["scope"]="receiving-only",["checks"]=new JsonArray(checks.Select(value=>(JsonNode)JsonValue.Create(value)!).ToArray()),
        }.ToJsonString());
        return;
    }
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
    PressKeys("^a");PressKeys("{BACKSPACE}");AwaitItemValue("","clear");
    const string itemDescription="Invoice created through Windows UI";var entered="";
    foreach(var character in itemDescription){
        if(!ItemHasFocus())throw new Exception("Item selector lost keyboard focus before next character; refusing to type into another control.");
        PressKeys(KeyboardLiteral(character.ToString()));entered+=character;AwaitItemValue(entered,"character "+entered.Length);
    }
    Check("item selector contains the exact complete text before Tab",Value(itemSelector)==itemDescription);
    // A second, continuous burst is mandatory: paced entry must not hide dropped
    // fast typing or an application control replacement during TextChanged.
    var originalItemRuntimeId=itemSelector.GetRuntimeId();typingDeadline.Restart();
    PressKeys("^a");PressKeys("{BACKSPACE}");AwaitItemValue("","rapid-entry clear");
    if(!ItemHasFocus())throw new Exception("Item selector lost focus before rapid typing.");
    PressKeys(KeyboardLiteral(itemDescription));AwaitItemValue(itemDescription,"continuous rapid typing");
    var currentItem=Wait(()=>EditField("Item / service"),"same item selector after rapid typing");
    Check("rapid typing retains exact text, keyboard focus and control identity",Value(currentItem)==itemDescription&&ItemHasFocus()&&originalItemRuntimeId.SequenceEqual(currentItem.GetRuntimeId()));
    PressKeys("{TAB}");
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
    AutomationElement NavigationItem(string label){
        var opened=false;
        return Wait(()=>{
            var item=Find(label,ControlType.ListItem);
            if(item is not null&&!item.Current.IsOffscreen&&(item.TryGetCurrentPattern(SelectionItemPattern.Pattern,out _)||item.TryGetCurrentPattern(InvokePattern.Pattern,out _)))return item;
            var toggle=ReadyButton("Open Navigation");if(!opened&&toggle is not null){Invoke(toggle);opened=true;}
            return null;
        },label+" visible navigation");
    }
    Invoke(NavigationItem("Dashboard"));Invoke(Wait(()=>Find("Purchases  ↗",ControlType.Button),"purchase register shortcut"));
    Invoke(Wait(()=>Find(evidenceBill["number"]!.GetValue<string>(),ControlType.Button),"synthetic purchase bill row"));Invoke(Wait(()=>Find("Retained receipts",ControlType.Button),"purchase bill retained evidence action"));
    Wait(()=>Find("No retained receipts. Upload original evidence to keep it with this transaction."),"empty receipt panel");Invoke(Wait(()=>Find("Choose receipt and upload",ControlType.Button),"native receipt upload action"));
    // Genuine system picker interaction; no hidden app state or direct upload API substitution.
    // Hosted Windows evidence shows this owned dialog nested beneath the app, not a desktop child.
    var picker=Wait(()=>window.FindAll(TreeScope.Descendants,new PropertyCondition(AutomationElement.ControlTypeProperty,ControlType.Window)).Cast<AutomationElement>().FirstOrDefault(e=>e.Current.Name=="Open"&&!e.Current.IsOffscreen),"owned system Open file picker inside app UIA tree");
    var filename=Wait(()=>picker.FindAll(TreeScope.Descendants,new PropertyCondition(AutomationElement.ControlTypeProperty,ControlType.Edit)).Cast<AutomationElement>().FirstOrDefault(e=>(e.Current.Name is "File name:" or "File name"||e.Current.AutomationId=="1148")&&e.TryGetCurrentPattern(ValuePattern.Pattern,out _)),"system picker File name field");Set(filename,evidenceFile);
    Check("Receipt picker contains exact requested path",Value(filename)==evidenceFile);
    filename.SetFocus();Wait(()=>filename.Current.HasKeyboardFocus?filename:null,"receipt picker filename keyboard focus",10);
    // The modern shell may expose Open as a split action rather than a Button.
    // Enter commits this verified filename through the real picker; canonical bytes below verify the result.
    PressKeys("{ENTER}");
    Wait(()=>Find("Archive retained receipt",ControlType.Button),"receipt uploaded through system picker");Snapshot("07-retained-receipt");
    var evidencePath=$"/api/companies/{cid}/records/{evidenceBill["id"]!.GetValue<string>()}/attachments";var uploaded=(await Get(evidencePath))["attachments"]!.AsArray();var expectedSha=Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(evidenceBytes)).ToLowerInvariant();
    Check("real receipt picker uploaded exactly one matching retained file",uploaded.Count==1&&uploaded[0]?["sha256"]?.ToString()==expectedSha&&Number(uploaded[0],"size_bytes")==evidenceBytes.Length);
    Invoke(Wait(()=>Find("Archive retained receipt",ControlType.Button),"archive receipt through UI"));Wait(()=>Find("Reactivate retained receipt",ControlType.Button),"archived receipt UI state");var archived=(await Get(evidencePath))["attachments"]!.AsArray();Check("archive UI retains the original evidence bytes and lineage",archived.Count==1&&archived[0]?["is_archived"]?.GetValue<bool>()==true&&archived[0]?["sha256"]?.ToString()==expectedSha);Snapshot("08-archived-receipt");
    Invoke(Wait(()=>Find("Done",ControlType.Button),"close retained receipt panel"));Invoke(NavigationItem("Settings"));Set(Wait(()=>EditField("Find a setting, for example logo, Vyapar or prefixes"),"Settings search"),"Download backup");Invoke(Wait(()=>RevealButton("Download backup"),"settings complete backup entry"));Wait(()=>Find("Complete portable backup"),"complete backup dialog");Wait(()=>ReadyButton("Verify and save backup"),"complete backup explicit save action");Snapshot("09-complete-backup-entry");Check("complete backup is discoverable after retaining receipt evidence");
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
    // FileSavePicker can create an empty destination before SaveStream writes/flushes.
    // A temporarily absent UIA button is not proof of completion. Require the
    // application's post-save success notice; failed writes must time out/fail,
    // not be hidden by retrying JSON parsing until it happens to work.
    Wait(()=>Find("Complete backup saved to the selected file.") is not null&&Find("Verify and save backup",ControlType.Button) is null&&File.Exists(backupPath)?window:null,"successful encrypted backup save and dialog close",120);
    var savedBackupBytes=await File.ReadAllBytesAsync(backupPath);
    Check("completed encrypted export has persisted bytes",savedBackupBytes.Length>0);
    var envelope=JsonNode.Parse(savedBackupBytes)!.AsObject();
    Check("actual Save picker produced encrypted v1 envelope",envelope["format"]?.ToString()=="apex-encrypted-backup"&&Number(envelope,"version")==1&&envelope["ciphertext"] is JsonValue);
    Snapshot("10-encrypted-export-saved");
    Set(Wait(()=>EditField("Find a setting, for example logo, Vyapar or prefixes"),"Settings search after export"),"Restore company backup");
    Invoke(Wait(()=>RevealButton("Restore company backup"),"restore from Settings"));
    ChooseNativeFile("Open","Open",backupPath);
    Wait(()=>Find("Restore complete backup into a new company"),"restore encrypted backup dialog");
    var restoredName="Windows UI Restored "+Guid.NewGuid().ToString("N")[..8];
    Set(Wait(()=>EditField("Name for the NEW restored company"),"new restored company name"),restoredName);
    Set(Wait(()=>EditField("Encrypted backup passphrase"),"restore passphrase"),backupPassword);
    var encryptedImport=Wait(()=>Find("This file uses Apex encrypted-backup v1",ControlType.CheckBox),"encrypted import mode");
    Check("encrypted file is recognized without plaintext fallback",((TogglePattern)encryptedImport.GetCurrentPattern(TogglePattern.Pattern)).Current.ToggleState==ToggleState.On);
    Invoke(Wait(()=>RevealButton("Validate / resume and preview"),"authenticate upload and preview"));
    Wait(()=>window.FindAll(TreeScope.Descendants,new PropertyCondition(AutomationElement.ControlTypeProperty,ControlType.Text)).Cast<AutomationElement>().FirstOrDefault(e=>e.Current.Name.Contains("Complete SHA256 verified. Review below",StringComparison.Ordinal)),"authenticated immutable preview",120);
    Check("preview has not created a company",(await Get("/api/companies")).AsArray().Count==sourceCompanies.Count);
    Snapshot("11-restore-reviewed-preview");
    Invoke(Wait(()=>ReadyButton("Restore reviewed backup"),"explicit new-company restore"));
    Wait(()=>Find("Restore reviewed backup",ControlType.Button) is null?Find(restoredName):null,"restore dialog closed and new company loaded",120);Invoke(NavigationItem("Dashboard"));Wait(()=>Find("Business overview"),"restored dashboard");Wait(()=>Find("Sales & collections  ↗",ControlType.Button),"restored company data ready",120);Snapshot("12-restored-company-dashboard");
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
    var quoteNavigation=ReadyButton("Open Navigation");if(quoteNavigation is not null)Invoke(quoteNavigation);
    combo=Wait(()=>Find("Choose company",ControlType.ComboBox),"quotation company picker");SelectCompany("Windows UI Quotation");
    var quoteCloseNavigation=ReadyButton("Close Navigation");if(quoteCloseNavigation is not null)Invoke(quoteCloseNavigation);
    Wait(()=>Find("Windows UI Quotation"),"quotation company heading");Invoke(NavigationItem("Dashboard"));Invoke(Wait(()=>RevealButton("1 open estimates"),"dashboard open quotation shortcut"));
    Invoke(Wait(()=>Find(seededQuote["number"]!.ToString(),ControlType.Button),"nine-line quotation row"));
    Invoke(Wait(()=>RevealButton("Edit"),"reopen nine-line quotation"));Wait(()=>Find("Save changes",ControlType.Button),"nine-line edit form");Snapshot("13-nine-line-quotation-edit");
    Invoke(Wait(()=>ReadyButton("Save changes"),"save unchanged nine-line quotation"));Wait(()=>Find("Save changes",ControlType.Button) is null?window:null,"quotation edit saved");
    if(ReadyButton("Done") is { } quoteDone)Invoke(quoteDone);
    Invoke(Wait(()=>Find(seededQuote["number"]!.ToString(),ControlType.Button),"saved quotation row"));Invoke(Wait(()=>ReadyButton("Convert to invoice"),"quotation conversion action"));
    Wait(()=>window.FindAll(TreeScope.Descendants,new PropertyCondition(AutomationElement.ControlTypeProperty,ControlType.Text)).Cast<AutomationElement>().FirstOrDefault(e=>e.Current.Name.StartsWith("Subtotal ",StringComparison.Ordinal)&&e.Current.Name.Contains("17,385.00",StringComparison.Ordinal)),"converted nine-line server preview");
    Snapshot("14-nine-line-conversion-preview");Invoke(Wait(()=>ReadyButton("Save invoice"),"save converted quotation"));Wait(()=>Find("Save invoice",ControlType.Button) is null?window:null,"conversion saved");
    var quoteStatus=await Get($"/api/companies/{quoteCid}/records/{seededQuote["id"]}");var convertedQuoteId=quoteStatus["converted_to"]!.ToString();var nineInvoice=await Get($"/api/companies/{quoteCid}/records/{convertedQuoteId}");
    Check("native quotation conversion total and linkage",Number(nineInvoice,"amount")==17385m&&nineInvoice["data"]?["source_document_id"]?.ToString()==seededQuote["id"]?.ToString());
    foreach(var key in new[]{"notes","terms","round_total"})Check("native quotation retains "+key,JsonNode.DeepEquals(nineInvoice["data"]?[key],quotationFixture["data"]?[key]));
    var nineLines=nineInvoice["data"]!["lines"]!.AsArray();Check("native quotation retains nine rows",nineLines.Count==9);
    for(var i=0;i<9;i++)foreach(var key in new[]{"description","quantity","rate","unit","hsn","gst_rate"})Check($"native quotation line {i+1} retains {key}",nineLines[i]?[key]?.ToString()==quotationFixture["data"]?["lines"]?[i]?[key]?.ToString());
    foreach(var key in new[]{"taxable","cgst","sgst","round_off"})Check("native quotation retains calculated "+key,Number(nineInvoice["data"],key)==Number(quotationFixture["expected"],key));
    Snapshot("15-nine-line-converted-detail");await File.WriteAllTextAsync(Path.Combine(evidence,"quotation-verification.json"),nineInvoice.ToJsonString());
    Dump();
    await File.WriteAllTextAsync(Path.Combine(evidence,"result.json"),new JsonObject{["passed"]=true,["api_origin"]=origin.ToString(),["checks"]=new JsonArray(checks.Select(x=>(JsonNode)JsonValue.Create(x)!).ToArray())}.ToJsonString());
}catch(Exception e){try{Dump();Snapshot("failure-visible-app");}catch{}await File.WriteAllTextAsync(Path.Combine(evidence,"failure.txt"),e.ToString());Console.Error.WriteLine(e);Environment.ExitCode=1;}
finally{if(app is not null&&!app.HasExited){app.Kill(entireProcessTree:true);app.WaitForExit(10000);}}

internal static class NativeWindowCapture
{
    [System.Runtime.InteropServices.DllImport("user32.dll")]
    [return: System.Runtime.InteropServices.MarshalAs(System.Runtime.InteropServices.UnmanagedType.Bool)]
    internal static extern bool SetForegroundWindow(IntPtr window);
    [System.Runtime.InteropServices.DllImport("dwmapi.dll")]
    internal static extern int DwmFlush();
    [System.Runtime.InteropServices.DllImport("user32.dll")]
    internal static extern uint GetDpiForWindow(IntPtr window);
    [System.Runtime.InteropServices.DllImport("user32.dll",SetLastError=true)]
    internal static extern bool SetWindowPos(IntPtr window,IntPtr insertAfter,int x,int y,int width,int height,uint flags);
    [System.Runtime.InteropServices.DllImport("user32.dll", SetLastError=true)]
    [return: System.Runtime.InteropServices.MarshalAs(System.Runtime.InteropServices.UnmanagedType.Bool)]
    internal static extern bool PrintWindow(IntPtr window,IntPtr deviceContext,uint flags);
}
