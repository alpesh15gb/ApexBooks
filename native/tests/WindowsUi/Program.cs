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
void Check(string message){checks.Add(message);Console.WriteLine("PASS "+message);}
using var http=new HttpClient(new HttpClientHandler{AllowAutoRedirect=false}){BaseAddress=origin,Timeout=TimeSpan.FromSeconds(30)};
async Task<JsonObject> Post(string path,JsonObject body){using var response=await http.PostAsync(path,new StringContent(body.ToJsonString(),Encoding.UTF8,"application/json"));var text=await response.Content.ReadAsStringAsync();if(!response.IsSuccessStatusCode)throw new Exception($"Synthetic API {path} failed ({(int)response.StatusCode}): {text}");return JsonNode.Parse(text)!.AsObject();}
AutomationElement Wait(Func<AutomationElement?> find,string description,int seconds=60){var timeout=Stopwatch.StartNew();while(timeout.Elapsed.TotalSeconds<seconds){try{var element=find();if(element is not null)return element;}catch(ElementNotAvailableException){}if(app?.HasExited==true)throw new Exception($"WinUI exited with {app.ExitCode} while waiting for {description}");Thread.Sleep(250);}throw new Exception("UI timeout: "+description);}
AutomationElement? Find(string name,ControlType? type=null)=>window?.FindAll(TreeScope.Descendants,Condition.TrueCondition).Cast<AutomationElement>().FirstOrDefault(x=>x.Current.Name==name&&(type is null||x.Current.ControlType==type));
void Invoke(AutomationElement element){if(element.TryGetCurrentPattern(InvokePattern.Pattern,out var pattern))((InvokePattern)pattern).Invoke();else if(element.TryGetCurrentPattern(SelectionItemPattern.Pattern,out pattern))((SelectionItemPattern)pattern).Select();else throw new Exception("Control has no supported Invoke/Selection pattern: "+element.Current.Name);}
void Set(AutomationElement element,string value){if(!element.TryGetCurrentPattern(ValuePattern.Pattern,out var pattern))throw new Exception("Control has no supported Value pattern: "+element.Current.Name);((ValuePattern)pattern).SetValue(value);}
void Snapshot(string name){if(window is null)return;var rectangle=window.Current.BoundingRectangle;if(rectangle.Width<1||rectangle.Height<1)throw new Exception("App has no visible capture rectangle.");using var bitmap=new Drawing.Bitmap((int)rectangle.Width,(int)rectangle.Height);using(var graphics=Drawing.Graphics.FromImage(bitmap))graphics.CopyFromScreen((int)rectangle.X,(int)rectangle.Y,0,0,bitmap.Size);bitmap.Save(Path.Combine(evidence,name+".png"),Drawing.Imaging.ImageFormat.Png);}
void Dump(){if(window is null)return;var rows=window.FindAll(TreeScope.Descendants,Condition.TrueCondition).Cast<AutomationElement>().Select(x=>new{type=x.Current.ControlType.ProgrammaticName,name=x.Current.Name,password=x.Current.IsPassword}).ToArray();File.WriteAllText(Path.Combine(evidence,"uia-tree.json"),System.Text.Json.JsonSerializer.Serialize(rows,new System.Text.Json.JsonSerializerOptions{WriteIndented=true}));}
try{
    if(!Environment.UserInteractive)throw new Exception("Runner has no interactive Windows desktop. UI smoke requires an already configured interactive runner; no desktop/security settings will be changed.");
    var email=$"windows-ui-{Guid.NewGuid():N}@example.invalid";var password="Synthetic-Windows-Ui-Only-42!";
    await Post("/api/auth/register",new(){["email"]=email,["password"]=password});var login=await Post("/api/auth/login",new(){["email"]=email,["password"]=password});http.DefaultRequestHeaders.Authorization=new AuthenticationHeaderValue("Bearer",login["token"]!.GetValue<string>());
    var first=await Post("/api/companies",new(){["name"]="Windows UI Alpha",["tax_mode"]="unregistered",["state_code"]="27"});var second=await Post("/api/companies",new(){["name"]="Windows UI Beta",["tax_mode"]="unregistered",["state_code"]="27"});
    var cid=second["id"]!.GetValue<string>();var date=DateTime.Today.ToString("yyyy-MM-dd");
    var invoice=await Post($"/api/companies/{cid}/records",new(){["kind"]="sales_invoice",["name"]="Synthetic UI Buyer",["date"]=date,["data"]=new JsonObject{["lines"]=new JsonArray(new JsonObject{["description"]="Synthetic UI service",["quantity"]="1",["rate"]="100",["gst_rate"]="0"})}});
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
    Invoke(Wait(()=>Find("Sales & collections  ↗",ControlType.Button),"sales register shortcut"));var number=invoice["number"]!.GetValue<string>();Invoke(Wait(()=>Find(number,ControlType.Button),"seeded invoice in register"));
    Wait(()=>Find("Synthetic UI Buyer"),"invoice detail buyer");Wait(()=>Find("Record payment received",ControlType.Button),"invoice collection context action");Snapshot("02-invoice-detail");Dump();Check("real register opened invoice detail with collection action");
    await File.WriteAllTextAsync(Path.Combine(evidence,"result.json"),new JsonObject{["passed"]=true,["api_origin"]=origin.ToString(),["checks"]=new JsonArray(checks.Select(x=>(JsonNode)JsonValue.Create(x)!).ToArray())}.ToJsonString());
}catch(Exception e){try{Dump();}catch{}await File.WriteAllTextAsync(Path.Combine(evidence,"failure.txt"),e.ToString());throw;}
finally{if(app is not null&&!app.HasExited){app.Kill(entireProcessTree:true);app.WaitForExit(10000);}}
