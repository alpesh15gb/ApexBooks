using ApexBooks_Windows.Services;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using System.Globalization;
using System.Text.Json.Nodes;
using static ApexBooks_Windows.Views.NativeUi;

namespace ApexBooks_Windows.Views;

/// <summary>Tally-style party ledger: date, particulars, voucher, debit, credit and a running Dr/Cr balance.</summary>
public static class PartyLedgerView
{
    private const int PageSize = 100;
    private static readonly double[] Widths = { 95, 175, 70, 115, 90, 90, 125 };
    private static readonly string[] Headings = { "Date", "Particulars", "Vch Type", "Vch No.", "Debit", "Credit", "Balance" };

    public static string Date(string iso) =>
        DateOnly.TryParseExact(iso, "yyyy-MM-dd", CultureInfo.InvariantCulture, DateTimeStyles.None, out var day)
            ? day.ToString("dd-MMM-yyyy", CultureInfo.InvariantCulture) : iso;

    /// <summary>Indian digit grouping; a blank stays blank so an empty debit or credit cell stays empty.</summary>
    public static string Amount(string value)
    {
        if (!decimal.TryParse(value, NumberStyles.Number, CultureInfo.InvariantCulture, out var number)) return "";
        var parts = Math.Abs(number).ToString("0.00", CultureInfo.InvariantCulture).Split('.');
        var whole = parts[0];
        var grouped = whole.Length > 3 ? whole[^3..] : whole;
        whole = whole.Length > 3 ? whole[..^3] : "";
        while (whole.Length > 0)
        {
            grouped = (whole.Length > 2 ? whole[^2..] : whole) + "," + grouped;
            whole = whole.Length > 2 ? whole[..^2] : "";
        }
        return (number < 0 ? "-" : "") + grouped + "." + parts[1];
    }

    public static string Balance(string amount, string side) => (Amount(amount.Length > 0 ? amount : "0") + " " + side).Trim();

    private static Grid Row(string[] cells, bool strong, bool header = false)
    {
        var grid = new Grid { ColumnSpacing = 12, Padding = new Thickness(10), BorderBrush = Brush(0xEC, 0xED, 0xF0), BorderThickness = new Thickness(0, 0, 0, 1) };
        if (header) grid.Background = Brush(0xF0, 0xF2, 0xF5);
        foreach (var width in Widths) grid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(width) });
        for (var i = 0; i < cells.Length; i++)
        {
            var text = Text(cells[i], header ? 12 : 13, strong || header);
            if (i >= 4) text.TextAlignment = TextAlignment.Right;
            Grid.SetColumn(text, i);
            grid.Children.Add(text);
        }
        return grid;
    }

    public static UIElement Build(JsonObject ledger)
    {
        var opening = ledger["opening"].Object();
        var totals = ledger["totals"].Object();
        var closing = ledger["closing"].Object();
        var rows = ledger["rows"].Array().OfType<JsonObject>().ToArray();
        var table = Stack(0);
        var pageRows = Stack(0);
        var page = 0;
        var status = Text("", 12);
        Button previous = null!, next = null!;
        void Render()
        {
            pageRows.Children.Clear();
            foreach (var row in rows.Skip(page * PageSize).Take(PageSize))
                pageRows.Children.Add(Row(new[] { Date(row.Text("date")), row.Text("particulars"), row.Text("voucher_type"), row.Text("voucher_number"), Amount(row.Text("debit")), Amount(row.Text("credit")), Balance(row.Text("balance"), row.Text("balance_side")) }, false));
            status.Text = rows.Length == 0 ? "No entries in this period" : $"{page * PageSize + 1}–{Math.Min((page + 1) * PageSize, rows.Length)} of {rows.Length}";
            previous.IsEnabled = page > 0;
            next.IsEnabled = (page + 1) * PageSize < rows.Length;
        }
        previous = Button("Previous", () => { page--; Render(); });
        next = Button("Next", () => { page++; Render(); });
        table.Children.Add(Row(Headings, true, true));
        table.Children.Add(Row(new[] { "", "Opening balance", "", "", "", "", Balance(opening.Text("amount"), opening.Text("side")) }, true));
        table.Children.Add(pageRows);
        table.Children.Add(Row(new[] { "", "Current total", "", "", Amount(totals.Text("debit")), Amount(totals.Text("credit")), "" }, true));
        table.Children.Add(Row(new[] { "", "Closing balance", "", "", "", "", Balance(closing.Text("amount"), closing.Text("side")) }, true));
        Render();
        var panel = Stack(8);
        panel.Children.Add(Text("Ledger", 20, true));
        panel.Children.Add(new ScrollViewer { Content = table, HorizontalScrollBarVisibility = ScrollBarVisibility.Auto, VerticalScrollBarVisibility = ScrollBarVisibility.Disabled, HorizontalScrollMode = ScrollMode.Auto, VerticalScrollMode = ScrollMode.Disabled });
        if (rows.Length > PageSize)
        {
            var pager = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 16, VerticalAlignment = VerticalAlignment.Center };
            pager.Children.Add(previous);
            pager.Children.Add(status);
            pager.Children.Add(next);
            panel.Children.Add(pager);
        }
        return panel;
    }
}
