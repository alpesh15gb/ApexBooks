using ApexBooks_Windows.Services;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Controls;
using System.Net.Http;
using System.Text.Json.Nodes;
using static ApexBooks_Windows.Views.NativeUi;

namespace ApexBooks_Windows;

public sealed partial class MainPage
{
    private static bool PurchaseReceivingStarted(JsonNode? order) => order.Text("kind") == "purchase_order"
        && order?["data"].Flag("purchase_order_receiving_started") == true;

    private static Border PurchaseReceivingSummary(JsonObject receiving, Action<string> openBill)
    {
        var contents = Stack(10);
        contents.Children.Add(Text("Receiving", 17, true));
        var status = receiving.Text("status") switch
        {
            "open" => "Awaiting delivery",
            "partial" => "Partially received",
            "received" => "Received in full",
            "converted" => "Converted to a purchase bill",
            _ => receiving.Text("reason") is { Length: > 0 } error ? error : "Receiving details unavailable",
        };
        var statusLabel = Text(status, 13, true);
        statusLabel.Foreground = Muted;
        contents.Children.Add(statusLabel);
        foreach (var line in receiving["lines"].Array())
        {
            var unit = line.Text("unit") is { Length: > 0 } lineUnit ? " " + lineUnit : "";
            contents.Children.Add(Text($"{line.Text("description")} · {line.Number("received_quantity"):0.###} of {line.Number("ordered_quantity"):0.###}{unit} received · {line.Number("remaining_quantity"):0.###} remaining"));
        }
        var receipts = receiving["receipts"].Array();
        if (receipts.Count > 0) contents.Children.Add(Text("Linked supplier bills", 14, true));
        foreach (var receipt in receipts)
        {
            var id = receipt.Text("id");
            var label = $"{receipt.Text("number")} · {receipt.Text("date")} · {J.Money(receipt.Number("amount"))}";
            if (receipt.Flag("cancelled")) label += " · Cancelled";
            var button = Button(label, () => openBill(id));
            button.HorizontalAlignment = HorizontalAlignment.Stretch;
            button.HorizontalContentAlignment = HorizontalAlignment.Left;
            contents.Children.Add(button);
        }
        var card = Card(contents);
        card.Padding = new Thickness(16);
        return card;
    }

