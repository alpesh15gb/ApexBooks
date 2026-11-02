using ApexBooks_Windows.Services;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using System.Text.Json.Nodes;
using static ApexBooks_Windows.Views.NativeUi;

namespace ApexBooks_Windows.Views;

public sealed class DocumentLine
{
    public Border View { get; }
    public TextBox Description { get; }
    public TextBox Quantity { get; }
    public TextBox Rate { get; }
    public TextBlock Amount { get; } = Text("—",16,true);
    private readonly TextBox hsn, unit, mrp, discount, gst;
    private readonly ComboBox treatment, credit;
    private readonly CheckBox inclusive;
    private string itemId = "";
    public event Action? Changed;

    public DocumentLine(IEnumerable<JsonObject> masters, bool purchase, bool regular, JsonObject? initial = null, bool preserveImportedValues = false)
    {
        var data = initial ?? new(); var items = masters.ToList(); itemId = data.Text("item_id");
        var panel = Stack(12); var link = Text("", 12); link.Foreground = Muted;
        var selector = new AutoSuggestBox { Header = "Item / service", PlaceholderText = "Search item or enter description", QueryIcon = new SymbolIcon(Symbol.Find) };
        var current = items.FirstOrDefault(r => r.Text("id") == itemId); selector.Text = current is null?data.Text("description"):current.Text("name");
        Description = Input("Item / service description", data.Text("description"));Description.IsReadOnly=itemId.Length>0;
        Quantity = Input("Quantity", data.Text("quantity") is { Length: > 0 } q ? q : "1");
        Rate = Input("Rate (₹)", data.Text("rate")); hsn = Input("HSN / SAC", data.Text("hsn")); unit = Input("Unit", data.Text("unit"));
        mrp = Input("MRP · reference only", data.Text("mrp")); discount = Input("Discount (%)", data.Text("discount_percent") is { Length: > 0 } d ? d : "0");
        gst = Input("GST rate (%)", data.Text("gst_rate") is { Length: > 0 } g ? g : regular ? "18" : "0");
        treatment = Select("Supply classification", [("taxable", "Taxable"), ("nil_rated", "Nil rated"), ("exempt", "Exempt"), ("non_gst", "Non-GST")], data.Text("tax_treatment") is { Length: > 0 } tax ? tax : "taxable");
        credit = Select("Supplier GST treatment", [("pending_review", "Input credit pending review"), ("ineligible", "Ineligible · include GST in cost")], data.Text("itc_treatment") is { Length: > 0 } itc ? itc : "pending_review");
        inclusive = new CheckBox { Content = "Rate includes GST", IsChecked = data.Flag("price_includes_tax") };
        var amount=Stack(8);amount.Children.Add(Text("Amount",12));amount.Children.Add(Amount);Amount.Foreground=Green;
        var showTax=regular||purchase;
        var fields=showTax?new FrameworkElement[]{selector,Quantity,unit,Rate,discount,gst,amount}:new FrameworkElement[]{selector,Quantity,unit,Rate,discount,amount};
        var cells=new Grid{ColumnSpacing=12,RowSpacing=12};foreach(var field in fields)cells.Children.Add(field);
        bool? compactLayout=null;
        void ArrangeFields(double width)
        {
            var compact=width>0&&width<760;if(compactLayout==compact)return;compactLayout=compact;
            cells.ColumnDefinitions.Clear();cells.RowDefinitions.Clear();
            foreach(var field in fields){Grid.SetRow(field,0);Grid.SetColumnSpan(field,1);}
            if(compact)
            {
                for(var i=0;i<3;i++){cells.ColumnDefinitions.Add(new ColumnDefinition{Width=new GridLength(1,GridUnitType.Star)});cells.RowDefinitions.Add(new RowDefinition{Height=GridLength.Auto});}
                Grid.SetColumn(selector,0);Grid.SetColumnSpan(selector,3);
                var quantities=new FrameworkElement[]{Quantity,unit,Rate};for(var i=0;i<quantities.Length;i++){Grid.SetRow(quantities[i],1);Grid.SetColumn(quantities[i],i);}
                Grid.SetRow(discount,2);Grid.SetColumn(discount,0);
                if(showTax){Grid.SetRow(gst,2);Grid.SetColumn(gst,1);}else Grid.SetColumnSpan(discount,2);
                Grid.SetRow(amount,2);Grid.SetColumn(amount,2);
            }
            else
            {
                cells.RowDefinitions.Add(new RowDefinition{Height=GridLength.Auto});
                for(var i=0;i<fields.Length;i++){cells.ColumnDefinitions.Add(new ColumnDefinition{Width=new GridLength(i==0?3:1,GridUnitType.Star)});Grid.SetColumn(fields[i],i);}
            }
        }
        ArrangeFields(1000);cells.SizeChanged+=(_,args)=>ArrangeFields(args.NewSize.Width);
        panel.Children.Add(cells);panel.Children.Add(link);
        var details = Stack(12); details.Children.Add(Columns(hsn, mrp)); details.Children.Add(inclusive);
        if (regular || purchase) { details.Children.Add(treatment); if (regular && purchase) details.Children.Add(credit); }
        panel.Children.Add(new Expander { Header = "Tax, HSN and discount", Content = details, HorizontalContentAlignment = HorizontalAlignment.Stretch, HorizontalAlignment = HorizontalAlignment.Stretch });
        details.Children.Add(Button("Unlink product", () => { itemId = "";Description.IsReadOnly=false; link.Text = "Unlinked description · no stock movement"; Changed?.Invoke(); }));
        void LinkLabel() => link.Text = itemId.Length == 0 ? "Description entry · no product linked" : preserveImportedValues ? "Product linked · scanned rate and GST kept" : "Product selected";
        LinkLabel();
        selector.TextChanged += (_, args) => { if (args.Reason == AutoSuggestionBoxTextChangeReason.UserInput){itemId="";Description.IsReadOnly=false;Description.Text=selector.Text;LinkLabel();selector.ItemsSource = items.Where(r => r.Text("name").Contains(selector.Text, StringComparison.OrdinalIgnoreCase) || r["data"].Text("barcode") == selector.Text).Take(20).Select(r => r.Text("name")).ToArray();Changed?.Invoke();} };
        selector.SuggestionChosen += (_, args) =>
        {
            var chosen = items.FirstOrDefault(r => r.Text("name") == args.SelectedItem?.ToString()); if (chosen is null) return;
            itemId = chosen.Text("id"); Description.Text = chosen.Text("name");Description.IsReadOnly=true; var values = chosen["data"];
            if(!preserveImportedValues||values.Text("hsn").Length>0)hsn.Text = values.Text("hsn");if(!preserveImportedValues||values.Text("unit").Length>0)unit.Text = values.Text("unit");
            if(!preserveImportedValues){Rate.Text = values.Text(purchase ? "purchase_rate" : "sale_rate");gst.Text = regular || purchase ? values.Text("gst_rate") : "0";var classification=values.Text("tax_treatment");if(regular&&!purchase&&values.Number("gst_rate")==0&&classification is "" or "taxable")classification="nil_rated";SelectValue(treatment,classification.Length>0?classification:"taxable");} LinkLabel(); Changed?.Invoke();
        };
        foreach (var field in new[] { Description, Quantity, Rate, hsn, unit, mrp, discount, gst }) field.TextChanged += (_, _) => Changed?.Invoke();
        treatment.SelectionChanged += (_, _) => { if (Value(treatment) != "taxable") gst.Text = "0"; Changed?.Invoke(); };
        credit.SelectionChanged += (_, _) => Changed?.Invoke(); inclusive.Checked += (_, _) => Changed?.Invoke(); inclusive.Unchecked += (_, _) => Changed?.Invoke();
        View = Card(panel);View.Padding=new Thickness(14);
    }

    public JsonObject Data() => new()
    {
        ["description"] = Description.Text.Trim(), ["item_id"] = itemId, ["quantity"] = Quantity.Text.Trim(), ["rate"] = Rate.Text.Trim(),
        ["hsn"] = hsn.Text.Trim(), ["unit"] = unit.Text.Trim(), ["mrp"] = mrp.Text.Trim().Length == 0 ? "0" : mrp.Text.Trim(),
        ["discount_percent"] = discount.Text.Trim().Length == 0 ? "0" : discount.Text.Trim(), ["gst_rate"] = gst.Text.Trim().Length == 0 ? "0" : gst.Text.Trim(),
        ["price_includes_tax"] = inclusive.IsChecked == true, ["tax_treatment"] = Value(treatment), ["itc_treatment"] = Value(credit)
    };
}
