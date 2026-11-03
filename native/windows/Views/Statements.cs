using ApexBooks_Windows.Models;
using ApexBooks_Windows.Services;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using System.Text.Json.Nodes;
using static ApexBooks_Windows.Views.NativeUi;

namespace ApexBooks_Windows;

public sealed partial class MainPage
{
    /// <summary>Formatted Profit &amp; Loss and Balance Sheet from /reports/statements. Figures are server-calculated.</summary>
    private static void RenderStatements(Panel panel, JsonObject data)
    {
        var pl = data["profit_loss"].Object(); var bs = data["balance_sheet"].Object();
        StackPanel Statement(string title, string period)
        {
            var s = Stack(4); s.Children.Add(Text(title, 20, true)); s.Children.Add(Text(period, 12)); return s;
        }
        void Heading(StackPanel s, string text) { var t = Text(text.ToUpperInvariant(), 11, true); t.Margin = new Thickness(0, 12, 0, 2); s.Children.Add(t); }
        void Row(StackPanel s, string label, string amount, bool bold = false, bool indent = false, double size = 14)
        {
            var grid = new Grid { ColumnSpacing = 12, Margin = new Thickness(indent ? 16 : 0, 0, 0, 0) };
            grid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
            grid.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
            var left = Text(label, size, bold); left.TextWrapping = TextWrapping.Wrap;
            var right = Text(J.Money(decimal.TryParse(amount, System.Globalization.NumberStyles.Any, System.Globalization.CultureInfo.InvariantCulture, out var v) ? v : 0), size, bold);
            right.HorizontalAlignment = HorizontalAlignment.Right; Grid.SetColumn(right, 1);
            grid.Children.Add(left); grid.Children.Add(right); s.Children.Add(grid);
        }
        void Lines(StackPanel s, JsonArray lines, string empty)
        {
            if (lines.Count == 0 && empty.Length > 0) s.Children.Add(Text(empty, 12));
            foreach (var line in lines) Row(s, line.Text("name"), line.Text("amount"), indent: true);
        }
        void Sections(StackPanel s, JsonArray sections)
        {
            if (sections.Count == 0) s.Children.Add(Text("None", 12));
            foreach (var section in sections)
            {
                Row(s, section.Text("label"), section.Text("total"), bold: true);
                var lines = section["lines"].Array();
                if (lines.Count > 1) foreach (var line in lines) Row(s, line.Text("name"), line.Text("amount"), indent: true);
            }
        }
        var profit = Statement("Profit and loss", data.Text("from_date") + " to " + data.Text("to_date"));
        Heading(profit, "Revenue"); Lines(profit, pl["revenue"]["lines"].Array(), "No sales in this period"); Row(profit, "Total revenue", pl["revenue"].Text("total"), true);
        Heading(profit, "Cost of sales"); Lines(profit, pl["cost_of_sales"]["lines"].Array(), "No cost of sales"); Row(profit, "Total cost of sales", pl["cost_of_sales"].Text("total"), true);
        Row(profit, "Gross profit", pl.Text("gross_profit"), true, size: 16);
        if (pl.Text("gross_margin_percent").Length > 0) profit.Children.Add(Text(pl.Text("gross_margin_percent") + "% of revenue", 12));
        if (pl["other_income"]["lines"].Array().Count > 0) { Heading(profit, "Other income"); Lines(profit, pl["other_income"]["lines"].Array(), ""); Row(profit, "Total other income", pl["other_income"].Text("total"), true); }
        Heading(profit, "Operating expenses"); Lines(profit, pl["operating_expenses"]["lines"].Array(), "No expenses recorded"); Row(profit, "Total operating expenses", pl["operating_expenses"].Text("total"), true);
        Row(profit, pl.Number("net_profit") < 0 ? "Net loss" : "Net profit", pl.Text("net_profit"), true, size: 18);

        var sheet = Statement("Balance sheet", "As of " + bs.Text("as_of"));
        Heading(sheet, "Assets"); Sections(sheet, bs["assets"]["sections"].Array()); Row(sheet, "Total assets", bs["assets"].Text("total"), true, size: 16);
        Heading(sheet, "Liabilities"); Sections(sheet, bs["liabilities"]["sections"].Array()); Row(sheet, "Total liabilities", bs["liabilities"].Text("total"), true, size: 16);
        Heading(sheet, "Equity"); Lines(sheet, bs["equity"]["lines"].Array(), ""); Row(sheet, "Total equity", bs["equity"].Text("total"), true, size: 16);
        Row(sheet, "Total liabilities and equity", bs.Text("total_liabilities_and_equity"), true, size: 18);
        var balanced = bs.Number("difference") == 0;
        sheet.Children.Add(Text(balanced ? "Balance sheet balances: assets equal liabilities plus equity." : "Out of balance by " + J.Money(bs.Number("difference")) + ". Do not rely on these figures.", 12, true));

        panel.Children.Add(Card(profit)); panel.Children.Add(Card(sheet));
        panel.Children.Add(Card(Text(data.Text("basis") + " Depreciation, net realisable value write-downs and accruals are not calculated; review with your accountant before using these statements for filing or lending.", 12)));
    }
}
