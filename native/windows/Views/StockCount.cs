using ApexBooks_Windows.Services;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Controls;
using System.Globalization;
using System.Net.Http;
using System.Text.Json.Nodes;
using Windows.System;
using static ApexBooks_Windows.Views.NativeUi;

namespace ApexBooks_Windows;

public sealed partial class MainPage
{
    private async Task StockCount()
    {
        var cid = CompanyId;
        var access = CaptureFileSaveAccess();
        var items = Records.OfType<JsonObject>().Where(row => row.Text("kind") == "item"
            && row["data"].Flag("track_stock") && row["data"].Text("item_type") is ("" or "goods"))
            .OrderBy(row => row.Text("name"), StringComparer.OrdinalIgnoreCase).ToArray();
        if (items.Length == 0)
        {
            await Dialog("Physical stock count", Text("Add a stock-tracked item before recording a count."),
                () => Task.CompletedTask, "Done");
            return;
        }

        var closed = false;
        var retry = new RetrySubmission();
        var key = Guid.NewGuid().ToString();
        JsonObject? snapshot = null, saved = null;
        CancellationTokenSource? reading = null;
        bool Current() => !closed && ScopedFileExport.Current(access);
        var form = Stack(14);
        var scan = Input("Scan item barcode");
        scan.PlaceholderText = "Scan or type a barcode";
        AutomationProperties.SetName(scan, "Scan item barcode");
        var item = Select("Tracked item", new[] { ("", "Choose a tracked item") }
            .Concat(items.Select(row => (row.Text("id"), row.Text("name")))));
        var scanError = new InfoBar { Severity = InfoBarSeverity.Warning, IsClosable = false, Visibility = Visibility.Collapsed };
        var stockLabel = Text("Current on hand", 13, true);
        var onHand = Text("Select an item", 22, true);
        onHand.Foreground = Green;
        AutomationProperties.SetAutomationId(onHand, "CountOnHand");
        var snapshotDate = Text("", 12);
        snapshotDate.Foreground = Muted;
        var counted = Input("Counted quantity");
        counted.PlaceholderText = "Units physically on hand";
        counted.MaxLength = 16;
        var cost = Input("Unit cost for added stock (₹)");
        cost.PlaceholderText = "Cost per unit";
        cost.MaxLength = 16;
        var reason = Input("Reason for difference");
        reason.MaxLength = 500;
        reason.PlaceholderText = "For example, damaged stock found during stocktake";
        var difference = Text("", 16, true);
        var reasonNote = Text("", 12);
        reasonNote.Foreground = Muted;
        var summary = Stack(4);
        summary.Children.Add(Text("Count difference", 13, true));
        summary.Children.Add(difference);
        summary.Children.Add(reasonNote);
        var summaryCard = Card(summary);
        summaryCard.Padding = new Thickness(12);
        var fields = new ContentControl { Content = form, HorizontalContentAlignment = HorizontalAlignment.Stretch };

        (bool Valid, decimal Change) Variance()
        {
            if (snapshot is null || !ReadCountValue(counted.Text, 3, 999_999_999_999.999m, out var quantity))
                return (false, 0);
            return (true, quantity - snapshot.Number("on_hand"));
        }
        bool Ready()
        {
            if (!CanWrite || !Current()) return false;
            if (retry.Unresolved) return true;
            var variance = Variance();
            return variance.Valid && variance.Change != 0 && reason.Text.Trim().Length > 0
                && (variance.Change < 0 || ReadCountValue(cost.Text, 2, 9_999_999_999_999.99m, out var unitCost) && unitCost > 0);
        }
        string Units()
        {
            var unit = items.FirstOrDefault(row => row.Text("id") == Value(item))?["data"].Text("unit");
            return string.IsNullOrWhiteSpace(unit) ? "units" : unit;
        }
        static string Quantity(decimal number) => number.ToString("0.###", CultureInfo.InvariantCulture);

        void Update()
        {
            var variance = Variance();
            fields.IsEnabled = !retry.Unresolved && CanWrite;
            counted.IsEnabled = reason.IsEnabled = snapshot is not null;
            cost.Visibility = variance.Valid && variance.Change > 0 ? Visibility.Visible : Visibility.Collapsed;
            reason.Visibility = variance.Valid && variance.Change != 0 ? Visibility.Visible : Visibility.Collapsed;
            summaryCard.Visibility = variance.Valid ? Visibility.Visible : Visibility.Collapsed;
            difference.Text = variance.Change switch
            {
                > 0 => $"Increase by {Quantity(variance.Change)} {Units()}",
                < 0 => $"Decrease by {Quantity(-variance.Change)} {Units()}",
                _ => "Count matches on-hand stock",
            };
            difference.Foreground = variance.Change > 0 ? Green : Muted;
            reasonNote.Text = variance.Change switch
            {
                > 0 => "The entered unit cost is used for the inventory gain.",
                < 0 => "The current moving-average cost is used for the inventory loss.",
                _ => "No adjustment is needed.",
            };
            RefreshDialogActions();
        }
        void ScanWarning(string message)
        {
            scanError.Message = message;
            scanError.IsOpen = message.Length > 0;
            scanError.Visibility = scanError.IsOpen ? Visibility.Visible : Visibility.Collapsed;
        }
        void ResetCount()
        {
            snapshot = null;
            counted.Text = "";
            cost.Text = "";
            snapshotDate.Text = "";
            Update();
        }
        async Task ReadOnHand(bool focus)
        {
            if (!Current() || retry.Unresolved) return;
            reading?.Cancel();
            ResetCount();
            var itemId = Value(item);
            onHand.Text = itemId.Length == 0 ? "Select an item" : "Checking stock…";
            if (itemId.Length == 0) return;
            using var request = new CancellationTokenSource();
            reading = request;
            try
            {
                var result = (await Api.Send(Api.CompanyPath(cid, $"/stock/counts/{Uri.EscapeDataString(itemId)}"),
                    cancellation: request.Token)).Object();
                if (!Current() || request.IsCancellationRequested || itemId != Value(item)) return;
                if (result.Text("item_id") != itemId || result.Text("stock_snapshot").Length != 64
                    || !ReadCountValue(result.Text("on_hand"), 3, 999_999_999_999.999m, out var quantity))
                    throw new InvalidOperationException("The server did not return a complete stock snapshot.");
                snapshot = result;
                onHand.Text = $"{Quantity(quantity)} {Units()}";
                snapshotDate.Text = "As of " + result.Text("date");
                Update();
                if (focus) counted.Focus(FocusState.Keyboard);
            }
            catch (Exception error)
            {
                if (!request.IsCancellationRequested && Current())
                {
                    onHand.Text = "Stock snapshot unavailable";
                    ScanWarning(error.Message);
                }
            }
            finally
            {
                if (ReferenceEquals(reading, request)) reading = null;
            }
        }
        item.SelectionChanged += async (_, _) =>
        {
            reason.Text = "";
            ScanWarning("");
            await ReadOnHand(true);
        };
        async Task LookupBarcode()
        {
            var barcode = scan.Text.Trim();
            if (barcode.Length == 0 || !Current() || retry.Unresolved) return;
            var matches = items.Where(row => row["data"].Text("barcode") == barcode).Take(2).ToArray();
            if (matches.Length != 1)
            {
                ScanWarning(matches.Length == 0 ? "No tracked goods match this barcode." : "Several goods share this barcode. Select an item by name.");
                return;
            }
            scan.Text = "";
            ScanWarning("");
            var chosen = matches[0].Text("id");
            if (chosen == Value(item)) await ReadOnHand(true);
            else SelectValue(item, chosen);
        }
        scan.KeyDown += async (_, args) =>
        {
            if (args.Key != VirtualKey.Enter) return;
            args.Handled = true;
            await LookupBarcode();
        };
        foreach (var input in new[] { counted, cost, reason })
            input.TextChanged += (_, _) => Update();
        var refresh = AsyncButton("Refresh on hand", async () => { ScanWarning(""); await ReadOnHand(true); }, Error);
        var stockValues = Stack(3);
        stockValues.Children.Add(stockLabel);
        stockValues.Children.Add(onHand);
        stockValues.Children.Add(snapshotDate);
        var snapshotCard = Card(ResponsiveGrid(160, stockValues, refresh));
        snapshotCard.Padding = new Thickness(12);
        var lookup = AsyncButton("Find barcode", LookupBarcode, Error);
        lookup.VerticalAlignment = VerticalAlignment.Bottom;
        form.Children.Add(Pair(scan, lookup));
        form.Children.Add(item);
        form.Children.Add(scanError);
        form.Children.Add(snapshotCard);
        form.Children.Add(counted);
        form.Children.Add(summaryCard);
        form.Children.Add(cost);
        form.Children.Add(reason);

        async Task Post()
        {
            access();
            if (!Ready()) return;
            var body = new JsonObject();
            if (!retry.Unresolved)
            {
                body["item_id"] = Value(item);
                body["date"] = snapshot.Text("date");
                body["stock_snapshot"] = snapshot.Text("stock_snapshot");
                body["counted_quantity"] = counted.Text.Trim();
                body["reason"] = reason.Text.Trim();
                if (Variance().Change > 0) body["unit_cost"] = cost.Text.Trim();
            }
            try
            {
                var result = (await Api.Send(Api.CompanyPath(cid, "/stock/counts"), HttpMethod.Post, retry.Body(body), key)).Object();
                if (result.Text("id").Length == 0)
                    throw new ApiFailure(502, "The server did not confirm the adjustment.");
                retry.Succeeded();
                saved = result;
            }
            catch (ApiFailure error) when (error.Status == 409)
            {
                retry.Succeeded();
                if (error.Message.Contains("refresh on-hand stock", StringComparison.OrdinalIgnoreCase))
                {
                    ResetCount();
                    onHand.Text = "Refresh and count again";
                }
                throw;
            }
            catch (Exception error)
            {
                if (error is not ApiFailure { Status: 401 or 403 }) retry.Failed(error);
                if (retry.Unresolved)
                    throw new InvalidOperationException("The count response was interrupted. Select Post count again to recover the original adjustment.", error);
                throw;
            }
            finally { Update(); }
        }

        Update();
        scan.Loaded += (_, _) => scan.Focus(FocusState.Keyboard);
        try
        {
            if (await Dialog("Physical stock count", fields, Post, "Post count", Ready,
                    hasChanges: () => counted.Text.Length > 0 || reason.Text.Length > 0,
                    unresolved: () => retry.Unresolved) && saved is not null && Current())
            {
                var result = saved;
                await Refresh();
                if (cid == CompanyId)
                    Success($"Count posted for {result.Text("name")} · {result.Text("number")} · on hand {result["data"]?["stock_count"].Text("counted_quantity")}");
            }
        }
        finally
        {
            closed = true;
            reading?.Cancel();
        }
    }

    private static bool ReadCountValue(string value, int precision, decimal maximum, out decimal amount)
    {
        value = value.Trim();
        int separator = value.IndexOf('.');
        return decimal.TryParse(value, NumberStyles.AllowDecimalPoint, CultureInfo.InvariantCulture, out amount)
            && amount <= maximum && (separator < 0 || value.Length - separator - 1 <= precision);
    }
}
