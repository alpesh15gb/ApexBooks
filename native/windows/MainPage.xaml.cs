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
    internal bool CanWrite => recordsReady && Company.Text("role") is ("owner" or "editor");
    internal bool IsOwner => Company.Text("role") == "owner";
    private NavigationView navigation = new();
    private readonly ContentControl host = new(){HorizontalContentAlignment=HorizontalAlignment.Stretch,VerticalContentAlignment=VerticalAlignment.Stretch};
    private readonly ComboBox companyPicker = new() { PlaceholderText = "Company", HorizontalAlignment = HorizontalAlignment.Stretch };
    internal readonly StackPanel Body = Stack(12);
    private Dictionary<string,decimal>? partyNet;private (decimal Receive,decimal Pay)? partyTotals;
    private readonly InfoBar notice = new() { IsClosable = true, Margin = new Thickness(24, 8, 24, 0) };
    private readonly ProgressBar progress = new() { IsIndeterminate = true, Height = 3, Visibility = Visibility.Collapsed };
    private bool changingCompanies, shellReady;
    private int generation, workspaceGeneration, companyLoads, refreshSequence;
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
        Api.SessionExpired += () => DispatcherQueue.TryEnqueue(()=>{if(!Api.SignedIn)ShowLogin();});
        Loaded += async (_, _) => { if (Api.RestoreSession()) await Run(LoadCompanies); else ShowLogin(); };
    }

    internal string PathFor(string suffix = "") => Api.CompanyPath(CompanyId, suffix);
    internal void Error(Exception e) {if(NativeUi.DialogError(e))return; notice.Severity = InfoBarSeverity.Error; notice.Message = e.Message; notice.IsOpen = true; }
    internal void Success(string message) { notice.Severity = InfoBarSeverity.Success; notice.Message = message; notice.IsOpen = true; }
    internal async Task Run(Func<Task> action)
    {
        progress.Visibility = Visibility.Visible;
        try { await action(); } catch (Exception e) { Error(e); } finally { progress.Visibility = Visibility.Collapsed; }
    }

    private void ShowLogin()
    {
        leavePage=null;hasUnsavedPage=null;hasPendingPage=null;posDrafts.Clear();CompanyId = ""; Company = new(); Records = new(); Banks = new();recordsReady=false; Companies = new(); generation++;workspaceGeneration++;companyLoads++;refreshSequence++;CurrentPage="dashboard"; Body.Children.Clear(); NativeUi.CloseDialog();
        var card = Stack(20); card.Width = 380;
        card.Children.Add(AppLogo(340));
        card.Children.Add(Text("Your business, in balance.", 18));
        card.Children.Add(Text("Sign in to your shared workspace. Documents and balances stay connected across devices."));
        var email = Input("Email address"); var password = new PasswordBox { Header = "Password", MinHeight = 42 };
        var remember = new CheckBox { Content = "Keep me signed in on this Windows account" };
        card.Children.Add(email); card.Children.Add(password); card.Children.Add(remember);
        card.Children.Add(AsyncButton("Sign in", async () => { await Api.Login(email.Text.Trim(), password.Password, remember.IsChecked == true); password.Password = ""; await LoadCompanies(); }, Error, true));
        card.Children.Add(AsyncButton("Create an account", Register, Error)); card.Children.Add(AsyncButton("Use a recovery code", Recover, Error));
        card.Children.Add(Text("Server · " + new Uri(Api.Origin).Host, 11));
        var outer = new ScrollViewer { Content = Card(card), HorizontalAlignment = HorizontalAlignment.Center, VerticalAlignment = VerticalAlignment.Center, Margin = new Thickness(24), MaxHeight = 800 };
        host.Content = outer;
    }

    private async Task Register()
    {
        var panel = Stack(); var email = Input("Email address"); var password = new PasswordBox { Header = "Password · at least 10 characters" }; var repeat = new PasswordBox { Header = "Confirm password" };
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
        navigation = new NavigationView { IsSettingsVisible = false, RequestedTheme = ElementTheme.Dark, PaneDisplayMode = NavigationViewPaneDisplayMode.Left, OpenPaneLength = 216, IsBackButtonVisible = NavigationViewBackButtonVisible.Collapsed };
        navigation.Resources["NavigationViewDefaultPaneBackground"] = Brush(0x18, 0x22, 0x34);
        navigation.Resources["NavigationViewExpandedPaneBackground"] = Brush(0x18, 0x22, 0x34);
        navigation.Resources["NavigationViewItemOnLeftMinHeight"]=36.0;navigation.Resources["NavigationViewSelectionIndicatorForeground"]=Brush(0x9F, 0xB5, 0xDB);
        var pane = Stack(8);pane.Margin=new Thickness(4,6,8,10);var brandRow=Stack(10);brandRow.Orientation=Orientation.Horizontal;brandRow.VerticalAlignment=VerticalAlignment.Center;
        brandRow.Children.Add(AppLogo(150));
        pane.Children.Add(brandRow);
        companyPicker.HorizontalAlignment=HorizontalAlignment.Stretch;companyPicker.MinHeight=34;companyPicker.Background=Brush(0x24, 0x31, 0x47);companyPicker.Foreground=Brush(255,255,255);companyPicker.BorderBrush=Brush(0x38, 0x45, 0x5B);pane.Children.Add(companyPicker);navigation.PaneHeader=pane;
        companyPicker.SelectionChanged += async (_, _) => { if (!changingCompanies) await Run(ChooseCompany); };
        foreach (var group in FeatureCatalog.Navigation.Where(f=>f.Key!="settings").GroupBy(f=>f.Group))
        {
            var expandable=group.Key is "Sales" or "Purchase" or "Purchases";
            var parent=expandable?new NavigationViewItem{Content=group.Key,Icon=new SymbolIcon(group.Key=="Sales"?Symbol.Document:Symbol.Shop)}:null;
            if(parent is not null)navigation.MenuItems.Add(parent);else navigation.MenuItems.Add(new NavigationViewItemHeader{Content=group.Key.ToUpperInvariant()});
            foreach(var feature in group){
            var symbol = feature.Key switch { "dashboard" => Symbol.Home, "party" => Symbol.People, "item" => Symbol.Shop, "reports" => Symbol.Document, "settings" => Symbol.Setting, "bank" => Symbol.World, "ledger" => Symbol.Library, "day_book" => Symbol.Calendar, _ => Symbol.Page };
            var item=new NavigationViewItem { Content = feature.Title, Tag = feature.Key, Icon = new SymbolIcon(symbol) };
            if(parent is not null)parent.MenuItems.Add(item);else navigation.MenuItems.Add(item);
            }
        }
        navigation.MenuItems.Add(new NavigationViewItem { Content="Settings",Tag="settings",Icon=new SymbolIcon(Symbol.Setting) });
        navigation.FooterMenuItems.Add(new NavigationViewItem { Content = "Add company", Tag = "new_company", Icon = new SymbolIcon(Symbol.Add) });
        navigation.FooterMenuItems.Add(new NavigationViewItem { Content = "Sign out", Tag = "logout", Icon = new SymbolIcon(Symbol.LeaveChat) });
        navigation.ItemInvoked += async (_, args) => await Run(async () =>
        {
            var key = (args.InvokedItemContainer as NavigationViewItem)?.Tag?.ToString();
            if (key == "logout") {if(posDrafts.Values.Any(d=>d.Submission.Unresolved)||hasPendingPage?.Invoke()==true){Error(new Exception("A held sale may already have posted. Return to its company’s Point of Sale and retry Complete sale to recover the original outcome before signing out."));return;}if(posDrafts.Count>0||hasUnsavedPage?.Invoke()==true){var prompt=Stack();prompt.Children.Add(Text("Held POS carts exist only in this session. Signing out discards them. Resolve any sale with an unknown save outcome before leaving."));if(!await Dialog("Discard held carts and sign out?",prompt,()=>Task.CompletedTask,"Sign out and discard"))return;}try{await Api.Logout();}finally{ShowLogin();}}
            else if (key == "new_company") await CompanyForm();
            else if (key is not null && CompanyId.Length > 0) await Navigate(key);
        });
        Body.Margin = new Thickness(20,12,20,20);Body.RequestedTheme=ElementTheme.Light;
        var content=new Grid{RequestedTheme=ElementTheme.Light,Background=Brush(0xF3, 0xF6, 0xF8)};content.RowDefinitions.Add(new RowDefinition{Height=GridLength.Auto});content.RowDefinitions.Add(new RowDefinition());content.Children.Add(BuildWorkspaceHeader());
        var scroll=new ScrollViewer {Content=Body,HorizontalScrollBarVisibility=ScrollBarVisibility.Disabled,VerticalScrollBarVisibility=ScrollBarVisibility.Auto};Grid.SetRow(scroll,1);content.Children.Add(scroll);navigation.AlwaysShowHeader=false;navigation.Content=content;host.Content=navigation;shellReady=true;
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
        var cid = CompanyId;if(cid.Length==0||!Api.SignedIn)return;var current=workspaceGeneration;var request=++refreshSequence; var rows = Api.Records(cid);var banks=Api.Send(Api.CompanyPath(cid,"/bank-accounts"));await Task.WhenAll(rows,banks); if (current != workspaceGeneration||request!=refreshSequence) return; Records = await rows;Banks=(await banks).Array();recordsReady=true; await Navigate(CurrentPage);
    }

    internal async Task Navigate(string page)
    {
        var leave=leavePage;leavePage=null;leave?.Invoke();hasUnsavedPage=null;hasPendingPage=null;
        ++generation;CurrentPage = page; Body.Children.Clear(); notice.IsOpen = false; workspaceCompany.Text = Company.Text("name");
        navigation.SelectedItem=FindNavigation(page);
        var heading=new StackPanel{Orientation=Orientation.Horizontal,Spacing=12,VerticalAlignment=VerticalAlignment.Bottom};
        heading.Children.Add(Text(page=="dashboard"?"Business overview":FeatureCatalog.Title(page), 22, true));
        var detail = Text(Company.Text("tax_mode") == "regular" ? "GST registered · " + Company.Text("gstin") : Company.Text("tax_mode") == "composition" ? "Composition company" : "Not GST registered", 12); detail.Foreground = Muted; detail.VerticalAlignment=VerticalAlignment.Bottom; detail.Margin=new Thickness(0,0,0,3); heading.Children.Add(detail);Body.Children.Add(heading);
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
        var party=Select("Customer / supplier",new[]{("all","All parties")}.Concat(Records.OfType<JsonObject>().Where(r=>r.Text("kind")==kind).Select(r=>r.Text("name")).Distinct().Order().Select(n=>(n,n))));var status=Select("Status",new[]{"All statuses","Unpaid","Part settled","Settled","Draft","Converted","Posted","Advance available","Advance settled","Credit available","Credit settled"}.Select(n=>(n,n)));var sort=Select("Sort",[("new","Newest first"),("old","Oldest first"),("name","Name A–Z"),("amount","Highest amount")]);
        toolbar.Children.Add(Button("Clear filters",()=>{search.Text="";SelectValue(period,"all");SelectValue(party,"all");SelectValue(status,"All statuses");SelectValue(sort,"new");}));
        if(!CanWrite)Body.Children.Add(Text("Read-only access · you can inspect records and export documents. Ask an owner for editor access to make changes.",12));
        if(!master){var filters=Stack();filters.Children.Add(Columns(period,party,status,sort));filters.Children.Add(Columns(from.View,to.View));Body.Children.Add(new Expander{Header="Filter documents",Content=filters,IsExpanded=false,HorizontalContentAlignment=HorizontalAlignment.Stretch,HorizontalAlignment=HorizontalAlignment.Stretch});}else Body.Children.Add(Columns(sort,masterStatus));
        var metrics=Stack();var holder=Stack();var caption=Text("",12);var pager=new StackPanel{Orientation=Orientation.Horizontal,Spacing=10};Button previous=null!,next=null!;Body.Children.Add(metrics);Body.Children.Add(holder);Body.Children.Add(pager);
        void Draw(bool reset=true){if(reset)page=0;holder.Children.Clear();metrics.Children.Clear();var range=Value(period);from.View.Visibility=to.View.Visibility=!master&&range=="custom"?Visibility.Visible:Visibility.Collapsed;var start=range=="fy"?J.FinancialStart:range=="month"?BusinessCalendar.Today.ToString("yyyy-MM-01"):range=="custom"?from.Value:"";var end=range is "month" or "fy"?J.Today:range=="custom"?to.Value:"";
            var source=Records.OfType<JsonObject>().Where(r=>r.Text("kind")==kind&&(!master||Value(masterStatus)=="all"||WorkflowMasterValues.IsActive(r)==(Value(masterStatus)=="active"))&&(r.Text("name")+" "+r.Text("number")+" "+r["data"].Text("phone")+" "+r["data"].Text("barcode")+" "+r["data"].Text("hsn")).Contains(search.Text,StringComparison.OrdinalIgnoreCase)&&(master||((start.Length==0||string.CompareOrdinal(r.Text("date"),start)>=0)&&(end.Length==0||string.CompareOrdinal(r.Text("date"),end)<=0)&&(Value(party)=="all"||r.Text("name")==Value(party))&&(Value(status)=="All statuses"||new RecordRow(r).Status==Value(status)))));
            source=Value(sort) switch{"old"=>source.OrderBy(r=>r.Text("date")).ThenBy(r=>r["data"].Text("created_at")).ThenBy(r=>r.Text("number")),"name"=>source.OrderBy(r=>r.Text("name"),StringComparer.OrdinalIgnoreCase),"amount"=>source.OrderByDescending(r=>r.Number("amount")),_=>source.OrderByDescending(r=>r.Text("date")).ThenByDescending(r=>r["data"].Text("created_at")).ThenByDescending(r=>r.Text("number"))};var all=source.ToArray();page=Math.Clamp(page,0,Math.Max(0,(all.Length-1)/size));
            if(kind=="party"&&partyTotals is {} owed)AddMetrics(metrics,("You'll get",owed.Receive),("You'll pay",owed.Pay));
            if(master)metrics.Children.Add(Text($"{all.Length} {FeatureCatalog.Title(kind).ToLowerInvariant()}"+(kind=="party"?" · click a party for transactions and balances":""),14,true));else if(kind is "sales_invoice" or "purchase_bill")AddMetrics(metrics,("Posted value",all.Sum(r=>r.Number("amount"))),("Outstanding",all.Sum(r=>r.Number("outstanding"))),("Unpaid documents",all.Count(r=>r.Number("outstanding")>0)),("Settled documents",all.Count(r=>r.Flag("posted")&&r.Number("outstanding")<=0)));else AddMetrics(metrics,("Documents",all.Length),("Total value",all.Sum(r=>r.Number("amount"))));
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
        var list = new ListView { ItemsSource = rows, SelectionMode = ListViewSelectionMode.Single, MaxHeight = 650, IsItemClickEnabled = true, CornerRadius=new CornerRadius(14), BorderBrush=Brush(0xDF, 0xE3, 0xEB),BorderThickness=new Thickness(1), Background = new Microsoft.UI.Xaml.Media.SolidColorBrush(Microsoft.UI.Colors.White) };
        list.ItemContainerStyle=new Style(typeof(ListViewItem)){Setters={new Setter(Control.HorizontalContentAlignmentProperty,HorizontalAlignment.Stretch),new Setter(Control.PaddingProperty,new Thickness(0)),new Setter(FrameworkElement.MarginProperty,new Thickness(0))}};
        list.ItemTemplate = (DataTemplate)XamlReader.Load("""
          <DataTemplate xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"><Grid Padding="12,6" ColumnSpacing="10"><Grid.ColumnDefinitions><ColumnDefinition Width="82"/><ColumnDefinition Width="2*"/><ColumnDefinition Width="72"/><ColumnDefinition Width="100"/><ColumnDefinition Width="110"/><ColumnDefinition Width="132"/></Grid.ColumnDefinitions><TextBlock Text="{Binding Date}" FontSize="12" VerticalAlignment="Center"/><StackPanel Grid.Column="1"><Button Command="{Binding OpenCommand}" Padding="0" BorderThickness="0" Background="Transparent" HorizontalAlignment="Stretch" HorizontalContentAlignment="Left" FontSize="12" FontWeight="SemiBold" ToolTipService.ToolTip="{Binding PrimaryText}"><TextBlock Text="{Binding PrimaryText}" TextTrimming="CharacterEllipsis"/></Button><TextBlock Text="{Binding SecondaryText}" FontSize="11" Foreground="#697D8B" TextTrimming="CharacterEllipsis"/></StackPanel><TextBlock Grid.Column="2" Text="{Binding Status}" FontSize="11" VerticalAlignment="Center" Foreground="{Binding StatusBrush}"/><TextBlock Grid.Column="3" Text="{Binding Amount}" FontWeight="SemiBold" HorizontalAlignment="Right" VerticalAlignment="Center"/><TextBlock Grid.Column="4" Text="{Binding BalanceValue}" FontSize="12" HorizontalAlignment="Right" VerticalAlignment="Center"/><StackPanel Grid.Column="5" Orientation="Horizontal" Spacing="6" VerticalAlignment="Center"><Button Content="Edit" Command="{Binding EditCommand}" FontSize="12" Padding="10,6" CornerRadius="8"/><Button Content="PDF" Command="{Binding PdfCommand}" Visibility="{Binding PdfVisibility}" FontSize="12" Padding="10,6" CornerRadius="8"/></StackPanel></Grid></DataTemplate>
          """);
        var actions = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 10 };
        var edit = AsyncButton("Edit selected", async () => { if (list.SelectedItem is RecordRow row) await EditRow(row.Source); }, Error); edit.IsEnabled = false;
        var pdf = AsyncButton("Document PDF", async () => { if (list.SelectedItem is RecordRow row) await PreviewDocument(row.Source); }, Error); pdf.IsEnabled = false;
        var convert = AsyncButton("Convert to invoice / bill", async () => { if (list.SelectedItem is RecordRow row) await EditDocument(row.Kind == "purchase_order" ? "purchase_bill" : "sales_invoice", null, row.Source); }, Error); convert.IsEnabled = false;
        bool Editable(RecordRow row)=>CanWrite&&(row.Kind is "party" or "item" or "payment_in" or "payment_out" or "bank_transfer"||FeatureCatalog.Documents.Contains(row.Kind))&&row.Source.Text("converted_to").Length==0&&!row.Source.Flag("cancelled");
        bool Printable(RecordRow row)=>FeatureCatalog.Documents.Contains(row.Kind)||row.Kind is "payment_in" or "payment_out" or "customer_refund" or "supplier_refund" or "advance_refund";
        list.SelectionChanged += (_, _) => { var row = list.SelectedItem as RecordRow; edit.IsEnabled = row is not null && Editable(row); pdf.IsEnabled = row is not null && Printable(row); convert.IsEnabled = row is not null && CanWrite && FeatureCatalog.Drafts.Contains(row.Kind) && row.Source.Text("converted_to").Length == 0; };
        list.ItemClick += async (_, args) => await Run(async () => { if (args.ClickedItem is RecordRow row) { if (row.Kind == "party") await PartyStatement(row.Source); else if (row.Kind=="item"&&Editable(row)) await EditRow(row.Source); } });
        list.DoubleTapped+=async(_,args)=>{for(var source=args.OriginalSource as DependencyObject;source is not null;source=Microsoft.UI.Xaml.Media.VisualTreeHelper.GetParent(source))if(source is Microsoft.UI.Xaml.Controls.Primitives.ButtonBase)return;await Run(async()=>{if(list.SelectedItem is RecordRow row&&row.Kind is not("party" or "item")){await TransactionDetails(row.Source);}});};
        actions.Children.Add(edit); if(rows.Any(Printable))actions.Children.Add(pdf);if(rows.Any(r=>FeatureCatalog.Drafts.Contains(r.Kind)))actions.Children.Add(convert);target.Children.Add(actions);
        var headings=new Grid{ColumnSpacing=10,Padding=new Thickness(12,10,12,10),Background=Brush(0xF0, 0xF3, 0xF7)};foreach(var width in new[]{new GridLength(82),new GridLength(2,GridUnitType.Star),new GridLength(72),new GridLength(100),new GridLength(110),new GridLength(132)})headings.ColumnDefinitions.Add(new ColumnDefinition{Width=width});var master=rows.Select(r=>r.Kind).Distinct().Count()==1?rows[0].Kind:"";var labels=new[]{"DATE",master=="party"?"PARTY / GSTIN":master=="item"?"ITEM / HSN":"DOCUMENT / PARTY","STATUS",master=="party"?"PHONE":master=="item"?"SALE PRICE":"AMOUNT","BALANCE","ACTIONS"};for(var i=0;i<labels.Length;i++){var label=Text(labels[i],9,true);label.Foreground=Muted;if(i is 3 or 4)label.HorizontalAlignment=HorizontalAlignment.Right;Grid.SetColumn(label,i);headings.Children.Add(label);}target.Children.Add(headings);target.Children.Add(list);
    }

    internal Task NewEntry(string kind) => kind is "party" or "item" ? MasterForm(kind) : kind is "payment_in" or "payment_out" ? EditPayment(kind) : EditDocument(kind);
    internal async Task EditRow(JsonObject row)
    {
        var cid=CompanyId;var stamp=generation;var full = (await Api.Record(cid, row.Text("id"))).Object();if(stamp!=generation)return; var kind = full.Text("kind");
        if (kind is "party" or "item") await MasterForm(kind, full); else if (kind is "payment_in" or "payment_out") await EditPayment(kind, full);else if(kind=="bank_transfer")await Transfer(previous:full);else await EditDocument(kind, full);
    }
}
