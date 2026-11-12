using ApexBooks_Windows.Models;
using ApexBooks_Windows.Services;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using System.Net.Http;
using System.Text;
using System.Text.Json.Nodes;
using static ApexBooks_Windows.Views.NativeUi;

namespace ApexBooks_Windows;
public sealed partial class MainPage
{
    private async Task AboutBuild()
    {
        var panel=Stack();panel.Children.Add(Text("Apex Books "+BuildIdentity.Version,24,true));panel.Children.Add(Text("Build revision",14,true));panel.Children.Add(Text(BuildIdentity.Revision,12));panel.Children.Add(Text("Include these details when contacting support about an issue.",12));panel.Children.Add(Text("API server · "+Api.Origin,12));panel.Children.Add(Text("Connected API version · "+Api.Capabilities.ApiVersion,12));panel.Children.Add(Text("Connected API build · "+Api.Capabilities.BuildRevision,12));await Dialog("About Apex Books",panel,()=>Task.CompletedTask,"Done");
    }
    private Task SettingsPage()
    {
        var entries=new List<(string Title,string Detail,(string Label,Func<Task> Action)[] Actions)>();
        void Add(string title,string detail,params (string Label,Func<Task> Action)[] actions)=>entries.Add((title,detail,actions));
        Add("Company",Company.Text("name")+" · "+Friendly(Company.Text("tax_mode"))+" · "+Company.Text("gstin"),("Create another company",()=>CompanyForm()));
        if(IsOwner){
            entries[0]=(entries[0].Title,entries[0].Detail,[ ("Edit company details",()=>CompanyForm(true)),("Create another company",()=>CompanyForm()) ]);
            Add("Documents & branding","Company logo, signature, bank / UPI details and five document formats.",("Logo, signature and formats",Branding),("Transaction prefixes",Prefixes));
            Add("Accounting","Opening balances and accounting period controls.",("Opening balances",OpeningBalance),("Accounting period lock",PeriodLock));
            Add("Data & migration","Import, export and protect your books. Vyapar migration includes reconciliation; backup restore creates a separate company.",("Import Vyapar .vyb backup",VyaparMigration),("Import parties / items CSV",MasterCsvImport),("Export company data",DataExport),("Download backup",BackupCompany),("Restore company backup",RestoreCompany));
            if(Supports("chunked_backups"))Add("Complete backup recovery","Resume or cancel your own staged transfers after a lost response or restart.",("Recover backup transfers",RecoverCompleteTransfers));
            Add("People & access","Manage company roles and permissions.",("Company members",Members));
        }
        Add("About Apex Books","Version "+BuildIdentity.Version+" · app and connection details for support",("About this build",AboutBuild));
        Add("Account security","Protect your account and review changes. Remembered sign-in is stored securely on this device.",("Password and sessions",Security),("One-use recovery codes",RecoveryCodes),("View audit history",AuditHistory));
        Add("Ecommerce","Manage online stores, stock, orders and deliveries.",("Open ecommerce workspace",()=>Navigate("commerce")));
        var search=Input("Find a setting, for example logo, Vyapar or prefixes");var category=Select("Settings category",new[]{("all","All settings")}.Concat(entries.Select(e=>(e.Title,e.Title))),"all");var content=Stack(18);
        void Draw(){content.Children.Clear();var query=search.Text.Trim();var selected=Value(category);var matches=entries.Where(e=>(query.Length>0||selected=="all"||e.Title==selected)&&(e.Title+" "+e.Detail+" "+string.Join(" ",e.Actions.Select(a=>a.Label))).Contains(query,StringComparison.OrdinalIgnoreCase)).ToArray();
            foreach(var entry in matches){var card=Stack();card.Children.Add(Text(entry.Title,21,true));card.Children.Add(Text(entry.Detail));foreach(var action in entry.Actions.Where(a=>query.Length==0||(entry.Title+" "+entry.Detail+" "+a.Label).Contains(query,StringComparison.OrdinalIgnoreCase))){var button=AsyncButton(action.Label,action.Action,Error);button.HorizontalAlignment=HorizontalAlignment.Stretch;button.HorizontalContentAlignment=HorizontalAlignment.Left;card.Children.Add(button);}content.Children.Add(Card(card));}
            if(matches.Length==0)content.Children.Add(Card(Text("No settings match. Try logo, backup or company.")));
        }
        Body.Children.Add(Text(Company.Text("name")+" · company settings",15,true));Body.Children.Add(Columns(category,search));Body.Children.Add(content);Body.Children.Add(Text("Apex Books for Windows · "+typeof(MainPage).Assembly.GetName().Version?.ToString(3),12));search.TextChanged+=(_,_)=>Draw();category.SelectionChanged+=(_,_)=>Draw();Draw();return Task.CompletedTask;
    }
    private async Task Branding()
    {
        var cid=CompanyId;var data=(await Api.Send(PathFor("/document-branding"))).Object();var preferences=await Api.Send(PathFor("/preferences"));var panel=Stack();panel.MinWidth=750;
        var format=Select("Default document format",new[]{"modern","vintage","mrp_discount","elegant","evergreen"}.Select(x=>(x,Friendly(x))),preferences.Text("document_template"));panel.Children.Add(format);
        var images=new Dictionary<string,string>{{"logo",data.Text("logo")},{"signature",data.Text("signature")}};
        foreach(var key in new[]{"logo","signature"})
        {
            var image=new Image{Width=160,Height=90,HorizontalAlignment=HorizontalAlignment.Left,Stretch=Microsoft.UI.Xaml.Media.Stretch.Uniform};if(images[key].Length>0)image.Source=await Bitmap(images[key]);var row=Stack();row.Children.Add(Text(Friendly(key),16,true));row.Children.Add(image);var actions=new StackPanel{Orientation=Orientation.Horizontal,Spacing=10};
            var state=Text(key=="logo"?"Logo uploads save immediately and apply to all document downloads.":"Save document details after choosing a signature.",12);state.Foreground=Muted;
            actions.Children.Add(AsyncButton(key=="logo"?"Upload & save logo":"Upload signature",async()=>{var file=await ApexFiles.Pick(".png",".jpg",".jpeg");if(file is null)return;var value=await ApexFiles.Image(file,900,240000);if(key=="logo")await Api.Send(Api.CompanyPath(cid,"/document-branding"),HttpMethod.Patch,new JsonObject{["logo"]=value});images[key]=value;image.Source=await Bitmap(value);state.Text=key=="logo"?"Company logo saved. Reopen any document to see it.":"Signature selected; save document details to keep it.";},Error));
            actions.Children.Add(AsyncButton(key=="logo"?"Remove saved logo":"Remove signature",async()=>{if(key=="logo")await Api.Send(Api.CompanyPath(cid,"/document-branding"),HttpMethod.Patch,new JsonObject{["logo"]=""});images[key]="";image.Source=null;state.Text=key=="logo"?"Company logo removed.":"Signature cleared; save document details to keep this change.";},Error));row.Children.Add(actions);row.Children.Add(state);panel.Children.Add(Card(row));
        }
        var fields=new Dictionary<string,TextBox>();foreach(var key in new[]{"phone","email","bank_name","account_number","ifsc","branch","upi_id","notes","terms"}){var field=Input(Friendly(key),data.Text(key),key is "notes" or "terms");if(key=="terms")field.MaxLength=3000;fields[key]=field;panel.Children.Add(field);}
        if(await Dialog("Document branding",panel,async()=>{var body=new JsonObject();foreach(var pair in fields)body[pair.Key]=pair.Value.Text;body["signature"]=images["signature"];await Api.Send(Api.CompanyPath(cid,"/document-branding"),HttpMethod.Put,body);await Api.Send(Api.CompanyPath(cid,"/preferences"),HttpMethod.Put,new JsonObject{["document_template"]=Value(format)});},"Save document details"))Success("Document branding saved.");
    }
    private async Task Prefixes()
    {
        var cid=CompanyId;var kinds=FeatureCatalog.Documents.Concat(new[]{"payment_in","payment_out"}).Distinct();var kind=Select("Document type",kinds.Select(k=>(k,FeatureCatalog.Singular(k))));var year=new NumberBox{Header="Financial year starting in April",Minimum=2000,Maximum=2100,Value=int.Parse(J.FinancialStart[..4])};var prefix=Input("Prefix · 1–6 uppercase letters, digits or hyphens");prefix.MaxLength=6;var panel=Stack();foreach(var field in new UIElement[]{kind,year,prefix})panel.Children.Add(field);Table(panel,(await Api.Send(PathFor("/number-series"))).Array(),"Existing series");await Dialog("Transaction prefixes",panel,async()=>{await Api.Send(Api.CompanyPath(cid,"/number-series"),HttpMethod.Put,new JsonObject{["kind"]=Value(kind),["financial_year"]=(int)year.Value,["prefix"]=prefix.Text.Trim().ToUpperInvariant()});});
    }
    private async Task OpeningBalance()
    {
        var cid=CompanyId;var kind=Select("Opening type",[("receivable","Customer receivable"),("payable","Supplier payable"),("cash","Cash"),("bank","Bank")]);var party=Select("Party",Records.Where(r=>r.Text("kind")=="party").Select(r=>(r.Text("id"),r.Text("name"))));var bank=BankChoice();var date=new DateInput("Opening date",J.FinancialStart);var amount=Input("Opening amount (₹)");var overdraft=new CheckBox{Content="Bank overdraft"};var panel=Stack();panel.Children.Add(Text("Set openings before the first transaction for the party or account. Stock openings are available in Items."));foreach(var field in new UIElement[]{kind,party,bank,date.View,amount,overdraft})panel.Children.Add(field);void ShowOpening(){party.Visibility=Value(kind) is "receivable" or "payable"?Visibility.Visible:Visibility.Collapsed;bank.Visibility=overdraft.Visibility=Value(kind)=="bank"?Visibility.Visible:Visibility.Collapsed;}kind.SelectionChanged+=(_,_)=>ShowOpening();ShowOpening();var key=Guid.NewGuid().ToString();if(await Dialog("Opening balance",panel,async()=>{await Api.Send(Api.CompanyPath(cid,"/opening-balances"),HttpMethod.Post,new JsonObject{["kind"]="opening_balance",["name"]="Opening balance",["date"]=date.Value,["amount"]=amount.Text,["data"]=new JsonObject{["balance_kind"]=Value(kind),["party_id"]=Value(party),["bank_account_id"]=Value(bank),["overdraft"]=overdraft.IsChecked==true}},key);},"Post opening"))await Refresh();
    }
    private async Task Members()
    {
        var cid=CompanyId;var panel=Stack();panel.MinWidth=650;var email=Input("Registered user's email");var role=Select("Role",[("viewer","Viewer"),("editor","Editor")]);var rows=Stack();
        async Task Load(){var members=(await Api.Send(Api.CompanyPath(cid,"/members"))).Array();rows.Children.Clear();foreach(var member in members){var m=member;var line=Stack();line.Children.Add(Text(m.Text("email")+" · "+m.Text("role")));if(m.Text("role")!="owner")line.Children.Add(AsyncButton("Remove access",async()=>{await Api.Send(Api.CompanyPath(cid,"/members/"+Uri.EscapeDataString(m.Text("email"))),HttpMethod.Delete);await Load();},Error));rows.Children.Add(Card(line));}}
        panel.Children.Add(Columns(email,role));panel.Children.Add(AsyncButton("Add / update access",async()=>{await Api.Send(Api.CompanyPath(cid,"/members"),HttpMethod.Post,new JsonObject{["email"]=email.Text.Trim(),["role"]=Value(role)});email.Text="";await Load();},Error,true));panel.Children.Add(rows);await Load();await Dialog("Company members",panel,()=>Task.CompletedTask,"Done");
    }
    private async Task PeriodLock()
    {
        var cid=CompanyId;var status=await Api.Send(PathFor("/period-lock"));var date=new DateInput("New lock date",J.Today);var panel=Stack();panel.Children.Add(Text("Locked through: "+(status.Text("locked_through") is {Length:>0} locked?locked:"No date set")));panel.Children.Add(Text("Entries through this date cannot be posted or edited. The date can only move forward."));panel.Children.Add(date.View);await Dialog("Lock accounting period",panel,async()=>{await Api.Send(Api.CompanyPath(cid,"/period-lock"),HttpMethod.Put,new JsonObject{["locked_through"]=date.Value});},"Lock through date");
    }
    private async Task BackupCompany()
    {
        if(Supports("chunked_backups")){await CompleteBackupCompany();return;}
        var cid=CompanyId;var exportAccess=CaptureFileSaveAccess();var password=new PasswordBox{Header="Optional backup password · at least 12 characters"};var panel=Stack();panel.Children.Add(Text("Keep the backup and its password securely. Passwords cannot be recovered."));panel.Children.Add(password);
        await Dialog("Download company backup",panel,async()=>{if(password.Password.Length is >0 and <12)throw new Exception("Use at least 12 characters.");var passphrase=password.Password;var encrypted=passphrase.Length>0;var saved=await ScopedFileExport.Download(exportAccess,()=>Api.Download(Api.CompanyPath(cid,"/backup")),encrypted?bytes=>Task.Run(()=>ApexFiles.EncryptBackup(bytes,passphrase)):null,(bytes,verify)=>ApexFiles.Save(bytes,$"apex-{cid[..8]}-{J.Today}."+(encrypted?"apexbackup":"json.gz"),verify));if(saved==false)throw new Exception("Choose a destination to save the backup.");},"Download backup");
    }
    private async Task RestoreCompany()
    {
        var verify=CaptureOwnerImportAccess();
        if(Supports("chunked_backups")){await RestoreCompleteCompany();return;}
        var file=await ApexFiles.Pick(".apexbackup",".gz",".json");if(file is null)return;verify();var content=await ApexFiles.Read(file);verify();var name=Input("Name for the restored company");var password=new PasswordBox{Header="Backup password · when encrypted"};var panel=Stack();panel.MinWidth=750;panel.Children.Add(Text(file.Name));panel.Children.Add(name);panel.Children.Add(password);var results=Stack();string encoded="",digest="",reviewedName="";
        panel.Children.Add(AsyncButton("Validate and preview",async()=>{verify();digest="";reviewedName="";results.Children.Clear();var requestedName=name.Text;var requestedPassword=password.Password;encoded=Convert.ToBase64String(ApexFiles.PrepareRestore(content,requestedPassword));var result=await Api.Send("/api/backups/restore/preview",HttpMethod.Post,new JsonObject{["company_name"]=requestedName,["backup_base64"]=encoded});verify();if(name.Text!=requestedName||password.Password!=requestedPassword)return;digest=result.Text("digest");reviewedName=requestedName;results.Children.Clear();RenderReport(results,result);},Error,true));panel.Children.Add(results);
        if(await Dialog("Restore into a new company",panel,async()=>{verify();if(digest.Length==0||name.Text!=reviewedName)throw new Exception("Validate this backup and company name before restoring.");var result=await Api.Send("/api/backups/restore/commit",HttpMethod.Post,new JsonObject{["company_name"]=name.Text,["backup_base64"]=encoded,["digest"]=digest});verify();CompanyId=result.Text("company_id");},"Restore reviewed backup"))await LoadCompanies();
    }
    private async Task VyaparMigration()
    {
        var verify=CaptureOwnerImportAccess();
        var cid = CompanyId;
        var file = await ApexFiles.Pick(".vyb");
        if (file is null) return;verify();
        var encoded = Convert.ToBase64String(await ApexFiles.Read(file, 3_000_000));
        verify();var panel = Stack(); panel.MinWidth = 850;
        panel.Children.Add(Text(file.Name));
        panel.Children.Add(Text("Choose the import scope, validate the mapping, then review the preview. Existing books are preserved if validation fails."));
        var scope = Select("Import scope", [("posting", "Full transaction posting"), ("archive", "Masters and source archive only")]);
        panel.Children.Add(scope);
        var results = Stack();
        string ReviewPrompt(string selectedScope) => selectedScope == "posting" ? "I reviewed the mapping and reconciliation. Post these transactions atomically." : "I reviewed the masters and source archive. Historical transactions will remain unposted.";
        var accepted = new CheckBox { IsEnabled = false, Content = ReviewPrompt(Value(scope)) };
        JsonNode? prepared = null;
        string reviewedScope = "";
        var previewRevision = 0;
        bool Ready() => prepared is not null && reviewedScope == Value(scope) && prepared["errors"].Array().Count == 0 && (reviewedScope != "posting" || prepared.Flag("ready"));
        string Endpoint(string action) => Api.CompanyPath(cid, Value(scope) == "posting" ? $"/imports/vyapar-posting/{action}" : $"/imports/vyapar/{action}");
        void Reset()
        {
            previewRevision++;
            prepared = null; reviewedScope = ""; results.Children.Clear(); accepted.IsChecked = false; accepted.IsEnabled = false;
            accepted.Content = ReviewPrompt(Value(scope));
            RefreshDialogActions(true);
        }
        scope.SelectionChanged += (_, _) => Reset();
        accepted.Checked += (_, _) => RefreshDialogActions();
        accepted.Unchecked += (_, _) => RefreshDialogActions();
        panel.Children.Add(AsyncButton("Validate and preview", async () =>
        {
            verify();Reset();
            var requestRevision = previewRevision;
            var requestedScope = Value(scope);
            var preview = await Api.Send(Endpoint("preview"), HttpMethod.Post, new JsonObject { ["backup_base64"] = encoded });
            verify();if (requestRevision != previewRevision || requestedScope != Value(scope)) return;
            prepared = preview;
            reviewedScope = requestedScope;
            RenderReport(results, prepared);
            accepted.Content = ReviewPrompt(reviewedScope);
            accepted.IsEnabled = Ready();
        }, Error, true));
        panel.Children.Add(results); panel.Children.Add(accepted);
        if (await Dialog("Import Vyapar backup", panel, async () =>
        {
            verify();if (!Ready() || accepted.IsChecked != true) throw new Exception("Validate and review the selected scope before importing.");
            await Api.Send(Endpoint("commit"), HttpMethod.Post, new JsonObject { ["backup_base64"] = encoded, ["digest"] = prepared.Text("digest") });
        }, "Import reviewed backup", () => Ready() && accepted.IsChecked == true))
        {
            verify();await Refresh();verify();
            Success(reviewedScope == "posting" ? "Migration posted and reconciled." : "Masters and source archive imported. Historical transactions remain unposted.");
        }
    }
    private async Task MasterCsvImport()
    {
        var cid=CompanyId;var verify=CaptureFileSaveAccess();
        void Guard(){verify();if(!CanWrite)throw new InvalidOperationException("Current editor or owner access is required to import or recover an import.");}
        bool Supported()=>Api.Capabilities.Supports("master_import_receipts");
        void CurrentError(Exception error){if(ScopedFileExport.Current(verify))Error(error);}
        Guard();
        var receipt=new ImportReceiptRecovery(ImportReceiptRecovery.Location(CompleteBackupTransfer.PrivateDirectory,Api.Origin,Api.Email,cid));
        if(receipt.Saved is { } saved){
            var recoveryPanel=Stack();var message=Text("Original import is unconfirmed. Recovery reference: "+saved.Key+". Only this reference, type and fingerprint are stored; CSV contents are not saved. Check the receipt, or continue to select the original unchanged CSV.");recoveryPanel.Children.Add(message);
            var confirmed=false;
            recoveryPanel.Children.Add(AsyncButton("Check original import",async()=>{
                Guard();if(!Supported())throw new Exception("Reconnect to a server supporting import receipts.");
                var result=await Api.Send(Api.CompanyPath(cid,"/masters/import-receipts/"+Uri.EscapeDataString(saved.Key)));Guard();receipt.Confirmed(result.Text("operation_key"));confirmed=true;message.Text="Original import confirmed. Close or continue to refresh the records; no import will be repeated.";
            },CurrentError,true));
            var proceed=await Dialog("Recover original master import",recoveryPanel,()=>Task.CompletedTask,"Continue");Guard();
            if(confirmed){await Refresh();Success("Original import confirmed; no import was repeated.");return;}
            if(!proceed)return;
            if(!Supported())throw new Exception("The original import remains unresolved. A legacy request cannot replace it.");
        }
        Guard();var file=await ApexFiles.Pick(".csv");Guard();if(file is null)return;
        var bytes=await ApexFiles.Read(file,3_000_000);Guard();var table=Csv.Parse(Csv.Decode(bytes));if(table.Count<2||table.Count>501)throw new Exception("Choose a CSV with headers and 1–500 rows.");var fields=table[0].Select(h=>h.Trim().ToLowerInvariant().Replace(' ','_')).ToArray();if(!fields.Contains("name"))throw new Exception("The CSV needs a name column. Export a master CSV as a template.");var supported=new HashSet<string>{"name","gstin","address","phone","email","party_type","hsn","unit","sale_rate","purchase_rate","gst_rate","barcode","item_type","tax_treatment","track_stock"};Csv.ValidateColumns(table,fields,supported);var rows=new JsonArray();for(var i=1;i<table.Count;i++){var row=new JsonObject();for(var j=0;j<fields.Length&&j<table[i].Length;j++){var key=fields[j];if(!supported.Contains(key))continue;var value=table[i][j];if(key=="track_stock")row[key]=Csv.Boolean(value);else if(key is "sale_rate" or "purchase_rate" or "gst_rate")row[key]=Csv.Money(value);else row[key]=value;}rows.Add(row);}
        var panel=Stack();panel.MinWidth=750;
        var kind=Select("Master type",[("party","Parties"),("item","Items")],receipt.Saved?.Kind??"party");kind.IsEnabled=!receipt.Pending;panel.Children.Add(kind);
        if(!Supported())panel.Children.Add(Text("This server does not advertise exact import recovery. Legacy duplicate-name skipping is not a replay receipt.",12));
        var recoveryNotice=Text(receipt.Saved is { } original?"Unconfirmed original import: "+original.Key:"A supported server will retain the exact import receipt.",12);panel.Children.Add(recoveryNotice);
        var resultPanel=Stack();string reviewed="";JsonObject Body()=>new(){["kind"]=Value(kind),["rows"]=rows.Copy()};
        panel.Children.Add(AsyncButton("Validate and preview",async()=>{
            Guard();var selected=Value(kind);var body=Body();body["dry_run"]=true;
            var result=await Api.Send(Api.CompanyPath(cid,"/masters/import"),HttpMethod.Post,body);Guard();
            if(Value(kind)!=selected)return;reviewed=selected;resultPanel.Children.Clear();RenderReport(resultPanel,result);Table(resultPanel,new JsonArray(rows.Take(10).Select(r=>r.Copy()).ToArray()),"First 10 rows");
        },CurrentError,true));panel.Children.Add(resultPanel);
        if(await Dialog("Import "+file.Name,panel,async()=>{
            Guard();if(reviewed!=Value(kind))throw new Exception("Validate and review the import first.");
            var body=Body();body["dry_run"]=false;var attempt=receipt.Begin(body.ToJsonString(),Value(kind),Supported());
            kind.IsEnabled=!receipt.Pending;recoveryNotice.Text=receipt.Saved is { } pending?"Unconfirmed original import: "+pending.Key+". Retry only the original file/type; reopening this workflow can check its receipt.":"Legacy import request.";
            try{var result=await Api.Send(Api.CompanyPath(cid,"/masters/import"),HttpMethod.Post,JsonNode.Parse(attempt.Body),attempt.Key);if(attempt.Key is not null)receipt.Confirmed(result.Text("operation_key"));Guard();}
            catch(Exception error){receipt.Failed(attempt,(error as ApiFailure)?.Status??0);throw;}
            finally{receipt.End();kind.IsEnabled=!receipt.Pending;}
        },"Import reviewed masters",()=>CanWrite&&ScopedFileExport.Current(verify),unresolved:()=>receipt.Pending)) {Guard();await Refresh();Success("Master import confirmed.");}
    }
    private async Task DataExport()
    {
        var cid=CompanyId;var exportAccess=CaptureFileSaveAccess();var kind=Select("Data",[("all","Full company JSON"),("party","Parties"),("item","Items"),("reconciliation","Vyapar reconciliation"),("archive","Vyapar source archive")]);var format=Select("Master export format",[("xlsx","XLSX"),("csv","CSV"),("pdf","PDF")]);var panel=Stack();panel.Children.Add(kind);panel.Children.Add(format);await Dialog("Export company data",panel,async()=>{var selected=Value(kind);var suffix=selected=="all"?"/data-export.json":selected=="reconciliation"?"/imports/vyapar-posting/reconciliation":selected=="archive"?"/imports/vyapar/archive.json":$"/masters/export.{Value(format)}?kind={selected}";var ext=selected is "all" or "reconciliation" or "archive"?"json":Value(format);if(await ScopedFileExport.Download(exportAccess,()=>Api.Download(Api.CompanyPath(cid,suffix)),null,(bytes,verify)=>ApexFiles.Save(bytes,"apex-"+selected+"."+ext,verify))==false)throw new Exception("Choose a destination to save the export.");},"Export");
    }
    private async Task Security()
    {
        var current=new PasswordBox{Header="Current password"};var next=new PasswordBox{Header="New password · 8–128 characters"};var panel=Stack();panel.Children.Add(Text("Changing your password signs out every device, including this one."));panel.Children.Add(current);panel.Children.Add(next);panel.Children.Add(AsyncButton("Sign out other devices",async()=>{var result=await Api.Send("/api/auth/logout-other-sessions",HttpMethod.Post);Success(result.Text("revoked")+" other sessions signed out.");},Error));
        if(await Dialog("Password and sessions",panel,async()=>{await Api.Send("/api/auth/change-password",HttpMethod.Post,new JsonObject{["current_password"]=current.Password,["new_password"]=next.Password});},"Change password")){Api.ForgetSession();ShowLogin();}
    }
    private async Task RecoveryCodes()
    {
        var exportAccess=CaptureFileSaveAccess();var password=new PasswordBox{Header="Current password"};var panel=Stack();panel.Children.Add(Text("Generating codes replaces any previous unused codes. Store them outside this device. Each code works once."));panel.Children.Add(password);JsonNode? result=null;
        if(await Dialog("Generate recovery codes",panel,async()=>{await ScopedFileExport.Run(exportAccess,async()=>{result=await Api.Send("/api/auth/recovery-codes",HttpMethod.Post,new JsonObject{["current_password"]=password.Password});exportAccess();return true;});},"Generate new codes")&&ScopedFileExport.Current(exportAccess)&&result is not null)
        {
            var codes=string.Join(Environment.NewLine,result?["codes"].Array().Select(r=>r.Text())??Array.Empty<string>());var view=Stack();var output=new TextBox{Text=codes,IsReadOnly=true,AcceptsReturn=true,FontFamily=new Microsoft.UI.Xaml.Media.FontFamily("Consolas")};view.Children.Add(output);bool closed=false;
            void Verify(){exportAccess();if(closed)throw new InvalidOperationException("This recovery-code view is closed.");}
            view.Children.Add(AsyncButton("Save recovery codes",async()=>{await ScopedFileExport.Run(Verify,()=>ApexFiles.Save(Encoding.UTF8.GetBytes("Apex Books recovery codes\n"+codes),"apex-recovery-codes.txt",Verify));},Error));
            void Invalidate(){codes="";output.Text="";view.Children.Clear();view.Children.Add(Text("Access changed. Close this view and reopen account recovery after signing in."));}
            ReadAccessInvalidated+=Invalidate;
            try{await Dialog("Save your one-use recovery codes",view,()=>Task.CompletedTask,"Done");}finally{closed=true;codes="";output.Text="";ReadAccessInvalidated-=Invalidate;}
        }
    }
    private async Task AuditHistory()
    {var panel=Stack();panel.MinWidth=850;Table(panel,(await Api.Send(PathFor("/audit-events"))).Array(),"Latest audit events");await Dialog("Audit history",panel,()=>Task.CompletedTask,"Done");}
}