    private async Task ReceivePurchaseOrder(JsonObject order, JsonObject snapshot)
    {
        if (!CanWrite || snapshot.Text("status") is not ("open" or "partial")) return;
        var cid = CompanyId;
        var access = CaptureFileSaveAccess();
        var orderId = Uri.EscapeDataString(order.Text("id"));
        var sourceVersion = (int)snapshot.Number("source_version");
        var retry = new RetrySubmission();
        var key = Guid.NewGuid().ToString();
        var rows = new List<(JsonNode Source, TextBox Quantity, TextBox Rate)>();
        var form = Stack(14);
        form.Children.Add(Text($"{order.Text("number")} · {order.Text("name")}", 17, true));
        var reference = Input("Supplier bill reference");
        reference.MaxLength = 16;
        reference.PlaceholderText = "Leave blank for the next bill number";
        var date = new DateInput("Bill date", J.Today);
        var due = new DateInput("Due date (optional)");
        var notes = Input("Delivery notes (optional)", multi: true);
        form.Children.Add(reference);
        form.Children.Add(ResponsiveGrid(235, date.View, due.View));
        foreach (var source in snapshot["lines"].Array().Where(line => line.Number("remaining_quantity") > 0))
        {
            var description = source.Text("description");
            var unit = source.Text("unit") is { Length: > 0 } lineUnit ? " " + lineUnit : "";
            var qty = Input("Receive now");
            qty.PlaceholderText = "0";
            qty.MaxLength = 16;
            AutomationProperties.SetName(qty, $"Quantity received for {description}");
            var rate = Input("Bill unit price (₹)");
            rate.PlaceholderText = source.Text("rate");
            rate.MaxLength = 16;
            AutomationProperties.SetName(rate, $"Bill unit price for {description}");
            var line = Stack(8);
            line.Children.Add(Text(description, 14, true));
            var amounts = Text($"{source.Number("received_quantity"):0.###} received · {source.Number("remaining_quantity"):0.###}{unit} remaining", 12);
            amounts.Foreground = Muted;
            line.Children.Add(amounts);
            var tax = source.Number("gst_rate");
            var pricing = Text($"Order unit price {J.Money(source.Number("rate"))}"
                + (tax > 0 ? $" · GST {tax:0.##}% {(source.Flag("price_includes_tax") ? "included" : "added")}" : ""), 12);
            pricing.Foreground = Muted;
            line.Children.Add(pricing);
            line.Children.Add(ResponsiveGrid(155, qty, rate));
            var card = Card(line);
            card.Padding = new Thickness(14);
            form.Children.Add(card);
            rows.Add((source!, qty, rate));
        }
        form.Children.Add(notes);
        var fields = new ContentControl { Content = form, HorizontalContentAlignment = HorizontalAlignment.Stretch };
        var panel = Stack(12);
        panel.Children.Add(fields);
        var total = Text("Review the bill total before posting stock.", 16, true);
        total.Foreground = Green;
        var status = Card(total);
        status.Padding = new Thickness(12);
        var reloadRequested = false;
        var reload = Button("Refresh order", () => { reloadRequested = true; CloseDialog(); });
        reload.Visibility = Visibility.Collapsed;
        JsonObject? saved = null;
        string? approvedDraft = null;
        string approvedAmount = "";

        JsonObject? Draft()
        {
            var selected = new JsonArray();
            foreach (var (source, quantity, rate) in rows)
            {
                if (string.IsNullOrWhiteSpace(quantity.Text)) continue;
                if (!ReadCountValue(quantity.Text, 3, source.Number("remaining_quantity"), out var received))
                    return null;
                if (received == 0) continue;
                var entry = new JsonObject { ["line_index"] = (int)source.Number("line_index"), ["quantity"] = quantity.Text.Trim() };
                if (!string.IsNullOrWhiteSpace(rate.Text))
                {
                    if (!ReadCountValue(rate.Text, 2, 9_999_999_999_999.99m, out _)) return null;
                    entry["rate"] = rate.Text.Trim();
                }
                selected.Add(entry);
            }
            if (selected.Count == 0 || date.Value.Length == 0) return null;
            return new JsonObject
            {
                ["source_version"] = sourceVersion, ["date"] = date.Value, ["number"] = reference.Text.Trim(),
                ["due_date"] = due.Value.Length > 0 ? due.Value : null, ["notes"] = notes.Text.Trim(), ["lines"] = selected,
            };
        }
        bool Ready() => CanWrite && ScopedFileExport.Current(access)
            && (retry.Unresolved || reload.Visibility != Visibility.Visible && approvedDraft is not null && Draft()?.ToJsonString() == approvedDraft);
        void Changed()
        {
            approvedDraft = null;
            if (!retry.Unresolved) total.Text = "Review the bill total before posting stock.";
            RefreshDialogActions(clearError: true);
        }
        foreach (var (_, quantity, rate) in rows)
        {
            quantity.TextChanged += (_, _) => Changed();
            rate.TextChanged += (_, _) => Changed();
        }
        reference.TextChanged += (_, _) => Changed();
        notes.TextChanged += (_, _) => Changed();
        date.Picker.DateChanged += (_, _) => Changed();
        due.Picker.DateChanged += (_, _) => Changed();
        void NeedRefresh()
        {
            approvedDraft = null;
            reload.Visibility = Visibility.Visible;
            total.Text = "Refresh the purchase order before reviewing another receipt.";
            RefreshDialogActions();
        }
        var review = AsyncButton("Review bill total", async () =>
        {
            access();
            if (reload.Visibility == Visibility.Visible)
                throw new InvalidOperationException("Refresh the order before reviewing its bill total again.");
            if (Draft() is not { } draft)
                throw new InvalidOperationException("Enter a quantity within the remaining stock on at least one line and review any price changes.");
            approvedDraft = null;
            try
            {
                var preview = await Api.Send(Api.CompanyPath(cid, $"/purchase-orders/{orderId}/receipts/preview"), HttpMethod.Post, draft);
                access();
                if (preview.Number("amount") <= 0 || Draft()?.ToJsonString() != draft.ToJsonString()) return;
                approvedDraft = draft.ToJsonString();
                approvedAmount = preview.Text("amount");
                total.Text = $"Bill total {J.Money(preview.Number("amount"))}";
            }
            catch (ApiFailure error) when (error.Status == 409)
            {
                NeedRefresh();
                throw;
            }
            finally { RefreshDialogActions(); }
        }, Error, true);
        form.Children.Add(review);
        panel.Children.Add(status);
        panel.Children.Add(reload);

        async Task Post()
        {
            access();
            if (!Ready()) return;
            var body = retry.Unresolved ? new JsonObject() : Draft()!;
            if (!retry.Unresolved) body["expected_total"] = approvedAmount;
            try
            {
                var bill = (await Api.Send(Api.CompanyPath(cid, $"/purchase-orders/{orderId}/receipts"),
                    HttpMethod.Post, retry.Body(body), key)).Object();
                if (bill.Text("kind") != "purchase_bill" || bill.Text("id").Length == 0)
                    throw new ApiFailure(502, "The supplier bill response was incomplete.");
                retry.Succeeded();
                saved = bill;
            }
            catch (ApiFailure error) when (error.Status == 409)
            {
                retry.Succeeded();
                NeedRefresh();
                throw;
            }
            catch (Exception error)
            {
                if (error is not ApiFailure { Status: 401 or 403 }) retry.Failed(error);
                if (retry.Unresolved)
                    throw new InvalidOperationException("The receipt response was interrupted. Select Post supplier bill again to recover the original bill.", error);
                throw;
            }
            finally
            {
                fields.IsEnabled = !retry.Unresolved;
                RefreshDialogActions();
            }
        }
        var confirmed = await Dialog("Receive purchase order", panel, Post, "Post supplier bill", Ready,
            hasChanges: () => !reloadRequested && (rows.Any(row => row.Quantity.Text.Length > 0 || row.Rate.Text.Length > 0)
                || reference.Text.Length > 0 || notes.Text.Length > 0),
            unresolved: () => retry.Unresolved);
        if (reloadRequested && ScopedFileExport.Current(access)) await TransactionDetails(order);
        if (confirmed && saved is not null && ScopedFileExport.Current(access))
        {
            var captured = saved;
            await Refresh();
            if (cid == CompanyId)
                Success($"Received stock on {captured.Text("number")} · {J.Money(captured.Number("amount"))}");
        }
    }
}
