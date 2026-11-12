using ApexBooks_Windows.Models;
using ApexBooks_Windows.Services;
using ApexBooks_Windows.Views;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Markup;
using System.Text.Json.Nodes;
using static ApexBooks_Windows.Views.NativeUi;

namespace ApexBooks_Windows;

public sealed partial class MainPage : Page
{
    internal ApexApi Api { get; }
    internal JsonArray Companies = new(), Records = new(), Banks = new();
    internal JsonObject Company = new();
    internal string CompanyId = "", CurrentPage = "dashboard";
    private bool recordsReady;
    private event Action? ReadAccessInvalidated;
    internal bool CanWrite => recordsReady && Company.Text("role") is ("owner" or "editor");
    internal bool IsOwner => Company.Text("role") == "owner";
    private NavigationView navigation = new();
    private readonly ContentControl host = new(){HorizontalContentAlignment=HorizontalAlignment.Stretch,VerticalContentAlignment=VerticalAlignment.Stretch};
    private readonly ComboBox companyPicker = new() { PlaceholderText = "Company", HorizontalAlignment = HorizontalAlignment.Stretch };
    internal readonly StackPanel Body = Stack(20);
    private Dictionary<string,decimal>? partyNet;private (decimal Receive,decimal Pay)? partyTotals;
    private readonly InfoBar notice = new() { IsClosable = true, Margin = new Thickness(24, 8, 24, 0) };
    private readonly ProgressBar progress = new() { IsIndeterminate = true, Height = 3, Visibility = Visibility.Collapsed };
    private bool changingCompanies, shellReady;
    private int generation, workspaceGeneration, companyLoads, refreshSequence, saveAccessEpoch;
    private sealed record PosDraft(JsonObject Body,string Key,RetrySubmission Submission);
    private readonly Dictionary<string,PosDraft> posDrafts=new();
    private Action? leavePage;
    private Func<bool>? hasUnsavedPage;
    private Func<bool>? hasPendingPage;

    public MainPage()
    {
        InitializeComponent();
        FontFamily=WorkspaceFont;
        Root.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });Root.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });Root.RowDefinitions.Add(new RowDefinition());
        Root.Children.Add(progress);Grid.SetRow(notice,1);Root.Children.Add(notice);Grid.SetRow(host,2);Root.Children.Add(host);
        var origin = ApexApi.ProductionOrigin;
#if DEBUG
        origin = Environment.GetEnvironmentVariable("APEX_BOOKS_API_ORIGIN")
            ?? System.Reflection.Assembly.GetExecutingAssembly().GetCustomAttributes(typeof(System.Reflection.AssemblyMetadataAttribute), false)
                .Cast<System.Reflection.AssemblyMetadataAttribute>()
                .FirstOrDefault(value => value.Key == "ApexApiOrigin")?.Value
            ?? "http://127.0.0.1:8012";
