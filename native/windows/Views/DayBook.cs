using ApexBooks_Windows.Models;
using ApexBooks_Windows.Services;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using System.Text.Json.Nodes;
using static ApexBooks_Windows.Views.NativeUi;

namespace ApexBooks_Windows;

public sealed partial class MainPage
{
    private string dayBookDay = "";

    /// <summary>Day book (Vyapar / MyBillBook style): everything dated one day, with the cash and bank it moved.</summary>
    private async Task DayBookPage()
    {
        if (!Supports("day_book")) { Body.Children.Add(Card(Text("The day book needs an updated Apex Books server. Your records are unaffected.", 14))); return; }
        var cid = CompanyId; var stamp = generation;
        if (dayBookDay.Length == 0) dayBookDay = J.Today;
        var bar = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 8 };
        var picker = new CalendarDatePicker { Date = new DateTimeOffset(DateTime.Parse(dayBookDay, System.Globalization.CultureInfo.InvariantCulture)), MinHeight = 34 };
        Task Go(string day) { dayBookDay = day; return Navigate("day_book"); }
        string Shift(int days) => DateTime.Parse(dayBookDay, System.Globalization.CultureInfo.InvariantCulture).AddDays(days).ToString("yyyy-MM-dd");
        bar.Children.Add(Button("‹ Previous", () => _ = Go(Shift(-1))));
        bar.Children.Add(picker);
        bar.Children.Add(Button("Next ›", () => _ = Go(Shift(1))));
        if (dayBookDay != J.Today) bar.Children.Add(Button("Today", () => _ = Go(J.Today)));
        picker.DateChanged += (sender, args) => { if (args.NewDate is { } d && d.ToString("yyyy-MM-dd") != dayBookDay) _ = Go(d.ToString("yyyy-MM-dd")); };
        Body.Children.Add(bar);
        var book = (await Api.Send(Api.CompanyPath(cid, "/day-book?day=" + Uri.EscapeDataString(dayBookDay)))).Object();
        if (stamp != generation || cid != CompanyId) return;
        var totals = book["totals"];
        var metrics = new Grid { ColumnSpacing = 10 };
        var cards = new[] { ("Sales", J.Money(totals.Number("sales"))), ("Purchases & expenses", J.Money(totals.Number("purchases") + totals.Number("expenses"))), ("Money in", J.Money(totals.Number("money_in"))), ("Money out", J.Money(totals.Number("money_out"))) };
        for (var i = 0; i < cards.Length; i++)
        {
            metrics.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
            var card = Stack(3); card.Children.Add(Text(cards[i].Item1.ToUpperInvariant(), 11, true)); var value = Text(cards[i].Item2, 22, true);
            if (i == 2) value.Foreground = Green; card.Children.Add(value);
            if (i == 3) card.Children.Add(Text("Net " + J.Money(totals.Number("net")), 12));
            var holder = Card(card); Grid.SetColumn(holder, i); metrics.Children.Add(holder);
        }
        Body.Children.Add(metrics);
        var list = Stack(0);
        var head = DayBookRow("TYPE", "NUMBER / PARTY", "AMOUNT", "MONEY IN", "MONEY OUT", true); list.Children.Add(head);
        foreach (var row in book["rows"].Array().OfType<JsonObject>())
        {
            var kind = row.Text("kind"); var state = row.Flag("cancelled") ? " · cancelled" : !row.Flag("posted") && kind != "journal" ? " · draft" : "";
            var label = FeatureCatalog.Singular(kind); var line = DayBookRow(char.ToUpperInvariant(label[0]) + label[1..] + state, (row.Text("number") is { Length: > 0 } n ? n + "  ·  " : "") + row.Text("name"), J.Money(row.Number("amount")),
                row.Number("money_in") > 0 ? J.Money(row.Number("money_in")) : "", row.Number("money_out") > 0 ? J.Money(row.Number("money_out")) : "");
            if (kind != "journal" && Records.OfType<JsonObject>().FirstOrDefault(r => r.Text("id") == row.Text("id")) is { } record)
            {
                var open = new Button { Content = line, HorizontalAlignment = HorizontalAlignment.Stretch, HorizontalContentAlignment = HorizontalAlignment.Stretch, Background = null, BorderThickness = new Thickness(0), Padding = new Thickness(0) };
                open.Click += async (_, _) => await Run(() => TransactionDetails(record)); list.Children.Add(open);
            }
            else list.Children.Add(line);
        }
        if (book.Number("count") == 0) list.Children.Add(Text("Nothing recorded on this day.", 14));
        Body.Children.Add(Card(list));
    }

    private static Grid DayBookRow(string kind, string party, string amount, string moneyIn, string moneyOut, bool header = false)
    {
        var grid = new Grid { Padding = new Thickness(12, 7, 12, 7), ColumnSpacing = 12 };
        foreach (var width in new[] { 1.4, 3.0, 1.2, 1.2, 1.2 }) grid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(width, GridUnitType.Star) });
        var values = new[] { kind, party, amount, moneyIn, moneyOut };
        for (var i = 0; i < values.Length; i++)
        {
            var text = Text(values[i], header ? 11 : 13, header); text.TextTrimming = TextTrimming.CharacterEllipsis;
            if (i >= 2) text.HorizontalAlignment = HorizontalAlignment.Right;
            if (!header && i == 3) text.Foreground = Green;
            Grid.SetColumn(text, i); grid.Children.Add(text);
        }
        if (header) { grid.BorderThickness = new Thickness(0, 0, 0, 1); grid.BorderBrush = Brush(0xE2, 0xE8, 0xF0); }
        return grid;
    }
}
