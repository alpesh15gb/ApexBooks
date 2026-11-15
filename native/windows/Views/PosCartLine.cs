using ApexBooks_Windows.Services;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Controls;
using System.Globalization;
using System.Text.Json.Nodes;
using static ApexBooks_Windows.Views.NativeUi;

namespace ApexBooks_Windows.Views;

internal sealed class PosCartLine
{
    private readonly JsonObject source;
    private readonly TextBox quantity, rate, discount, gst;
    private readonly ComboBox discountMode, taxTreatment;
    private readonly CheckBox inclusive;
    private readonly LineDiscountState discountState;
    private readonly TextBlock total;

    internal Border View { get; }
    internal string ItemId => source.Text("item_id");
    internal decimal Quantity => decimal.TryParse(quantity.Text, NumberStyles.Number, CultureInfo.InvariantCulture, out var amount) ? amount : 0;
    internal bool Ready => Quantity > 0 && rate.Text.Trim().Length > 0;
    internal event Action? Changed;

    internal PosCartLine(JsonObject line, bool regular, Action<PosCartLine> remove)
    {
        source = line.DeepClone().AsObject();
        var name = source.Text("description");
        quantity = Input("", source.Text("quantity"));
        quantity.TextAlignment = TextAlignment.Center;
        quantity.MinWidth = 60;
        quantity.MaxLength = 16;
        AutomationProperties.SetName(quantity, $"Quantity for {name}");
        rate = Input("Unit price (₹)", source.Text("rate"));
        rate.MaxLength = 16;
        discountState = new LineDiscountState(source);
        discount = Input("Discount", discountState.Value);
        discount.MaxLength = 16;
        discountMode = Select("Discount type", [("percent", "Percentage"), ("amount", "Fixed amount (₹)")], discountState.Mode);
        gst = Input("GST rate (%)", source.Text("gst_rate"));
        gst.MaxLength = 8;
        inclusive = new CheckBox { Content = "Price includes GST", IsChecked = source.Flag("price_includes_tax") };
        taxTreatment = Select("GST classification",
            [("taxable", "Taxable"), ("nil_rated", "Nil rated"), ("exempt", "Exempt"), ("non_gst", "Non-GST")],
            source.Text("tax_treatment"));

        var description = Text(name, 15, true);
        description.MaxLines = 2;
        description.TextTrimming = TextTrimming.CharacterEllipsis;
        total = Text("—", 16, true);
        total.Foreground = Green;
        total.HorizontalAlignment = HorizontalAlignment.Right;
        total.VerticalAlignment = VerticalAlignment.Center;

        var decrease = StepButton("−", $"Decrease quantity of {name}", () =>
        {
            if (Quantity > 1) SetQuantity(Quantity - 1);
            else remove(this);
        });
        var increase = StepButton("+", $"Increase quantity of {name}", () => SetQuantity(Math.Max(Quantity, 0) + 1));
        var quantityControl = new Grid { ColumnSpacing = 4, HorizontalAlignment = HorizontalAlignment.Left };
        quantityControl.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
        quantityControl.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(64) });
        quantityControl.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
        quantityControl.Children.Add(decrease);
        Grid.SetColumn(quantity, 1);
        quantityControl.Children.Add(quantity);
        Grid.SetColumn(increase, 2);
        quantityControl.Children.Add(increase);
        // Same label size and gap as the adjacent TextBox headers so both controls share one top edge.
        var quantityContents = Stack(4);
        var quantityLabel = Text(source.Text("unit") is { Length: > 0 } unit ? $"Quantity · {unit}" : "Quantity", 14);
        quantityContents.Children.Add(quantityLabel);
        quantityContents.Children.Add(quantityControl);

        var details = Stack(10);
        details.Children.Add(ResponsiveGrid(135, discountMode, discount));
        if (regular)
        {
            details.Children.Add(ResponsiveGrid(135, gst, taxTreatment));
            details.Children.Add(inclusive);
        }
        var removeButton = Button("Remove item", () => remove(this));
        AutomationProperties.SetName(removeButton, $"Remove {name} from sale");
        details.Children.Add(removeButton);
        var adjustments = new Expander
        {
            Header = regular ? "Discount and tax" : "Discount and removal",
            Content = details,
            HorizontalContentAlignment = HorizontalAlignment.Stretch,
            HorizontalAlignment = HorizontalAlignment.Stretch,
        };
        if (discountState.Value is not ("" or "0" or "0.00")) adjustments.IsExpanded = true;

        var title = new Grid { ColumnSpacing = 10 };
        title.ColumnDefinitions.Add(new ColumnDefinition());
        title.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
        title.Children.Add(description);
        Grid.SetColumn(total, 1);
        title.Children.Add(total);
        var content = Stack(10);
        content.Children.Add(title);
        content.Children.Add(ResponsiveGrid(155, quantityContents, rate));
        content.Children.Add(adjustments);
        View = Card(content);
        View.Padding = new Thickness(14);

        foreach (var input in new[] { quantity, rate, gst, discount })
            input.TextChanged += (_, _) => Changed?.Invoke();
        discountMode.SelectionChanged += (_, _) =>
        {
            discountState.Select(Value(discountMode));
            discount.Text = discountState.Value;
            discount.Header = discountState.Mode == "amount" ? "Discount (₹)" : "Discount (%)";
            Changed?.Invoke();
        };
        taxTreatment.SelectionChanged += (_, _) =>
        {
            if (Value(taxTreatment) != "taxable") gst.Text = "0";
            Changed?.Invoke();
        };
        inclusive.Checked += (_, _) => Changed?.Invoke();
        inclusive.Unchecked += (_, _) => Changed?.Invoke();
    }

    private static Button StepButton(string label, string automationName, Action change)
    {
        var button = Button(label, change);
        button.Padding = new Thickness(0);
        button.Width = 38;
        AutomationProperties.SetName(button, automationName);
        return button;
    }

    internal void SetQuantity(decimal amount) => quantity.Text = amount.ToString("0.###", CultureInfo.InvariantCulture);
    internal void RenderAmount(decimal? amount) => total.Text = amount is null ? "—" : J.Money(amount.Value);

    internal JsonObject Data()
    {
        var line = source.DeepClone().AsObject();
        line["quantity"] = quantity.Text.Trim();
        line["rate"] = rate.Text.Trim();
        line["price_includes_tax"] = inclusive.IsChecked == true;
        line["gst_rate"] = gst.Text.Trim() is { Length: > 0 } gstRate ? gstRate : "0";
        line["tax_treatment"] = Value(taxTreatment);
        discountState.Value = discount.Text;
        discountState.WriteTo(line);
        return line;
    }
}