#endif
        Api = new ApexApi(origin);
        ApexFiles.CaptureSaveAccess=CaptureFileSaveAccess;
        Api.SessionExpired += () => DispatcherQueue.TryEnqueue(()=>{if(!Api.SignedIn)ShowLogin();});
        Loaded += async (_, _) => { if (Api.RestoreSession()) await Run(LoadCompanies); else ShowLogin(); };
    }

    private Action CaptureFileSaveAccess()
    {
        var session=Api.SessionGeneration;var cid=CompanyId;var workspace=workspaceGeneration;var access=saveAccessEpoch;var ready=recordsReady;
        void Verify(){if(!Api.SignedIn||Api.SessionGeneration!=session||CompanyId!=cid||workspaceGeneration!=workspace||saveAccessEpoch!=access||(ready&&!recordsReady))throw new InvalidOperationException("Company or sign-in access changed while choosing a save location. Reopen the export in the current workspace.");}
        Verify();return Verify;
    }

    private Action CaptureOwnerImportAccess()
    {
        var access=CaptureFileSaveAccess();
        void Verify(){access();if(!CanWrite||!IsOwner)throw new InvalidOperationException("Current owner access is required to restore or migrate a backup. Your inputs are preserved.");}
        Verify();return Verify;
    }

    private Action CaptureRecurringWriteAccess()
    {
        var access=CaptureFileSaveAccess();
        void Verify(){access();if(!CanWrite)throw new InvalidOperationException("Current editor or owner access is required to save a recurring schedule or generate a draft. Your inputs and any unresolved request are preserved.");}
        Verify();return Verify;
    }

    internal string PathFor(string suffix = "") => Api.CompanyPath(CompanyId, suffix);
    internal void Error(Exception e) {if(NativeUi.DialogError(e))return; notice.Severity = InfoBarSeverity.Error; notice.Message = e.Message; notice.IsOpen = true; }
    internal void Success(string message) { notice.Severity = InfoBarSeverity.Success; notice.Message = message; notice.IsOpen = true; }
    private async Task FinishConfirmedImport(string message)
    {
        var cid=CompanyId;var workspace=workspaceGeneration;var session=Api.SessionGeneration;
        bool Current()=>Api.SignedIn&&Api.SessionGeneration==session&&CompanyId==cid&&workspaceGeneration==workspace;
        try{await Refresh();if(Current())Success(message);}
        catch(OperationCanceledException){throw;}
        catch(Exception error){
            if(Current())throw new ApiFailure((error as ApiFailure)?.Status??0,
                message+" The list could not refresh. Do not repeat the import; refresh the current company after access or connectivity is restored. "+error.Message);
        }
    }

    internal async Task Run(Func<Task> action)
    {
        progress.Visibility = Visibility.Visible;
        try { await action(); } catch (Exception e) { Error(e); } finally { progress.Visibility = Visibility.Collapsed; }
    }

    private void ShowLogin()
    {
        leavePage=null;hasUnsavedPage=null;hasPendingPage=null;posDrafts.Clear();CompanyId = ""; Company = new(); Records = new(); Banks = new();recordsReady=false; Companies = new(); generation++;workspaceGeneration++;companyLoads++;refreshSequence++;CurrentPage="dashboard"; Body.Children.Clear(); NativeUi.CloseDialog();
        var card = Stack(20); card.MaxWidth = 380;
        card.Children.Add(AppLogo(340));
        card.Children.Add(Text("Your business, in balance.", 28, true));
        card.Children.Add(Text("Sign in to your shared workspace. Documents and balances stay connected across devices."));
        var email = Input("Email address"); var password = new PasswordBox { Header = "Password", MinHeight = 42 };
        var remember = new CheckBox { Content = "Keep me signed in on this Windows account" };
        card.Children.Add(email); card.Children.Add(password); card.Children.Add(remember);
        card.Children.Add(AsyncButton("Sign in", async () => { await Api.Login(email.Text.Trim(), password.Password, remember.IsChecked == true); password.Password = ""; await LoadCompanies(); }, Error, true));
        card.Children.Add(AsyncButton("Create an account", Register, Error)); card.Children.Add(AsyncButton("Use a recovery code", Recover, Error));
        card.Children.Add(Text("Server · " + new Uri(Api.Origin).Host, 11));
        var outer = new ScrollViewer { Content = Card(card), MaxWidth=460, HorizontalAlignment = HorizontalAlignment.Stretch, VerticalAlignment = VerticalAlignment.Center, Margin = new Thickness(24), MaxHeight = 800 };
        host.Content = outer;
    }

    private async Task Register()
    {
        var panel = Stack(); var email = Input("Email address"); var password = new PasswordBox { Header = "Password · at least 8 characters" }; var repeat = new PasswordBox { Header = "Confirm password" };
        panel.Children.Add(email); panel.Children.Add(password); panel.Children.Add(repeat);
        var saved = await Dialog("Create your Apex Books account", panel, async () =>
        {
            if (password.Password != repeat.Password) throw new Exception("The passwords do not match.");
            await Api.Send("/api/auth/register", System.Net.Http.HttpMethod.Post, new JsonObject { ["email"] = email.Text.Trim(), ["password"] = password.Password });
            await Api.Login(email.Text.Trim(), password.Password, false);
        }, "Create account");
        if (saved) await LoadCompanies();
    }

    private async Task Recover()
    {
        var panel = Stack(); var email = Input("Email address"); var code = Input("One-use recovery code"); var password = new PasswordBox { Header = "New password" };
        panel.Children.Add(email); panel.Children.Add(code); panel.Children.Add(password);
        if (await Dialog("Recover account access", panel, async () => { await Api.Send("/api/auth/recover", System.Net.Http.HttpMethod.Post, new JsonObject { ["email"] = email.Text.Trim(), ["code"] = code.Text.Trim(), ["new_password"] = password.Password }); }, "Reset access")) Success("Password reset. Sign in with your new password.");
    }

    internal async Task LoadCompanies()
    {
        var stamp=workspaceGeneration;var request=++companyLoads;
        _=Api.EnsureCapabilities();var loaded=(await Api.Send("/api/companies")).Array();
        if(!Api.SignedIn||stamp!=workspaceGeneration||request!=companyLoads)return;
        Companies=loaded;
        if (!shellReady) BuildShell(); else host.Content=navigation;
        changingCompanies = true; companyPicker.Items.Clear();
        foreach (var company in Companies) companyPicker.Items.Add(new ComboBoxItem { Content = ClientCapabilities.CompanyLabel(company)+" · "+Friendly(company.Text("role")), Tag = company.Text("id") });
        SelectValue(companyPicker, CompanyId); if (companyPicker.SelectedIndex < 0 && companyPicker.Items.Count > 0) companyPicker.SelectedIndex = 0;
        changingCompanies = false;
        if (companyPicker.SelectedIndex >= 0) await ChooseCompany();
        else { if(!Api.SignedIn||stamp!=workspaceGeneration||request!=companyLoads)return;CompanyId="";Company=new();Records=new();Banks=new();recordsReady=false;posDrafts.Clear();leavePage=null;hasUnsavedPage=null;hasPendingPage=null;generation++;workspaceGeneration++;refreshSequence++;NativeUi.CloseDialog();Body.Children.Clear(); Body.Children.Add(Text("Welcome to Apex Books", 30, true)); Body.Children.Add(Text("Create your first company to start recording transactions.")); Body.Children.Add(AsyncButton("Create company", () => CompanyForm(), Error, true));if(!Api.Capabilities.HasCoreAdditions)Body.Children.Add(CapabilityNotice()); }
    }

    private void BuildShell()
    {
        navigation = new NavigationView { IsSettingsVisible = false, RequestedTheme = ElementTheme.Light, PaneDisplayMode = NavigationViewPaneDisplayMode.Auto, OpenPaneLength = 252, CompactModeThresholdWidth=640, ExpandedModeThresholdWidth=1100, IsBackButtonVisible = NavigationViewBackButtonVisible.Collapsed };
        navigation.Resources["NavigationViewDefaultPaneBackground"] = Brush(0x28,0x2B,0x30);
        navigation.Resources["NavigationViewExpandedPaneBackground"] = Brush(0x28,0x2B,0x30);
        navigation.Foreground=Brush(255,255,255);
        navigation.Resources["NavigationViewItemForeground"]=Brush(255,255,255);
        navigation.Resources["NavigationViewItemForegroundSelected"]=Brush(255,255,255);
        navigation.Resources["NavigationViewItemBackgroundSelected"]=Brush(0x39,0x3D,0x42);
        navigation.Resources["NavigationViewItemBackgroundPointerOver"]=Brush(0x39,0x3D,0x42);
        navigation.Resources["NavigationViewItemOnLeftMinHeight"]=44.0;navigation.Resources["NavigationViewSelectionIndicatorForeground"]=Brush(0x2C,0xC0,0x71);
        var pane = Stack(8);pane.Margin=new Thickness(4,6,8,10);var brandRow=Stack(10);brandRow.Orientation=Orientation.Horizontal;brandRow.VerticalAlignment=VerticalAlignment.Center;
        brandRow.Children.Add(AppLogo(150));
        pane.Children.Add(brandRow);
        companyPicker.HorizontalAlignment=HorizontalAlignment.Stretch;companyPicker.MinHeight=44;companyPicker.RequestedTheme=ElementTheme.Dark;companyPicker.Background=Brush(0x39,0x3D,0x42);companyPicker.Foreground=Brush(255,255,255);companyPicker.BorderBrush=Brush(0x56,0x5C,0x65);pane.Children.Add(companyPicker);navigation.PaneHeader=pane;
        companyPicker.SelectionChanged += async (_, _) => { if (!changingCompanies) await Run(ChooseCompany); };
        Microsoft.UI.Xaml.Automation.AutomationProperties.SetName(companyPicker,"Choose company");
        foreach (var group in FeatureCatalog.Navigation.Where(f=>f.Key!="settings").GroupBy(f=>f.Group))
        {
            var expandable=group.Key is "Sales" or "Purchase" or "Purchases";
            var parent=expandable?new NavigationViewItem{Content=group.Key,Icon=new SymbolIcon(group.Key=="Sales"?Symbol.Document:Symbol.Shop)}:null;
            if(parent is not null)navigation.MenuItems.Add(parent);else navigation.MenuItems.Add(new NavigationViewItemHeader{Content=group.Key.ToUpperInvariant(),Foreground=Brush(0xBC,0xC4,0xCD)});
            foreach(var feature in group){
            var symbol = feature.Key switch { "dashboard" => Symbol.Home, "party" => Symbol.People, "item" => Symbol.Shop, "reports" => Symbol.Document, "settings" => Symbol.Setting, "bank" => Symbol.World, "ledger" => Symbol.Library, "day_book" => Symbol.Calendar, _ => Symbol.Page };
            var item=new NavigationViewItem { Content = feature.Title, Tag = feature.Key, Icon = new SymbolIcon(symbol) };
            if(parent is not null)parent.MenuItems.Add(item);else navigation.MenuItems.Add(item);
            }
        }
        navigation.FooterMenuItems.Add(new NavigationViewItem { Content="Settings",Tag="settings",Icon=new SymbolIcon(Symbol.Setting) });
        navigation.FooterMenuItems.Add(new NavigationViewItem { Content = "Add company", Tag = "new_company", Icon = new SymbolIcon(Symbol.Add) });
        navigation.FooterMenuItems.Add(new NavigationViewItem { Content = "Sign out", Tag = "logout", Icon = new SymbolIcon(Symbol.LeaveChat) });
        navigation.ItemInvoked += async (_, args) => await Run(async () =>
        {
            var key = (args.InvokedItemContainer as NavigationViewItem)?.Tag?.ToString();
            if (key == "logout") {if(posDrafts.Values.Any(d=>d.Submission.Unresolved)||hasPendingPage?.Invoke()==true){Error(new Exception("A held sale may already have posted. Return to its company’s Point of Sale and retry Complete sale to recover the original outcome before signing out."));return;}if(posDrafts.Count>0||hasUnsavedPage?.Invoke()==true){var prompt=Stack();prompt.Children.Add(Text("Held POS carts exist only in this session. Signing out discards them. Resolve any sale with an unknown save outcome before leaving."));if(!await Dialog("Discard held carts and sign out?",prompt,()=>Task.CompletedTask,"Sign out and discard"))return;}try{await Api.Logout();}finally{ShowLogin();}}
            else if (key == "new_company") await CompanyForm();
            else if (key is not null && CompanyId.Length > 0) await Navigate(key);
        });
        Body.Margin = new Thickness(30,24,30,36);Body.RequestedTheme=ElementTheme.Light;
        var content=new Grid{RequestedTheme=ElementTheme.Light,Background=Brush(0xF4, 0xF5, 0xF7)};content.RowDefinitions.Add(new RowDefinition{Height=GridLength.Auto});content.RowDefinitions.Add(new RowDefinition());content.Children.Add(BuildWorkspaceHeader());
        var scroll=new ScrollViewer {Content=Body,HorizontalScrollBarVisibility=ScrollBarVisibility.Disabled,VerticalScrollBarVisibility=ScrollBarVisibility.Auto};Grid.SetRow(scroll,1);content.Children.Add(scroll);navigation.AlwaysShowHeader=false;navigation.Content=content;host.Content=navigation;shellReady=true;InstallShortcuts(navigation);
    }

    private async Task ChooseCompany()
    {
        var id = Value(companyPicker); if (id.Length == 0) return;
        var leave=leavePage;leavePage=null;leave?.Invoke();hasUnsavedPage=null;hasPendingPage=null;
        CompanyId = id; Company = Companies.OfType<JsonObject>().First(r => r.Text("id") == id);Records=new();Banks=new();recordsReady=false;++generation;var current=++workspaceGeneration;var request=++refreshSequence;NativeUi.CloseDialog();
        Body.Children.Clear(); Body.Children.Add(Text("Loading " + Company.Text("name") + "…", 22, true));
        var loaded=await Api.LoadCompanyCore(id);
        if (current != workspaceGeneration||request!=refreshSequence) return;
        Records = loaded.Records; Banks = loaded.Banks;recordsReady=true; await Navigate(CurrentPage);
    }

    internal async Task Refresh()
    {
        var cid=CompanyId;if(cid.Length==0||!Api.SignedIn)return;
        var current=workspaceGeneration;var session=Api.SessionGeneration;var request=++refreshSequence;
        await ScopedCoreRefresh.Run(Api.Records(cid),Api.Send(Api.CompanyPath(cid,"/bank-accounts")),
            ()=>Api.SignedIn&&session==Api.SessionGeneration&&cid==CompanyId&&current==workspaceGeneration&&request==refreshSequence,
            ()=>{saveAccessEpoch++;Records=new();Banks=new();recordsReady=false;ReadAccessInvalidated?.Invoke();},
            (rows,banks)=>{Records=rows;Banks=banks.Array();recordsReady=true;},
            ()=>Navigate(CurrentPage));
    }

    internal async Task Navigate(string page)
    {
        var leave=leavePage;leavePage=null;leave?.Invoke();hasUnsavedPage=null;hasPendingPage=null;
        ++generation;CurrentPage = page; Body.Children.Clear(); notice.IsOpen = false; workspaceCompany.Text = Company.Text("name");
        navigation.SelectedItem=FindNavigation(page);
        var heading=new Grid{ColumnSpacing=12,RowSpacing=6,VerticalAlignment=VerticalAlignment.Bottom};
        heading.Children.Add(Text(page=="dashboard"?"Business overview":FeatureCatalog.Title(page), 30, true));
        var detail = Text(Company.Text("tax_mode") == "regular" ? "GST registered · " + Company.Text("gstin") : Company.Text("tax_mode") == "composition" ? "Composition company" : "Not GST registered", 12); detail.Foreground = Muted; detail.VerticalAlignment=VerticalAlignment.Bottom; detail.Margin=new Thickness(0,0,0,3); heading.Children.Add(detail);Body.Children.Add(heading);
        bool? compactHeading=null;void ArrangeHeading(){var narrow=heading.ActualWidth<600;if(compactHeading==narrow)return;compactHeading=narrow;heading.ColumnDefinitions.Clear();heading.RowDefinitions.Clear();heading.ColumnDefinitions.Add(new ColumnDefinition{Width=new GridLength(1,GridUnitType.Star)});heading.RowDefinitions.Add(new RowDefinition{Height=GridLength.Auto});if(narrow){heading.RowDefinitions.Add(new RowDefinition{Height=GridLength.Auto});Grid.SetColumn(detail,0);Grid.SetRow(detail,1);}else{heading.ColumnDefinitions.Add(new ColumnDefinition{Width=GridLength.Auto});Grid.SetColumn(detail,1);Grid.SetRow(detail,0);}}ArrangeHeading();heading.SizeChanged+=(_,_)=>ArrangeHeading();
        if(!Api.Capabilities.HasCoreAdditions)Body.Children.Add(CapabilityNotice());
        if(!recordsReady){Body.Children.Add(Text("Loading complete company history…",20,true));Body.Children.Add(Text("Balances and billing become available once all records are ready. No partial totals are shown."));Body.Children.Add(AsyncButton("Retry company data",Refresh,Error));return;}
        if (page == "dashboard") await Dashboard();
        else if (page == "reports") await ReportsPage();
        else if (page == "settings") await SettingsPage();
        else if (page == "commerce") await CommercePage();
        else if (page == "bank") await BankPage();
        else if (page == "ledger") await LedgerPage();
        else if (page == "day_book") await DayBookPage();
        else if (page == "pos") await PosPage();
        else Registers(page);
    }

    private async Task Dashboard()
    {
        await RichDashboard();
    }

    private void Registers(string kind)
    {
        var toolbar = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 12 };
        var search = Input("Search name or reference"); search.Width = 340;
        var add = AsyncButton("Add " + FeatureCatalog.Singular(kind), () => NewEntry(kind), Error, true); add.IsEnabled = CanWrite; toolbar.Children.Add(add); toolbar.Children.Add(AsyncButton("Refresh", Refresh, Error)); toolbar.Children.Add(search); Body.Children.Add(toolbar);
        if (kind == "item") { var stock = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 10 }; var opening = AsyncButton("Opening stock", StockOpening, Error); var adjust = AsyncButton("Adjust stock", StockAdjust, Error); opening.IsEnabled = adjust.IsEnabled = CanWrite; stock.Children.Add(opening); stock.Children.Add(adjust); Body.Children.Add(stock); }
        if(kind=="party"&&WhatsAppShare.OverdueByParty(Records,J.Today) is {Count:>0} overdue)toolbar.Children.Add(AsyncButton($"Remind overdue ({overdue.Count})",()=>RemindOverdue(overdue),Error));
        if(CanWrite && kind is "payment_in" or "payment_out" or "credit_note" or "debit_note")Body.Children.Add(AsyncButton(kind is "payment_in" or "payment_out"?"Apply / refund advance":"Apply / refund note credit",()=>SettleBalance(kind is "credit_note" or "debit_note"),Error));
        var master=kind is "party" or "item";var masterStatus=Select("Master status",[("all","All masters"),("active","Active"),("archived","Archived")]);var page=0;const int size=50;
        var period=Select("Period",[("all","All dates"),("month","This month"),("fy","This financial year"),("custom","Custom dates")]);var from=new DateInput("From",J.FinancialStart);var to=new DateInput("To",J.Today);
        var party=Select("Customer / supplier",new[]{("all","All parties")}.Concat(Records.OfType<JsonObject>().Where(r=>r.Text("kind")==kind).Select(r=>r.Text("name")).Distinct().Order().Select(n=>(n,n))));var status=Select("Status",new[]{"All statuses","Unpaid","Part settled","Settled","Draft","Converted","Posted","Cancelled","Advance available","Advance settled","Credit available","Credit settled"}.Select(n=>(n,n)));var sort=Select("Sort",[("new","Newest first"),("old","Oldest first"),("name","Name A–Z"),("amount","Highest amount")]);
        toolbar.Children.Add(Button("Clear filters",()=>{search.Text="";SelectValue(period,"all");SelectValue(party,"all");SelectValue(status,"All statuses");SelectValue(sort,"new");}));
        if(!CanWrite)Body.Children.Add(Text("Read-only access · you can inspect records and export documents. Ask an owner for editor access to make changes.",12));
        if(!master){var filters=Stack();filters.Children.Add(Columns(period,party,status,sort));filters.Children.Add(Columns(from.View,to.View));Body.Children.Add(new Expander{Header="Filter documents",Content=filters,IsExpanded=false,HorizontalContentAlignment=HorizontalAlignment.Stretch,HorizontalAlignment=HorizontalAlignment.Stretch});}else Body.Children.Add(Columns(sort,masterStatus));
        var metrics=Stack();var holder=Stack();var caption=Text("",12);var pager=new StackPanel{Orientation=Orientation.Horizontal,Spacing=10};Button previous=null!,next=null!;Body.Children.Add(metrics);Body.Children.Add(holder);Body.Children.Add(pager);
        void Draw(bool reset=true){if(reset)page=0;holder.Children.Clear();metrics.Children.Clear();var range=Value(period);from.View.Visibility=to.View.Visibility=!master&&range=="custom"?Visibility.Visible:Visibility.Collapsed;var start=range=="fy"?J.FinancialStart:range=="month"?BusinessCalendar.Today.ToString("yyyy-MM-01"):range=="custom"?from.Value:"";var end=range is "month" or "fy"?J.Today:range=="custom"?to.Value:"";
            var source=Records.OfType<JsonObject>().Where(r=>r.Text("kind")==kind&&(!master||Value(masterStatus)=="all"||WorkflowMasterValues.IsActive(r)==(Value(masterStatus)=="active"))&&(r.Text("name")+" "+r.Text("number")+" "+r["data"].Text("phone")+" "+r["data"].Text("barcode")+" "+r["data"].Text("hsn")).Contains(search.Text,StringComparison.OrdinalIgnoreCase)&&(master||((start.Length==0||string.CompareOrdinal(r.Text("date"),start)>=0)&&(end.Length==0||string.CompareOrdinal(r.Text("date"),end)<=0)&&(Value(party)=="all"||r.Text("name")==Value(party))&&(Value(status)=="All statuses"||new RecordRow(r).Status==Value(status)))));
            source=Value(sort) switch{"old"=>source.OrderBy(r=>r.Text("date")).ThenBy(r=>r["data"].Text("created_at")).ThenBy(r=>r.Text("number")),"name"=>source.OrderBy(r=>r.Text("name"),StringComparer.OrdinalIgnoreCase),"amount"=>source.OrderByDescending(r=>r.Number("amount")),_=>source.OrderByDescending(r=>r.Text("date")).ThenByDescending(r=>r["data"].Text("created_at")).ThenByDescending(r=>r.Text("number"))};var all=source.ToArray();page=Math.Clamp(page,0,Math.Max(0,(all.Length-1)/size));
            if(kind=="party"&&partyTotals is {} owed)AddMetrics(metrics,("You'll get",owed.Receive),("You'll pay",owed.Pay));
            if(master)metrics.Children.Add(Text($"{all.Length} {FeatureCatalog.Title(kind).ToLowerInvariant()}"+(kind=="party"?" · click a party for transactions and balances":""),14,true));else if(kind is "sales_invoice" or "purchase_bill")AddMetrics(metrics,("Posted value",all.Where(r=>WorkflowMasterValues.IsPostedRecord(r)).Sum(r=>r.Number("amount"))),("Outstanding",all.Where(r=>WorkflowMasterValues.IsPostedRecord(r)).Sum(r=>r.Number("outstanding"))),("Unpaid documents",all.Count(r=>WorkflowMasterValues.IsPostedRecord(r)&&r.Number("outstanding")>0)),("Settled documents",all.Count(r=>WorkflowMasterValues.IsPostedRecord(r)&&r.Number("outstanding")<=0)));else AddMetrics(metrics,("Documents",all.Length),("Total value",all.Sum(r=>r.Number("amount"))));
            if(all.Length==0)holder.Children.Add(Card(Text("No records match these filters.")));else AddRecordList(all.Skip(page*size).Take(size),holder);caption.Text=all.Length==0?"0 records":$"Showing {page*size+1}–{Math.Min((page+1)*size,all.Length)} of {all.Length}";previous.IsEnabled=page>0;next.IsEnabled=(page+1)*size<all.Length;
        }
        partyNet=null;partyTotals=null;
        if(kind=="party"&&Api.Capabilities.Supports("party_balances")){var stamp=generation;var cid=CompanyId;_=Run(async()=>{var result=await Api.Send(Api.CompanyPath(cid,"/parties/balances"));if(stamp!=generation||cid!=CompanyId)return;partyNet=result["rows"].Array().ToDictionary(r=>r.Text("party_id"),r=>r.Number("net"));partyTotals=(result["totals"].Number("to_receive"),result["totals"].Number("to_pay"));Draw(false);});}
        previous=Button("Previous",()=>{page--;Draw(false);});next=Button("Next",()=>{page++;Draw(false);});pager.Children.Add(previous);pager.Children.Add(caption);pager.Children.Add(next);search.TextChanged+=(_,_)=>Draw();foreach(var choice in new[]{period,party,status,sort,masterStatus})choice.SelectionChanged+=(_,_)=>Draw();from.Picker.DateChanged+=(_,_)=>Draw();to.Picker.DateChanged+=(_,_)=>Draw();Draw();
    }

    private void AddRecordList(IEnumerable<JsonObject> records, Panel? target = null)
    {
        target ??= Body; var rows = records.Select(r => new RecordRow(r)).ToList();
        if (rows.Count == 0) { target.Children.Add(Card(Text("No records here yet. Add an entry to get started."))); return; }
        foreach(var row in rows){
            if(row.Kind=="party"&&partyNet is not null){var net=partyNet.GetValueOrDefault(row.Id);row.PartyBalance=net>0?"Get "+J.Money(net):net<0?"Pay "+J.Money(-net):"Settled";}
            row.EditCommand=new CommunityToolkit.Mvvm.Input.AsyncRelayCommand(()=>Run(()=>EditRow(row.Source)),()=>Editable(row));
            row.PdfCommand=new CommunityToolkit.Mvvm.Input.AsyncRelayCommand(()=>Run(()=>PreviewDocument(row.Source)),()=>Printable(row));row.PdfVisibility=Printable(row)?Visibility.Visible:Visibility.Collapsed;
            row.OpenCommand=new CommunityToolkit.Mvvm.Input.AsyncRelayCommand(()=>Run(async()=>{if(row.Kind=="party")await PartyStatement(row.Source);else if(row.Kind=="item"&&Editable(row))await EditRow(row.Source);else await TransactionDetails(row.Source);}),()=>true);
        }
        var list = new ListView { ItemsSource = rows, SelectionMode = ListViewSelectionMode.Single, MaxHeight = 650, IsItemClickEnabled = true, CornerRadius=new CornerRadius(14), BorderBrush=Brush(0xF0, 0xE5, 0xDB),BorderThickness=new Thickness(1), Background = new Microsoft.UI.Xaml.Media.SolidColorBrush(Microsoft.UI.Colors.White) };
        list.ItemContainerStyle=new Style(typeof(ListViewItem)){Setters={new Setter(Control.HorizontalContentAlignmentProperty,HorizontalAlignment.Stretch),new Setter(Control.PaddingProperty,new Thickness(0)),new Setter(FrameworkElement.MarginProperty,new Thickness(0))}};
        var wideTemplate = (DataTemplate)XamlReader.Load("""
          <DataTemplate xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"><Grid Padding="18,14" ColumnSpacing="10"><Grid.ColumnDefinitions><ColumnDefinition Width="82"/><ColumnDefinition Width="2*"/><ColumnDefinition Width="72"/><ColumnDefinition Width="100"/><ColumnDefinition Width="110"/><ColumnDefinition Width="132"/></Grid.ColumnDefinitions><TextBlock Text="{Binding Date}" FontSize="12" VerticalAlignment="Center"/><StackPanel Grid.Column="1"><Button Command="{Binding OpenCommand}" Padding="0" BorderThickness="0" Background="Transparent" HorizontalAlignment="Stretch" HorizontalContentAlignment="Left" FontSize="12" FontWeight="SemiBold" ToolTipService.ToolTip="{Binding PrimaryText}"><TextBlock Text="{Binding PrimaryText}" TextTrimming="CharacterEllipsis"/></Button><TextBlock Text="{Binding SecondaryText}" FontSize="12" Foreground="#796c63" TextTrimming="CharacterEllipsis"/></StackPanel><TextBlock Grid.Column="2" Text="{Binding Status}" FontSize="12" VerticalAlignment="Center" Foreground="{Binding StatusBrush}"/><TextBlock Grid.Column="3" Text="{Binding Amount}" FontWeight="SemiBold" HorizontalAlignment="Right" VerticalAlignment="Center"/><TextBlock Grid.Column="4" Text="{Binding BalanceValue}" FontSize="12" HorizontalAlignment="Right" VerticalAlignment="Center"/><StackPanel Grid.Column="5" Orientation="Horizontal" Spacing="6" VerticalAlignment="Center"><Button Content="Edit" Command="{Binding EditCommand}" FontSize="12" MinHeight="44" Padding="10,6" CornerRadius="8"/><Button Content="PDF" Command="{Binding PdfCommand}" Visibility="{Binding PdfVisibility}" FontSize="12" MinHeight="44" Padding="10,6" CornerRadius="8"/></StackPanel></Grid></DataTemplate>
          """);
        var compactTemplate=(DataTemplate)XamlReader.Load("""
          <DataTemplate xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation">
            <StackPanel Padding="18,16" Spacing="12">
              <Button Command="{Binding OpenCommand}" Padding="0" MinHeight="44" BorderThickness="0" Background="Transparent" HorizontalAlignment="Stretch" HorizontalContentAlignment="Left" FontSize="14" FontWeight="SemiBold"><TextBlock Text="{Binding PrimaryText}" TextWrapping="Wrap"/></Button>
              <TextBlock Text="{Binding SecondaryText}" FontSize="13" Foreground="#796c63" TextWrapping="Wrap"/>
              <Grid ColumnSpacing="12"><Grid.ColumnDefinitions><ColumnDefinition Width="*"/><ColumnDefinition Width="*"/></Grid.ColumnDefinitions><TextBlock Text="{Binding Date}" FontSize="12" Foreground="#796c63"/><TextBlock Grid.Column="1" Text="{Binding Status}" FontSize="12" Foreground="{Binding StatusBrush}" HorizontalAlignment="Right" TextWrapping="Wrap"/></Grid>
              <Grid ColumnSpacing="12"><Grid.ColumnDefinitions><ColumnDefinition Width="*"/><ColumnDefinition Width="*"/></Grid.ColumnDefinitions><TextBlock Text="{Binding Amount}" FontSize="17" FontWeight="SemiBold" TextWrapping="Wrap"/><TextBlock Grid.Column="1" Text="{Binding Balance}" FontSize="13" TextWrapping="Wrap" HorizontalAlignment="Right"/></Grid>
              <StackPanel Orientation="Horizontal" Spacing="8"><Button Content="Edit" Command="{Binding EditCommand}" MinHeight="44" Padding="14,10"/><Button Content="PDF" Command="{Binding PdfCommand}" Visibility="{Binding PdfVisibility}" MinHeight="44" Padding="14,10"/></StackPanel>
            </StackPanel>
          </DataTemplate>
          """);
        list.ItemTemplate=compactTemplate;
        var actions = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 10 };
        var edit = AsyncButton("Edit selected", async () => { if (list.SelectedItem is RecordRow row) await EditRow(row.Source); }, Error); edit.IsEnabled = false;
        var pdf = AsyncButton("Document PDF", async () => { if (list.SelectedItem is RecordRow row) await PreviewDocument(row.Source); }, Error); pdf.IsEnabled = false;
        var convert = AsyncButton("Convert to invoice / bill", async () => { if (list.SelectedItem is RecordRow row) await EditDocument(row.Kind == "purchase_order" ? "purchase_bill" : "sales_invoice", null, row.Source); }, Error); convert.IsEnabled = false;
        bool Editable(RecordRow row)=>CanWrite&&(row.Kind is "party" or "item" or "payment_in" or "payment_out" or "bank_transfer"||FeatureCatalog.Documents.Contains(row.Kind))&&row.Source.Text("converted_to").Length==0&&!row.Source.Flag("cancelled");
        bool Printable(RecordRow row)=>FeatureCatalog.Documents.Contains(row.Kind)||row.Kind is "payment_in" or "payment_out" or "customer_refund" or "supplier_refund" or "advance_refund";
        list.SelectionChanged += (_, _) => { var row = list.SelectedItem as RecordRow; edit.IsEnabled = row is not null && Editable(row); pdf.IsEnabled = row is not null && Printable(row); convert.IsEnabled = row is not null && CanWrite && FeatureCatalog.Drafts.Contains(row.Kind) && row.Source.Text("converted_to").Length == 0; };
        list.ItemClick += async (_, args) => await Run(async () => { if (args.ClickedItem is RecordRow row) { if (row.Kind == "party") await PartyStatement(row.Source); else if (row.Kind=="item"&&Editable(row)) await EditRow(row.Source); } });
        list.DoubleTapped+=async(_,args)=>{for(var source=args.OriginalSource as DependencyObject;source is not null;source=Microsoft.UI.Xaml.Media.VisualTreeHelper.GetParent(source))if(source is Microsoft.UI.Xaml.Controls.Primitives.ButtonBase)return;await Run(async()=>{if(list.SelectedItem is RecordRow row&&row.Kind is not("party" or "item")){await TransactionDetails(row.Source);}});};
        actions.Children.Add(edit); if(rows.Any(Printable))actions.Children.Add(pdf);if(rows.Any(r=>FeatureCatalog.Drafts.Contains(r.Kind)))actions.Children.Add(convert);var selectedActions=actions.Children.Cast<UIElement>().ToArray();actions.Children.Clear();target.Children.Add(ResponsiveGrid(180,selectedActions));
        var headings=new Grid{ColumnSpacing=10,Padding=new Thickness(12,10,12,10),Background=Brush(0xFF, 0xF4, 0xE9)};foreach(var width in new[]{new GridLength(82),new GridLength(2,GridUnitType.Star),new GridLength(72),new GridLength(100),new GridLength(110),new GridLength(132)})headings.ColumnDefinitions.Add(new ColumnDefinition{Width=width});var master=rows.Select(r=>r.Kind).Distinct().Count()==1?rows[0].Kind:"";var labels=new[]{"DATE",master=="party"?"PARTY / GSTIN":master=="item"?"ITEM / HSN":"DOCUMENT / PARTY","STATUS",master=="party"?"PHONE":master=="item"?"SALE PRICE":"AMOUNT","BALANCE","ACTIONS"};for(var i=0;i<labels.Length;i++){var label=Text(labels[i],9,true);label.Foreground=Muted;if(i is 3 or 4)label.HorizontalAlignment=HorizontalAlignment.Right;Grid.SetColumn(label,i);headings.Children.Add(label);}headings.Visibility=Visibility.Collapsed;target.Children.Add(headings);target.Children.Add(list);
        void ArrangeRecords(){var wide=list.ActualWidth>=760;var template=wide?wideTemplate:compactTemplate;if(!ReferenceEquals(list.ItemTemplate,template))list.ItemTemplate=template;headings.Visibility=wide?Visibility.Visible:Visibility.Collapsed;}
        list.SizeChanged+=(_,_)=>ArrangeRecords();
    }

    internal Task NewEntry(string kind) => kind is "party" or "item" ? MasterForm(kind) : kind is "payment_in" or "payment_out" ? EditPayment(kind) : EditDocument(kind);
    internal async Task EditRow(JsonObject row)
    {
        var cid=CompanyId;var stamp=generation;var full = (await Api.Record(cid, row.Text("id"))).Object();if(stamp!=generation)return; var kind = full.Text("kind");
        if (kind is "party" or "item") await MasterForm(kind, full); else if (kind is "payment_in" or "payment_out") await EditPayment(kind, full);else if(kind=="bank_transfer")await Transfer(previous:full);else await EditDocument(kind, full);
    }
}
