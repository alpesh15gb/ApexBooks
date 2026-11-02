using Microsoft.UI;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using System.Text.Json.Nodes;
using ApexBooks_Windows.Services;

namespace ApexBooks_Windows.Views;

public static class NativeUi
{
    public static void SetFormEnabled(Panel panel,bool enabled)
    {
        foreach(var child in panel.Children)
        {
            if(child is Control control)control.IsEnabled=enabled;
            else if(child is Panel nested)SetFormEnabled(nested,enabled);
        }
    }

    private sealed class DialogContext(ContentDialog dialog, InfoBar error, Func<bool>? canSave = null)
    {
        public ContentDialog Dialog { get; } = dialog;
        public InfoBar Error { get; } = error;
        public Func<bool>? CanSave { get; } = canSave;
        public int Operations;
        public bool Saving, ForcedClose;
        public Button? SaveButton, NewButton;
        public void Update()
        {
            var ready = !Saving && Operations == 0;
            Dialog.IsPrimaryButtonEnabled = ready && (CanSave?.Invoke() ?? true);
            Dialog.IsSecondaryButtonEnabled = ready && (CanSave?.Invoke() ?? true);
            if(SaveButton is not null)SaveButton.IsEnabled=ready&&(CanSave?.Invoke()??true);
            if(NewButton is not null)NewButton.IsEnabled=ready&&(CanSave?.Invoke()??true);
            if (Dialog.Content is Control content) content.IsEnabled = ready;
        }
    }
    private static DialogContext? active;
    public static void RefreshDialogActions(bool clearError = false) { if (active is not null) { if (clearError) active.Error.IsOpen = false; active.Update(); } }
    public static bool DialogError(Exception e){if(active is null)return false;active.Error.Message=e.Message;active.Error.IsOpen=true;return true;}
    public static void CloseDialog(){var current=active;active=null;if(current is not null){current.ForcedClose=true;current.Dialog.Hide();}}
    public static readonly SolidColorBrush Green = Brush(0x12, 0x7C, 0x66);
    public static readonly SolidColorBrush Muted = Brush(0x69, 0x7D, 0x8B);
    public static readonly FontFamily WorkspaceFont = new("ms-appx:///Assets/Fonts/DMSans.ttf#DM Sans");
    public static Border AppLogo(double width) => new() { Width=width, Padding=new Thickness(10), CornerRadius=new CornerRadius(7), Background=Brush(255,255,255), Child=new Image{ Width=width-20, Height=(width-20)*230/1569, Stretch=Stretch.Uniform, Source=new Microsoft.UI.Xaml.Media.Imaging.BitmapImage(new Uri("ms-appx:///Assets/ApexBooksWordmark.png")) } };
    public static SolidColorBrush Brush(byte r, byte g, byte b) => new(Windows.UI.Color.FromArgb(255, r, g, b));
    public static TextBlock Text(string text, double size = 13, bool bold = false) => new() { Text = text, FontFamily=WorkspaceFont,Foreground=Brush(0x19,0x2F,0x3B),FontSize = size, FontWeight = bold ? Microsoft.UI.Text.FontWeights.SemiBold : Microsoft.UI.Text.FontWeights.Normal, TextWrapping = TextWrapping.Wrap };
    public static StackPanel SectionHeading(string number,string title,string detail=""){
        var row=Stack(12);row.Orientation=Orientation.Horizontal;row.VerticalAlignment=VerticalAlignment.Center;
        row.Children.Add(new Border{Width=30,Height=30,CornerRadius=new CornerRadius(8),Background=Brush(0xED,0xF7,0xF1),BorderBrush=Brush(0xD6,0xE8,0xE0),BorderThickness=new Thickness(1),Child=new TextBlock{Text=number,FontFamily=WorkspaceFont,FontSize=11,FontWeight=Microsoft.UI.Text.FontWeights.SemiBold,Foreground=Green,HorizontalAlignment=HorizontalAlignment.Center,VerticalAlignment=VerticalAlignment.Center}});
        var labels=Stack(3);labels.Children.Add(Text(title,14,true));if(detail.Length>0){var caption=Text(detail,11);caption.Foreground=Muted;labels.Children.Add(caption);}row.Children.Add(labels);return row;
    }
    public static StackPanel Stack(double spacing = 12) => new() { Spacing = spacing };
    public static Button Button(string label, Action click, bool primary = false)
    {
        var button = new Button { Content = label, MinHeight = 40, CornerRadius = new CornerRadius(8), Padding = new Thickness(16, 8, 16, 8) };
        if (primary) button.Style = (Style)Application.Current.Resources["AccentButtonStyle"];
        button.Click += (_, _) => click(); return button;
    }
    public static Button AsyncButton(string label, Func<Task> click, Action<Exception> error, bool primary = false)
    {
        var button = Button(label, () => { }, primary);
        Microsoft.UI.Xaml.Automation.AutomationProperties.SetName(button,label);
        button.Click += async (_, _) =>
        {
            var context = active;
            button.IsEnabled = false;
            var progress=Stack(8);progress.Orientation=Orientation.Horizontal;
            progress.Children.Add(new ProgressRing{IsActive=true,Width=16,Height=16,VerticalAlignment=VerticalAlignment.Center});progress.Children.Add(Text(label));button.Content=progress;
            if (context is not null) { context.Error.IsOpen = false; context.Operations++; context.Update(); }
            try { await click(); }
            catch (Exception e) { error(e); }
            finally
            {
                if (context is not null) { context.Operations--; context.Update(); }
                button.IsEnabled = true;
                button.Content=label;
            }
        };
        return button;
    }
    public static Border Card(UIElement child) => new() { Child = child, Background = new SolidColorBrush(Colors.White), BorderBrush = Brush(0xDF, 0xE7, 0xEB), BorderThickness = new Thickness(1), CornerRadius = new CornerRadius(12), Padding = new Thickness(18) };
    public static TextBox Input(string label, string value = "", bool multi = false) => new() { Header = label, Text = value, FontFamily=WorkspaceFont,FontSize=13,MinHeight = 40, AcceptsReturn = multi, TextWrapping = multi ? TextWrapping.Wrap : TextWrapping.NoWrap, MaxLength = multi ? 2000 : 500 };
    public sealed class DateInput
    {
        public StackPanel View { get; } = Stack(6);
        public CalendarDatePicker Picker { get; } = new() { HorizontalAlignment = HorizontalAlignment.Stretch, MinHeight = 38, PlaceholderText = "YYYY-MM-DD · choose date", DateFormat="{year.full}-{month.integer(2)}-{day.integer(2)}", CalendarIdentifier=Windows.Globalization.CalendarIdentifiers.Gregorian };
        public string Value => Picker.Date?.ToString("yyyy-MM-dd", System.Globalization.CultureInfo.InvariantCulture) ?? "";
        public DateInput(string label, string value = "")
        {
            View.Children.Add(Text(label+" · YYYY-MM-DD", 13)); View.Children.Add(Picker);ToolTipService.SetToolTip(Picker,"Gregorian business date · year-month-day (YYYY-MM-DD). Choose from the calendar; dates are not interpreted as month/day text.");Microsoft.UI.Xaml.Automation.AutomationProperties.SetName(Picker,label+" · YYYY-MM-DD");
            if (DateTime.TryParseExact(value, "yyyy-MM-dd", System.Globalization.CultureInfo.InvariantCulture, System.Globalization.DateTimeStyles.None, out var date)) Picker.Date = new DateTimeOffset(date);
        }
    }
    public static ComboBox Select(string label, IEnumerable<(string Key, string Label)> choices, string selected = "")
    {
        var box = new ComboBox { Header = label, HorizontalAlignment = HorizontalAlignment.Stretch, MinHeight = 38 };
        foreach (var (key, text) in choices) { var item = new ComboBoxItem { Content = text, Tag = key }; box.Items.Add(item); if (key == selected) box.SelectedItem = item; }
        if (box.SelectedIndex < 0 && box.Items.Count > 0) box.SelectedIndex = 0;
        return box;
    }
    public static string Value(ComboBox box) => (box.SelectedItem as ComboBoxItem)?.Tag?.ToString() ?? "";
    public static void SelectValue(ComboBox box, string value) { foreach (ComboBoxItem item in box.Items) if (item.Tag?.ToString() == value) { box.SelectedItem = item; break; } }
    public static Grid Columns(params UIElement[] elements)
    {
        var grid = new Grid { ColumnSpacing = 16, RowSpacing = 16 };
        for (var i = 0; i < elements.Length; i++) { grid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) }); Grid.SetColumn((FrameworkElement)elements[i], i); grid.Children.Add(elements[i]); }
        return grid;
    }
    public static async Task<bool> Dialog(string title, UIElement content, Func<Task> save, string action = "Save", Func<bool>? canSave = null, Func<bool>? hasChanges = null, Func<Task>? saveAndNew = null, UIElement? stickyFooter = null, Func<bool>? unresolved = null)
    {
        var heading = Stack(); heading.Children.Add(Text(title,20,true));
        var error = new InfoBar { Severity = InfoBarSeverity.Error, IsClosable = true }; heading.Children.Add(error);
        var rootHeight = (App.Window.Content as FrameworkElement)?.ActualHeight ?? 900;
        var rootWidth = (App.Window.Content as FrameworkElement)?.ActualWidth ?? 1280;
        var workbench=stickyFooter is not null;
        var dialogWidth=Math.Max(320,Math.Min(workbench?1440:1050,rootWidth-64));
        var bodyWidth=Math.Max(260,dialogWidth-48);
        if(content is FrameworkElement surface){surface.MinWidth=Math.Min(surface.MinWidth,bodyWidth);surface.MaxWidth=bodyWidth;}
        var layout = new Grid { RowSpacing = 14, MaxWidth=bodyWidth };
        layout.RowDefinitions.Add(new RowDefinition { Height = new GridLength(1, GridUnitType.Star) });
        layout.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
        var bodyScroll=new ScrollViewer { Content = content, MaxWidth=bodyWidth, MaxHeight = Math.Max(180, Math.Min(760, rootHeight - (workbench ? 210 : 260))), VerticalScrollBarVisibility = ScrollBarVisibility.Auto, HorizontalScrollBarVisibility = ScrollBarVisibility.Disabled, HorizontalScrollMode=ScrollMode.Disabled };
        layout.Children.Add(bodyScroll);
        var dialog = new ContentDialog { Title = heading, Content = new ContentControl { Content = layout, HorizontalContentAlignment = HorizontalAlignment.Stretch }, PrimaryButtonText = workbench?"":action, SecondaryButtonText = workbench||saveAndNew is null ? "" : "Save & new", CloseButtonText = workbench||action=="Done"?"":"Cancel", DefaultButton = workbench?ContentDialogButton.None:ContentDialogButton.Primary, XamlRoot = App.Window.Content.XamlRoot };
        Microsoft.UI.Xaml.Automation.AutomationProperties.SetName(dialog,title);
        var done = false;var context=new DialogContext(dialog,error,canSave);context.Update();
        var discard = Stack(8); discard.Visibility = Visibility.Collapsed;
        discard.Children.Add(Text("Discard unsaved changes?", 16, true));
        discard.Children.Add(Text("Your draft has not been saved. Keep editing or discard this draft.", 13));
        var discardActions = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 10 };
        discardActions.Children.Add(Button("Keep editing", () => discard.Visibility = Visibility.Collapsed, true));
        discardActions.Children.Add(Button("Discard draft", () => { context.ForcedClose = true; dialog.Hide(); }));
        discard.Children.Add(discardActions); heading.Children.Add(discard);
        void ResizeBody(){if(workbench)bodyScroll.MaxHeight=Math.Max(140,Math.Min(760,rootHeight-210-error.ActualHeight-discard.ActualHeight));}
        error.SizeChanged+=(_,_)=>ResizeBody();discard.SizeChanged+=(_,_)=>ResizeBody();
        dialog.Closing+=(_,args)=>{
            if(context.ForcedClose)return;
            if(context.Saving||context.Operations>0){args.Cancel=true;return;}
            if(!done && unresolved?.Invoke()==true){args.Cancel=true;discard.Visibility=Visibility.Collapsed;error.Message="The previous save may already have posted. Retry the original save to recover its outcome before closing; do not create a replacement entry.";error.IsOpen=true;return;}
            if(!done && hasChanges?.Invoke()==true){args.Cancel=true;discard.Visibility=Visibility.Visible;}
        };
        async Task<bool> Commit(bool again,bool close=false)
        {
            if(context.Saving||context.Operations>0||!(context.CanSave?.Invoke()??true))return false;
            error.IsOpen=false;context.Saving=true;context.Update();var success=false;
            try{await (again&&saveAndNew is not null?saveAndNew():save());done=true;success=true;}
            catch(Exception e){error.Message=e.Message;error.IsOpen=true;}
            finally{context.Saving=false;context.Update();}
            if(success&&close){context.ForcedClose=true;dialog.Hide();}return success;
        }
        dialog.PrimaryButtonClick += async (_, args)=>{args.Cancel=true;var deferral=args.GetDeferral();try{args.Cancel=!await Commit(false);}finally{deferral.Complete();}};
        if(saveAndNew is not null) dialog.SecondaryButtonClick += async (_, args) =>
        {
            args.Cancel=true;var deferral=args.GetDeferral();try{args.Cancel=!await Commit(true);}finally{deferral.Complete();}
        };
        if(stickyFooter is not null){
            var footer=new Grid{ColumnSpacing=18,Padding=new Thickness(0,14,0,0),BorderBrush=Brush(0xDF,0xE7,0xEB),BorderThickness=new Thickness(0,1,0,0)};
            footer.ColumnDefinitions.Add(new ColumnDefinition{Width=new GridLength(1,GridUnitType.Star)});footer.ColumnDefinitions.Add(new ColumnDefinition{Width=GridLength.Auto});
            if(stickyFooter is Border summary){summary.Padding=new Thickness(0);summary.BorderThickness=new Thickness(0);summary.CornerRadius=new CornerRadius(0);}
            footer.Children.Add(stickyFooter);var actions=new StackPanel{Orientation=Orientation.Horizontal,Spacing=10,VerticalAlignment=VerticalAlignment.Center};
            actions.Children.Add(Button("Cancel",()=>dialog.Hide()));
            if(saveAndNew is not null){var next=Button("Save & new",()=>{});next.Click+=async(_,_)=>await Commit(true,true);context.NewButton=next;actions.Children.Add(next);}
            var primary=Button(action,()=>{},true);primary.Click+=async(_,_)=>await Commit(false,true);context.SaveButton=primary;actions.Children.Add(primary);Grid.SetColumn(actions,1);footer.Children.Add(actions);Grid.SetRow(footer,1);layout.Children.Add(footer);context.Update();
            var accelerator = new Microsoft.UI.Xaml.Input.KeyboardAccelerator { Key=Windows.System.VirtualKey.Enter, Modifiers=Windows.System.VirtualKeyModifiers.Control };
            accelerator.Invoked += async (_, args) => {
                args.Handled=true;await Commit(false,true);
            };
            dialog.KeyboardAccelerators.Add(accelerator);
        }
        // Bound the template and body, not the overlay: a MaxWidth on ContentDialog
        // also narrows its centering surface and shifts small dialogs to the left.
        dialog.Resources["ContentDialogMaxWidth"]=dialogWidth;active=context;try{await dialog.ShowAsync();}finally{if(ReferenceEquals(active,context))active=null;}return done;
    }
    public static void AddMetrics(Panel target, params (string Label, decimal Value)[] values)
    {
        var grid = new Grid { ColumnSpacing = 14, RowSpacing = 14, Margin = new Thickness(0, 0, 0, 12) };
        for (var col = 0; col < Math.Min(4, values.Length); col++) grid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
        for (var i = 0; i < values.Length; i++)
        {
            var columnCount = Math.Min(4, values.Length); var row = i / columnCount;
            if (grid.RowDefinitions.Count <= row) grid.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
            var stack = Stack(10); var label = Text(values[i].Label, 11, true); label.Foreground = Muted; stack.Children.Add(label); var amount = Text(values[i].Label is "Documents" or "Records" or "Items"||values[i].Label.EndsWith("documents",StringComparison.OrdinalIgnoreCase) ? values[i].Value.ToString("N0") : J.Money(values[i].Value), 25, true); amount.Foreground = Green; stack.Children.Add(amount); var card = Card(stack); Grid.SetColumn(card, i % columnCount); Grid.SetRow(card, row); grid.Children.Add(card);
        }
        target.Children.Add(grid);
    }
    private static readonly HashSet<string> Acronyms = new(StringComparer.OrdinalIgnoreCase) { "gst", "gstin", "cgst", "sgst", "igst", "hsn", "sac", "ifsc", "upi", "mrp", "pos", "pdf", "xlsx", "itc", "gstr1", "gstr2a", "gstr3b", "b2b", "b2c", "b2cs", "b2cl", "id" };
    public static string Friendly(string text) => string.Join(" ", text.Split('_', StringSplitOptions.RemoveEmptyEntries).Select(w => Acronyms.Contains(w) ? w.ToUpperInvariant() : w.Length > 0 ? char.ToUpperInvariant(w[0]) + w[1..] : w));
    public static string Display(string key, JsonNode? node)
    {
        if (node is null) return "—";
        if(key is "kind" or "tax_mode" or "payment_account" or "payment_method" or "status" or "direction" or "category")return Friendly(node.ToString());
        if(node is JsonValue boolean && boolean.TryGetValue<bool>(out var truth))return truth?"Yes":"No";
        if (node is JsonObject || node is JsonArray) return "";
        if(key.Contains("gst_rate")||key.Contains("tax_rate")||key.Contains("percent"))return node+"%";
        var money = !new[]{"quantity","count","records","items"}.Any(key.Contains)&&(new[] { "amount", "total", "taxable", "cgst", "sgst", "igst", "value", "balance", "receivable", "payable", "profit", "income", "expense", "debit", "credit", "cost", "available", "paid", "outstanding", "difference" }.Any(key.Contains)||new[]{"sales","purchases","receipts","payments","movement"}.Contains(key)||key.EndsWith("_movement"));
        return money && decimal.TryParse(node.ToString(), System.Globalization.NumberStyles.Any, System.Globalization.CultureInfo.InvariantCulture, out var value) ? J.Money(value) : node.ToString();
    }
    public static void Table(Panel target, JsonArray rows, string title = "", IEnumerable<string>? columns = null)
    {
        if (title.Length > 0) target.Children.Add(Text(title, 20, true));
        if (rows.Count == 0) { target.Children.Add(Card(Text("No entries in this view."))); return; }
        var keys = (columns ?? rows.OfType<JsonObject>().SelectMany(r => r.Select(p => p.Key)).Distinct().Where(k => k != "id" && !k.EndsWith("_id") && rows.Any(r => r?[k] is JsonValue))).ToArray();
        if (keys.Length == 0) return;
        var table = Stack(0); var header = new Grid { ColumnSpacing = 14, Padding = new Thickness(12), Background = Brush(0xF0, 0xF5, 0xF1) };
        foreach (var key in keys) header.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(key is "name" or "party" or "description" or "section" ? 230 : 145) });
        for (var i = 0; i < keys.Length; i++) { var text = Text(Friendly(keys[i]), 12, true); Grid.SetColumn(text, i); header.Children.Add(text); }
        var page=0;const int pageSize=50;var objects=rows.OfType<JsonObject>().ToArray();
        var scroller=new ScrollViewer { Content = table, HorizontalScrollBarVisibility = ScrollBarVisibility.Auto, VerticalScrollBarVisibility = ScrollBarVisibility.Auto, MaxHeight = 550 };
        var status=Text("",12);
        Button previous=null!,next=null!;
        previous=Button("Previous",()=>{page--;Render();});
        next=Button("Next",()=>{page++;Render();});
        void Render()
        {
            table.Children.Clear();table.Children.Add(header);
            foreach (var row in objects.Skip(page*pageSize).Take(pageSize))
            {
            var grid = new Grid { ColumnSpacing = 14, Padding = new Thickness(12), BorderBrush = Brush(0xEC, 0xF0, 0xEC), BorderThickness = new Thickness(0, 0, 0, 1) };
            foreach (var definition in header.ColumnDefinitions) grid.ColumnDefinitions.Add(new ColumnDefinition { Width = definition.Width });
            for (var i = 0; i < keys.Length; i++) { var text = Text(Display(keys[i], row[keys[i]]), 13); Grid.SetColumn(text, i); grid.Children.Add(text); }
            table.Children.Add(grid);
            }
            status.Text=$"{page*pageSize+1}–{Math.Min((page+1)*pageSize,objects.Length)} of {objects.Length}";
            previous.IsEnabled=page>0;next.IsEnabled=(page+1)*pageSize<objects.Length;
            scroller.ChangeView(null,0,null);
        }
        Render();target.Children.Add(scroller);
        if(objects.Length>pageSize){var pager=new StackPanel{Orientation=Orientation.Horizontal,Spacing=16,VerticalAlignment=VerticalAlignment.Center};pager.Children.Add(previous);pager.Children.Add(status);pager.Children.Add(next);target.Children.Add(pager);}
    }
}
