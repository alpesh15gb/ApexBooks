using ApexBooks_Windows.Services;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using static ApexBooks_Windows.Views.NativeUi;

namespace ApexBooks_Windows;

public sealed partial class MainPage
{
    /// <summary>"Remind all overdue": WhatsApp opens one customer at a time; nothing is sent until you press send there.</summary>
    private async Task RemindOverdue(List<WhatsAppShare.OverdueGroup> groups)
    {
        var upi = ""; try { upi = (await Api.Send(PathFor("/document-branding"))).Text("upi_id"); } catch (Exception) { /* works without a UPI ID */ }
        var panel = Stack(8); panel.MinWidth = 560;
        panel.Children.Add(Text($"{groups.Count} {(groups.Count==1?"customer":"customers")} · {J.Money(groups.Sum(g => g.Total))} overdue · one WhatsApp message each", 13));
        foreach (var group in groups)
        {
            var row = new Grid { ColumnSpacing = 12 };
            row.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
            row.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
            row.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
            var who = Stack(2); who.Children.Add(Text(group.Name, 14, true));
            var detail = Text(string.Join(", ", group.Invoices.Select(i => i.Text("number"))) + (WhatsAppShare.Phone(group.Phone).Length == 0 ? " · no phone saved" : ""), 12); detail.Foreground = Muted; who.Children.Add(detail);
            var amount = Text(J.Money(group.Total), 14, true); amount.VerticalAlignment = VerticalAlignment.Center; Grid.SetColumn(amount, 1);
            Button send = null!;
            send = Button("Remind on WhatsApp", () => { _ = Windows.System.Launcher.LaunchUriAsync(WhatsAppShare.Url(group.Phone, WhatsAppShare.PartyReminderMessage(group, Company.Text("name"), upi))); send.Content = "Opened ✓"; });
            Grid.SetColumn(send, 2);
            row.Children.Add(who); row.Children.Add(amount); row.Children.Add(send);
            panel.Children.Add(Card(row));
        }
        panel.Children.Add(Text("WhatsApp opens with the message filled in. Customers without a saved phone open WhatsApp so you can pick the chat.", 12));
        await Dialog("Remind overdue customers", panel, () => Task.CompletedTask, "Done");
    }
}
