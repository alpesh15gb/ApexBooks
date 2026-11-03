using ApexBooks_Windows.Models;
using ApexBooks_Windows.Services;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using System.Text.Json.Nodes;
using static ApexBooks_Windows.Views.NativeUi;

namespace ApexBooks_Windows;

public sealed partial class MainPage
{
    private async Task CancelDocument(JsonObject row)
    {
        var cid = CompanyId; var stamp = generation;
        var label = row.Text("number") is { Length: > 0 } number ? number : Friendly(row.Text("kind"));
        var reason = Input("Reason (required)", ""); reason.MaxLength = 200;
        var panel = Stack(12); panel.MinWidth = 440;
        panel.Children.Add(Text("Cancel " + label + "?", 16, true));
        panel.Children.Add(Text("This reverses its ledger entry, returns any stock and frees balances it used. The number is kept and the action is logged. It cannot be undone.", 13));
        panel.Children.Add(reason);
        var done = await Dialog("Cancel document", panel, async () =>
        {
            if (reason.Text.Trim().Length < 3) throw new Exception("Enter a reason of at least 3 characters.");
            await Api.CancelRecord(cid, row.Text("id"), reason.Text.Trim());
        }, "Cancel document");
        if (done && stamp == generation && cid == CompanyId) { await Refresh(); await TransactionDetails(row); }
    }
}
