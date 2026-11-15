using ApexBooks_Windows.Services;
using ApexBooks_Windows.Views;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Input;
using Microsoft.UI.Xaml.Markup;
using Microsoft.UI.Xaml.Media;
using System.Globalization;
using System.Net.Http;
using System.Text.Json.Nodes;
using Windows.System;
using static ApexBooks_Windows.Views.NativeUi;

namespace ApexBooks_Windows;

public sealed partial class MainPage
{
    private Task PosPage()
    {
        var cid = CompanyId;
        var stamp = generation;
        var regular = Company.Text("tax_mode") == "regular";
        var strictStock = Supports("pos_require_available_stock");
        var splitSupported = Supports("pos_split_tender");
        var thermalSupported = Supports("thermal_receipts");
        var registerSupported = Supports("pos_register_sessions");
        var stockSupported = Supports("pos_stock_summary");
        var items = Records.OfType<JsonObject>()
            .Where(row => row.Text("kind") == "item" && WorkflowMasterValues.IsActive(row))
            .OrderBy(row => row.Text("name"), StringComparer.OrdinalIgnoreCase).ToArray();
        posDrafts.TryGetValue(cid, out var draft);
        var saved = draft?.Body["data"].Object() ?? new JsonObject();
        var submission = draft?.Submission ?? new RetrySubmission();
        var key = draft?.Key ?? Guid.NewGuid().ToString();
        var lines = new List<PosCartLine>();
        var posting = false;
        var initializing = true;
        var fillingBuyer = false;
        var lastShippingDefault = "";
        JsonNode? quote = null;
        var quoteDate = "";
        CancellationTokenSource? quoteRequest = null;
        CancellationTokenSource? stockRequest = null;
        var bookStock = new Dictionary<string, decimal>(StringComparer.Ordinal);
        var stockLabels = new Dictionary<string, (TextBlock Label, Button Action, string Unit, string ProductName)>(StringComparer.Ordinal);
        bool stockLoading = stockSupported;
        bool Current() => stamp == generation && cid == CompanyId && Api.SignedIn;
        bool Editable() => Current() && CanWrite && !posting && !submission.Unresolved;

        var search = Input("Scan barcode or search");
        search.PlaceholderText = "Barcode, product name or HSN";
        AutomationProperties.SetName(search, "Search products / scan barcode");
        AutomationProperties.SetAutomationId(search, "PosProductSearch");
        var scanStatus = Text("", 12);
        scanStatus.Foreground = Muted;
        var products = new ItemsControl
        {
            ItemsPanel = (ItemsPanelTemplate)XamlReader.Load(
                "<ItemsPanelTemplate xmlns='http://schemas.microsoft.com/winfx/2006/xaml/presentation'><ItemsWrapGrid Orientation='Horizontal'/></ItemsPanelTemplate>"),
        };
        var catalog = Stack(14);
        catalog.Children.Add(Text("Products", 21, true));
        catalog.Children.Add(search);
        catalog.Children.Add(scanStatus);
        catalog.Children.Add(new ScrollViewer
        {
            Content = products, MaxHeight = 510,
            VerticalScrollBarVisibility = ScrollBarVisibility.Auto,
            HorizontalScrollBarVisibility = ScrollBarVisibility.Disabled,
        });
        var catalogHost = StretchHost(Card(catalog));
        catalogHost.VerticalAlignment = VerticalAlignment.Top;

        var customer = Input("Customer name", draft?.Body.Text("name") ?? "Walk-in customer");
        var address = Input("Billing address", saved.Text("party_address"));
        var shipping = Input("Shipping address", saved.Text("shipping_address"), true);
        var phone = Input("Phone", saved.Text("party_phone"));
        var gstin = Input("GSTIN", saved.Text("party_gstin"));
        var supply = Input("Place of supply · state code",
            saved.Text("place_of_supply") is { Length: > 0 } state ? state : Company.Text("state_code"));
        var buyer = Select("Saved customer", new[] { ("", "Walk-in / entered customer") }
            .Concat(Records.Where(row => row.Text("kind") == "party" && WorkflowMasterValues.IsActive(row))
                .Select(row => (row.Text("id"), row.Text("name")))), saved.Text("party_id"));
        var billing = Stack(10);
        billing.Children.Add(buyer);
        billing.Children.Add(customer);
        billing.Children.Add(ResponsiveGrid(150, phone, gstin));
        if (regular) billing.Children.Add(supply);
        billing.Children.Add(address);
        billing.Children.Add(shipping);
        var buyerPanel = new Expander
        {
            Header = customer.Text,
            Content = billing,
            HorizontalAlignment = HorizontalAlignment.Stretch,
            HorizontalContentAlignment = HorizontalAlignment.Stretch,
        };

        var cart = Stack(8);
        var cartTitle = Text("Current sale", 22, true);
        var itemCount = Text("0 items", 12);
        itemCount.Foreground = Muted;
        itemCount.HorizontalAlignment = HorizontalAlignment.Right;
        itemCount.VerticalAlignment = VerticalAlignment.Center;
        var empty = Text("Scan a barcode or select a product.", 14);
        empty.Foreground = Muted;
        empty.Margin = new Thickness(0, 8, 0, 8);
        var cartFields = Stack(10);
        cartFields.Children.Add(Pair(cartTitle, itemCount));
        cartFields.Children.Add(empty);
        cartFields.Children.Add(new ScrollViewer
        {
            Content = cart, MaxHeight = 370,
            VerticalScrollBarVisibility = ScrollBarVisibility.Auto,
            HorizontalScrollBarVisibility = ScrollBarVisibility.Disabled,
        });
        cartFields.Children.Add(buyerPanel);
        var cartCard = Card(cartFields);
        cartCard.Padding = new Thickness(16);
        var cartHost = StretchHost(cartCard);

        var methods = new List<(string, string)> { ("cash", "Cash"), ("bank", "Bank / UPI / card") };
        if (splitSupported) methods.Add(("split", "Cash + bank / UPI / card"));
        var method = Select("Payment method", methods, saved.Text("payment_account"));
        var bank = BankChoice("Settlement account", saved.Text("bank_account_id"));
        var bankAmount = Input("Paid by bank / UPI / card (₹)", saved.Text("bank_amount"));
        var tender = Input("Cash received (₹)", saved.Text("tender_amount"));
        tender.PlaceholderText = "Exact amount";
        var bankConfirmed = new CheckBox { Content = "Bank, UPI or card payment confirmed" };
        var round = new CheckBox { Content = "Round to nearest rupee", IsChecked = saved.Flag("round_total") };
        billing.Children.Add(round);
        AutomationProperties.SetName(buyerPanel, "Customer and bill options");
        var tenderFields = Stack(8);
        tenderFields.Children.Add(bank);
        tenderFields.Children.Add(bankAmount);
        tenderFields.Children.Add(tender);
        tenderFields.Children.Add(bankConfirmed);
        var paymentFields = Stack(10);
        paymentFields.Children.Add(ResponsiveGrid(168, method, tenderFields));
        var paymentHost = StretchHost(paymentFields);

        var totalLabel = Text("Total due", 13, true);
        totalLabel.Foreground = Green;
        var total = Text("—", 28, true);
        total.Foreground = Green;
        total.TextAlignment = TextAlignment.Right;
        AutomationProperties.SetAutomationId(total, "PosTotalDue");
        var subtotal = Text("", 13);
        subtotal.Foreground = Muted;
        var tenderResult = Text("", 14, true);
        tenderResult.TextAlignment = TextAlignment.Right;
        tenderResult.MaxWidth = 190;
        var amountLabels = Stack(4);
        amountLabels.Children.Add(totalLabel);
        amountLabels.Children.Add(subtotal);
        var amountValues = Stack(3);
        amountValues.Children.Add(total);
        amountValues.Children.Add(tenderResult);
        var amountSummary = Pair(amountLabels, amountValues);
        var amountCard = new Border
        {
            Background = Brush(0xEC, 0xF8, 0xF1),
            BorderBrush = Brush(0xC6, 0xE7, 0xD3),
            BorderThickness = new Thickness(1),
            CornerRadius = new CornerRadius(8),
            Padding = new Thickness(12),
            Child = amountSummary,
        };
        var status = new InfoBar { IsClosable = false, Visibility = Visibility.Collapsed };
        var receipt = Stack(10);
        var save = Button("Complete sale", () => { }, true);
        save.HorizontalAlignment = HorizontalAlignment.Stretch;
        AutomationProperties.SetAutomationId(save, "PosCompleteSale");
        var checkoutFields = Stack(10);
        checkoutFields.Children.Add(amountCard);
        checkoutFields.Children.Add(paymentHost);
        checkoutFields.Children.Add(status);
        checkoutFields.Children.Add(save);
        checkoutFields.Children.Add(receipt);
        var checkout = Stack(12);
        var paymentCard = Card(checkoutFields);
        paymentCard.Padding = new Thickness(16);
        checkout.Children.Add(cartHost);
        checkout.Children.Add(paymentCard);

        var register = ResponsiveGrid(400, catalogHost, checkout);
        register.SizeChanged += (_, _) =>
        {
            if (register.ColumnDefinitions.Count != 2) return;
            register.ColumnDefinitions[0].Width = new GridLength(1.15, GridUnitType.Star);
            register.ColumnDefinitions[1].Width = new GridLength(1, GridUnitType.Star);
        };
        var posHost = StretchHost(register);

        JsonObject BodyValue(string date) => new()
        {
            ["kind"] = "pos",
            ["name"] = customer.Text.Trim() is { Length: > 0 } name ? name : "Walk-in customer",
            ["date"] = date,
            ["data"] = new JsonObject
            {
                ["lines"] = new JsonArray(lines.Select(row => (JsonNode)row.Data()).ToArray()),
                ["party_id"] = Value(buyer),
                ["party_address"] = address.Text,
                ["shipping_address"] = shipping.Text,
                ["party_phone"] = phone.Text,
                ["party_gstin"] = gstin.Text.Trim().ToUpperInvariant(),
                ["place_of_supply"] = supply.Text.Trim(),
                ["round_total"] = round.IsChecked == true,
            },
        };
        void SetStatus(InfoBarSeverity severity, string message)
        {
            status.Severity = severity;
            status.Message = message;
            status.IsOpen = message.Length > 0;
            status.Visibility = status.IsOpen ? Visibility.Visible : Visibility.Collapsed;
        }
        (bool Valid, string Message) VerifyPayment()
        {
            if (quote is null) return (false, "");
            var due = quote.Number("amount");
            if (due <= 0) return (false, "Sale total must be greater than zero.");
            var selected = Value(method);
            decimal cashDue = selected == "bank" ? 0 : due;
            if (selected != "cash" && Value(bank).Length == 0)
                return (false, "Choose a settlement account.");
            if (selected == "split")
            {
                if (!ReadPosMoney(bankAmount.Text, out var bankPaid) || bankPaid <= 0 || bankPaid >= due)
                    return (false, "Enter a bank amount smaller than the total due.");
                cashDue = due - bankPaid;
            }
            var cashPaid = cashDue;
            if (cashDue > 0 && tender.Text.Trim().Length > 0 && !ReadPosMoney(tender.Text, out cashPaid))
                return (false, "Enter cash received with up to two decimal places.");
            if (cashPaid < cashDue)
                return (false, $"Cash still due {J.Money(cashDue - cashPaid)}");
            if (selected != "cash" && bankConfirmed.IsChecked != true)
                return (false, "Confirm that the bank, UPI or card payment was received.");
            if (cashDue == 0) return (true, "Bank payment confirmed.");
            var change = J.Money(cashPaid - cashDue);
            return (true, selected == "split" ? $"Cash share {J.Money(cashDue)} · Change {change}" : $"Change {change}");
        }
        void UpdatePayment()
        {
            var selected = Value(method);
            bank.Visibility = bankConfirmed.Visibility = selected == "cash" ? Visibility.Collapsed : Visibility.Visible;
            bankAmount.Visibility = selected == "split" ? Visibility.Visible : Visibility.Collapsed;
            tender.Visibility = selected == "bank" ? Visibility.Collapsed : Visibility.Visible;
            var payment = VerifyPayment();
            tenderResult.Text = payment.Message;
            tenderResult.Foreground = payment.Valid ? Green : Muted;
            catalogHost.IsEnabled = cartHost.IsEnabled = paymentHost.IsEnabled = Editable();
            save.Visibility = CanWrite ? Visibility.Visible : Visibility.Collapsed;
            save.IsEnabled = Current() && CanWrite && !posting && (submission.Unresolved || payment.Valid);
            var label = posting ? "Posting sale…" : submission.Unresolved ? "Retry original sale" : "Complete sale";
            save.Content = new TextBlock { Text = label, TextWrapping = TextWrapping.Wrap, TextAlignment = TextAlignment.Center };
            AutomationProperties.SetName(save, label);
        }
        void ShowCart()
        {
            empty.Visibility = lines.Count == 0 ? Visibility.Visible : Visibility.Collapsed;
            itemCount.Text = $"{lines.Count} {(lines.Count == 1 ? "line" : "lines")}";
        }
        async Task Calculate()
        {
            if (initializing || submission.Unresolved || posting) return;
            quoteRequest?.Cancel();
            quote = null;
            bankConfirmed.IsChecked = false;
            ShowCart();
            foreach (var row in lines) row.RenderAmount(null);
            total.Text = "—";
            subtotal.Text = "";
            UpdatePayment();
            SetStatus(InfoBarSeverity.Informational, "");
            if (lines.Count == 0) return;
            if (lines.Any(row => !row.Ready))
            {
                SetStatus(InfoBarSeverity.Warning, "Enter a quantity and unit price for each line.");
                return;
            }
            using var request = new CancellationTokenSource();
            quoteRequest = request;
            var date = J.Today;
            var body = BodyValue(date);
            if (strictStock) body["data"]!["require_available_stock"] = true;
            subtotal.Text = "Calculating total…";
            try
            {
                await Task.Delay(180, request.Token);
                var result = await Api.Send(Api.CompanyPath(cid, "/documents/preview"), HttpMethod.Post, body, cancellation: request.Token);
                if (request.IsCancellationRequested || !Current()) return;
                quote = result;
                quoteDate = date;
                total.Text = J.Money(result.Number("amount"));
                var data = result["data"];
                var itemsTotal = data.Number("taxable");
                var tax = data.Number("cgst") + data.Number("sgst") + data.Number("igst");
                var rounding = data.Number("round_off");
                subtotal.Text = $"Subtotal {J.Money(itemsTotal)}"
                    + (tax > 0 ? $" · GST {J.Money(tax)}" : "")
                    + (rounding != 0 ? $" · Round off {J.Money(rounding)}" : "");
                var calculated = data?["lines"].Array() ?? new JsonArray();
                for (var index = 0; index < Math.Min(lines.Count, calculated.Count); index++)
                    lines[index].RenderAmount(calculated[index].Number("taxable") + calculated[index].Number("tax"));
                UpdatePayment();
            }
            catch (OperationCanceledException) when (request.IsCancellationRequested) { }
            catch (Exception error)
            {
                if (!request.IsCancellationRequested && Current())
                {
                    subtotal.Text = "";
                    SetStatus(InfoBarSeverity.Error, error.Message);
                }
            }
            finally
            {
                if (ReferenceEquals(quoteRequest, request)) quoteRequest = null;
            }
        }
        void ClearContact()
        {
            address.Text = "";
            if (shipping.Text == lastShippingDefault) shipping.Text = "";
            lastShippingDefault = "";
            phone.Text = gstin.Text = "";
            supply.Text = Company.Text("state_code");
        }
        buyer.SelectionChanged += (_, _) =>
        {
            if (fillingBuyer) return;
            fillingBuyer = true;
            try
            {
                var party = Records.FirstOrDefault(row => row.Text("id") == Value(buyer));
                if (party is null)
                {
                    customer.Text = "Walk-in customer";
                    ClearContact();
                    return;
                }
                customer.Text = party.Text("name");
                var data = party["data"];
                address.Text = data.Text("address");
                var delivery = Supports("party_shipping_address") ? WorkflowMasterValues.ShippingAddress(data) : address.Text;
                if (shipping.Text.Length == 0 || shipping.Text == lastShippingDefault) shipping.Text = delivery;
                lastShippingDefault = delivery;
                phone.Text = data.Text("phone");
                gstin.Text = data.Text("gstin");
                supply.Text = gstin.Text.Length >= 2 ? gstin.Text[..2] : Company.Text("state_code");
            }
            finally
            {
                fillingBuyer = false;
                buyerPanel.Header = customer.Text;
                _ = Calculate();
            }
        };
        customer.TextChanged += (_, _) =>
        {
            if (fillingBuyer) return;
            buyerPanel.Header = customer.Text.Trim() is { Length: > 0 } name ? name : "Walk-in customer";
            if (Value(buyer).Length > 0)
            {
                fillingBuyer = true;
                try { SelectValue(buyer, ""); ClearContact(); }
                finally { fillingBuyer = false; }
            }
            _ = Calculate();
        };
        foreach (var field in new[] { gstin, supply })
            field.TextChanged += (_, _) => { if (!fillingBuyer) _ = Calculate(); };
        round.Checked += (_, _) => _ = Calculate();
        round.Unchecked += (_, _) => _ = Calculate();
        foreach (var field in new[] { method, bank })
            field.SelectionChanged += (_, _) => { bankConfirmed.IsChecked = false; UpdatePayment(); };
        bankAmount.TextChanged += (_, _) => { bankConfirmed.IsChecked = false; UpdatePayment(); };
        tender.TextChanged += (_, _) => UpdatePayment();
        bankConfirmed.Checked += (_, _) => UpdatePayment();
        bankConfirmed.Unchecked += (_, _) => UpdatePayment();

        void Remove(PosCartLine row)
        {
            if (!Editable()) return;
            lines.Remove(row);
            cart.Children.Remove(row.View);
            _ = Calculate();
        }
        void LinkCartLine(JsonObject data)
        {
            var line = new PosCartLine(data, regular, Remove);
            lines.Add(line);
            cart.Children.Add(line.View);
            line.Changed += () => _ = Calculate();
        }
        void Add(JsonObject item)
        {
            if (!Editable()) return;
            var existing = lines.FirstOrDefault(row => row.ItemId == item.Text("id"));
            if (existing is not null) existing.SetQuantity(Math.Max(existing.Quantity, 0) + 1);
            else
            {
                var data = item["data"];
                var gst = regular ? data.Text("gst_rate") : "0";
                var classification = data.Text("tax_treatment");
                if (regular && data.Number("gst_rate") == 0 && classification is "" or "taxable") classification = "nil_rated";
                LinkCartLine(new JsonObject
                {
                    ["item_id"] = item.Text("id"), ["description"] = item.Text("name"),
                    ["quantity"] = "1", ["rate"] = data.Text("sale_rate"), ["gst_rate"] = gst,
                    ["tax_treatment"] = classification.Length == 0 ? "taxable" : classification,
                    ["hsn"] = data.Text("hsn"), ["unit"] = data.Text("unit"),
                });
                _ = Calculate();
            }
            receipt.Children.Clear();
            search.Text = "";
            scanStatus.Text = $"Added {item.Text("name")}";
            search.Focus(FocusState.Keyboard);
        }
        bool Matches(JsonObject item, string value) =>
            InventoryText.SearchText(item, InventorySetup)
                .Contains(value, StringComparison.OrdinalIgnoreCase);
        var productSequence = 0;
        async Task SetThumbnail(Image image, string value, int call)
        {
            try
            {
                var bitmap = await Bitmap(value);
                if (Current() && call == productSequence)
                {
                    image.Source = bitmap;
                    image.Visibility = Visibility.Visible;
                }
            }
            catch { /* A missing thumbnail must not block product selection. */ }
        }
        string StockCaption(string itemId, string unit) => stockLoading ? "Checking on hand…" :
            bookStock.TryGetValue(itemId, out var quantity)
                ? $"Book on hand {quantity.ToString("0.###", CultureInfo.InvariantCulture)} {unit}"
                : "On hand unavailable";
        void UpdateStockLabels()
        {
            foreach (var (id, row) in stockLabels)
            {
                row.Label.Text = StockCaption(id, row.Unit);
                AutomationProperties.SetName(row.Action, $"{row.ProductName} · {row.Label.Text}");
            }
        }
        void Products()
        {
            var call = ++productSequence;
            products.Items.Clear();
            stockLabels.Clear();
            var query = search.Text.Trim();
            var found = items.Where(row => Matches(row, query)).Take(37).ToArray();
            scanStatus.Text = found.Length switch
            {
                0 => query.Length == 0 ? "No active products in this company." : "No matching products.",
                > 36 => "Showing 36 products. Scan or search to narrow results.",
                _ => $"{found.Length} {(found.Length == 1 ? "product" : "products")}",
            };
            foreach (var item in found.Take(36))
            {
                var name = Text(item.Text("name"), 13, true);
                name.MaxLines = 2;
                name.TextTrimming = TextTrimming.CharacterEllipsis;
                var price = Text(J.Money(item["data"].Number("sale_rate")), 16, true);
                price.Foreground = Green;
                var labels = Stack(6);
                var thumbnail = item["data"].Text("image_thumbnail");
                if (thumbnail.Length > 0)
                {
                    var image = new Image { Height = 40, Stretch = Stretch.Uniform, Visibility = Visibility.Collapsed };
                    labels.Children.Add(image);
                    _ = SetThumbnail(image, thumbnail, call);
                }
                labels.Children.Add(name);
                labels.Children.Add(price);
                var where = InventoryText.LocationNames(InventorySetup, InventoryText.LocationIds(item["data"]));
                if (where.Count > 0)
                {
                    var place = Text("📍 " + string.Join(" · ", where), 12);
                    place.Foreground = Muted; place.MaxLines = 1; place.TextTrimming = TextTrimming.CharacterEllipsis;
                    labels.Children.Add(place);
                }
                var tracked = item["data"].Flag("track_stock");
                var button = Button("", () => Add(item));
                button.Content = labels;
                button.Width = 145;
                button.Height = (tracked && thumbnail.Length > 0 ? 140 : 118) + (where.Count > 0 ? 20 : 0);
                button.Margin = new Thickness(0, 0, 8, 8);
                button.Padding = new Thickness(10);
                button.HorizontalContentAlignment = HorizontalAlignment.Stretch;
                var productName = $"Add {item.Text("name")} · {price.Text}";
                if (tracked)
                {
                    var id = item.Text("id");
                    var unit = item["data"].Text("unit") is { Length: > 0 } stockUnit ? stockUnit : "units";
                    var stockLabel = Text(StockCaption(id, unit), 12);
                    stockLabel.Foreground = Muted;
                    stockLabel.MaxLines = 1;
                    stockLabel.TextTrimming = TextTrimming.CharacterEllipsis;
                    labels.Children.Add(stockLabel);
                    stockLabels[id] = (stockLabel, button, unit, productName);
                    AutomationProperties.SetName(button, $"{productName} · {stockLabel.Text}");
                }
                else AutomationProperties.SetName(button, productName);
                products.Items.Add(button);
            }
        }
        async Task RefreshOnHand()
        {
            if (!stockSupported || !Current()) return;
            stockRequest?.Cancel();
            using var request = new CancellationTokenSource();
            stockRequest = request;
            stockLoading = true;
            UpdateStockLabels();
            try
            {
                var result = await Api.Send(Api.CompanyPath(cid, "/pos/stock"), cancellation: request.Token);
                if (!Current() || request.IsCancellationRequested) return;
                var fresh = new Dictionary<string, decimal>(StringComparer.Ordinal);
                if (result.Text("date") == J.Today)
                {
                    foreach (var row in result["rows"].Array())
                    {
                        var id = row.Text("item_id");
                        if (id.Length > 0 && decimal.TryParse(row.Text("closing_quantity"), NumberStyles.Number,
                                CultureInfo.InvariantCulture, out var quantity))
                            fresh[id] = quantity;
                    }
                }
                bookStock = fresh;
            }
            catch (Exception)
            {
                if (Current() && !request.IsCancellationRequested) bookStock.Clear();
            }
            finally
            {
                if (ReferenceEquals(stockRequest, request))
                {
                    stockRequest = null;
                    stockLoading = false;
                    if (Current()) UpdateStockLabels();
                }
            }
        }
        search.TextChanged += (_, _) => Products();
        search.KeyDown += (_, e) =>
        {
            if (e.Key == VirtualKey.Escape)
            {
                search.Text = "";
                e.Handled = true;
            }
            if (e.Key != VirtualKey.Enter || !Editable()) return;
            e.Handled = true;
            var query = search.Text.Trim();
            if (query.Length == 0) return;
            var exactBarcode = items.Where(row => string.Equals(row["data"].Text("barcode"), query, StringComparison.OrdinalIgnoreCase)).ToArray();
            var exactName = items.Where(row => string.Equals(row.Text("name"), query, StringComparison.OrdinalIgnoreCase)).ToArray();
            var matches = exactBarcode.Length > 0 ? exactBarcode
                : exactName.Length > 0 ? exactName : items.Where(row => Matches(row, query)).Take(2).ToArray();
            if (matches.Length == 1) Add(matches[0]);
            else if (matches.Length > 1) scanStatus.Text = "Several products match. Select the correct product.";
            else scanStatus.Text = "No matching product. Check the barcode.";
        };
        var scanShortcut = new KeyboardAccelerator { Key = VirtualKey.F2 };
        scanShortcut.Invoked += (_, e) =>
        {
            if (Editable() && ReferenceEquals(posHost.Content, register))
            {
                search.Focus(FocusState.Keyboard);
                search.SelectAll();
                e.Handled = true;
            }
        };
        posHost.KeyboardAccelerators.Add(scanShortcut);
        ToolTipService.SetToolTip(search, "F2 focuses the scanner field. Enter adds an exact match.");

        var historyPanel = Stack();
        var historySearch = Input("Search sales history");
        historySearch.PlaceholderText = "Customer, receipt number or date";
        var historyRows = Stack();
        historyPanel.Children.Add(historySearch);
        historyPanel.Children.Add(historyRows);
        void DrawHistory()
        {
            historyRows.Children.Clear();
            var query = historySearch.Text.Trim();
            var sales = Records.OfType<JsonObject>()
                .Where(row => row.Text("kind") == "pos"
                    && $"{row.Text("name")} {row.Text("number")} {row.Text("date")}".Contains(query, StringComparison.OrdinalIgnoreCase))
                .OrderByDescending(row => row.Text("date"))
                .ThenByDescending(row => row["data"].Text("created_at")).ThenByDescending(row => row.Text("number")).ToArray();
            if (sales.Length == 0) historyRows.Children.Add(Card(Text("No receipts match this search.")));
            else AddRecordList(sales, historyRows);
        }
        historySearch.TextChanged += (_, _) => DrawHistory();
        var saleTab = Button("Checkout", () => { }, true);
        var historyTab = Button("Receipts", () => { });
        var accentStyle = saleTab.Style;
        var defaultStyle = historyTab.Style;
        saleTab.Click += (_, _) =>
        {
            historyTab.Style = defaultStyle;
            saleTab.Style = accentStyle;
            posHost.Content = register;
            if (Editable()) search.Focus(FocusState.Keyboard);
        };
        historyTab.Click += (_, _) =>
        {
            saleTab.Style = defaultStyle;
            historyTab.Style = accentStyle;
            DrawHistory();
            posHost.Content = historyPanel;
            historySearch.Focus(FocusState.Keyboard);
        };
        var tabs = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 8 };
        tabs.Children.Add(saleTab);
        tabs.Children.Add(historyTab);

        JsonObject SaleBody()
        {
            var body = BodyValue(quoteDate);
            var data = body["data"]!.AsObject();
            var selected = Value(method);
            data["payment_account"] = selected;
            if (selected != "cash") data["bank_account_id"] = Value(bank);
            if (selected == "split") data["bank_amount"] = bankAmount.Text.Trim();
            if (selected != "bank" && tender.Text.Trim().Length > 0) data["tender_amount"] = tender.Text.Trim();
            if (strictStock)
            {
                data["require_available_stock"] = true;
                data["expected_total"] = quote.Text("amount");
            }
            if (registerSupported && quote?["data"] is JsonObject quoteData && quoteData.ContainsKey("pos_register_session_id"))
                data["expected_register_session"] = quoteData["pos_register_session_id"].Copy();
            return body;
        }
        void ConfirmReceipt(JsonObject result)
        {
            receipt.Children.Clear();
            var summary = Stack(8);
            var confirmed = WorkflowMasterValues.IsPostedRecord(result);
            var heading = Text(confirmed ? "Sale completed" : "Receipt previously recorded", 16, true);
            heading.Foreground = Green;
            summary.Children.Add(heading);
            summary.Children.Add(Text($"{result.Text("number")} · {J.Money(result.Number("amount"))}"));
            var buttons = new List<UIElement>
            {
                AsyncButton("View / print receipt", () => PreviewDocument(result), Error),
            };
            if (thermalSupported)
                buttons.Add(AsyncButton("80 mm receipt", () => ShowDocumentPdf(result, "thermal_80"), Error));
            summary.Children.Add(ResponsiveGrid(145, buttons.ToArray()));
            receipt.Children.Add(Card(summary));
        }
        async Task Submit()
        {
            if (posting || !Current() || !CanWrite) return;
            if (!submission.Unresolved && !VerifyPayment().Valid) return;
            if (!submission.Unresolved && quoteDate != J.Today)
            {
                await Calculate();
                return;
            }
            SetStatus(InfoBarSeverity.Informational, "");
            var refreshQuote = false;
            posting = true;
            navigation.IsEnabled = saleTab.IsEnabled = historyTab.IsEnabled = false;
            UpdatePayment();
            try
            {
                var result = (await Api.SaveRecord(cid, submission.Body(SaleBody()), key)).Object();
                if (result.Text("kind") != "pos" || result.Text("id").Length == 0)
                    throw new ApiFailure(502, "The sale response did not include its receipt.");
                submission.Succeeded();
                posDrafts.Remove(cid);
                if (!Current()) return;
                lines.Clear();
                cart.Children.Clear();
                quote = null;
                quoteRequest?.Cancel();
                key = Guid.NewGuid().ToString();
                fillingBuyer = true;
                try
                {
                    SelectValue(buyer, "");
                    customer.Text = "Walk-in customer";
                    buyerPanel.Header = customer.Text;
                    ClearContact();
                    shipping.Text = "";
                }
                finally { fillingBuyer = false; }
                SelectValue(method, "cash");
                bankAmount.Text = tender.Text = "";
                bankConfirmed.IsChecked = false;
                total.Text = "—";
                subtotal.Text = "";
                ShowCart();
                ConfirmReceipt(result);
                _ = RefreshOnHand();
                try
                {
                    var updated = await Api.Records(cid);
                    if (Current()) Records = updated;
                }
                catch (Exception error) when (Current())
                {
                    SetStatus(InfoBarSeverity.Warning, $"Receipt saved. Refresh history to see the sale. {error.Message}");
                }
            }
            catch (Exception error)
            {
                if (Current())
                {
                    if (error is ApiFailure { Code: "POS_REQUOTE_REQUIRED" })
                    {
                        // Rejected before any write: clear the stale command and quote again with a new key.
                        submission.Succeeded();
                        key = Guid.NewGuid().ToString();
                        refreshQuote = true;
                        quote = null;
                    }
                    // Every other POS rejection is definitive: the server replays committed keys before validating.
                    else if (error is not ApiFailure { Status: 401 or 403 }) submission.Failed(error, definitiveConflict: true);
                    SetStatus(submission.Unresolved ? InfoBarSeverity.Warning : InfoBarSeverity.Error,
                        submission.Unresolved
                            ? "Sale confirmation was interrupted. Retry the original sale before collecting payment again."
                            : error.Message);
                }
            }
            finally
            {
                posting = false;
                if (Current())
                {
                    navigation.IsEnabled = saleTab.IsEnabled = historyTab.IsEnabled = true;
                    UpdatePayment();
                }
            }
            if (refreshQuote && Current()) await Calculate();
            if (Editable() && lines.Count == 0) search.Focus(FocusState.Keyboard);
        }
        save.Click += async (_, _) => await Submit();

        Body.Children.Add(tabs);
        Body.Children.Add(posHost);
        if (!CanWrite) SetStatus(InfoBarSeverity.Informational, "View-only access. Sales history is available.");
        foreach (var row in saved["lines"].Array().OfType<JsonObject>()) LinkCartLine(row);
        initializing = false;
        ShowCart();
        Products();
        _ = RefreshOnHand();
        UpdatePayment();
        if (submission.Unresolved)
            SetStatus(InfoBarSeverity.Warning, "Sale confirmation was interrupted. Retry the original sale before collecting payment again.");
        else if (lines.Count > 0) _ = Calculate();
        posHost.Loaded += (_, _) => { if (Editable()) search.Focus(FocusState.Keyboard); };

        hasUnsavedPage = () => lines.Count > 0 || submission.Unresolved;
        hasPendingPage = () => submission.Unresolved;
        leavePage = () =>
        {
            quoteRequest?.Cancel();
            stockRequest?.Cancel();
            if (lines.Count == 0 && !submission.Unresolved) posDrafts.Remove(cid);
            else
            {
                var body = SaleBody();
                body["data"]!["tender_amount"] = tender.Text;
                posDrafts[cid] = new PosDraft(body, key, submission);
            }
        };
        return Task.CompletedTask;
    }

    private static ContentControl StretchHost(UIElement child) => new()
    {
        Content = child,
        HorizontalAlignment = HorizontalAlignment.Stretch,
        HorizontalContentAlignment = HorizontalAlignment.Stretch,
    };

    private static Grid Pair(FrameworkElement heading, FrameworkElement right)
    {
        var grid = new Grid { ColumnSpacing = 10 };
        grid.ColumnDefinitions.Add(new ColumnDefinition());
        grid.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
        grid.Children.Add(heading);
        Grid.SetColumn(right, 1);
        grid.Children.Add(right);
        return grid;
    }

    private static bool ReadPosMoney(string text, out decimal amount)
    {
        text = text.Trim();
        var decimalPoint = text.IndexOf('.');
        return decimal.TryParse(text, NumberStyles.AllowDecimalPoint, CultureInfo.InvariantCulture, out amount)
            && amount <= 9_999_999_999_999.99m && (decimalPoint < 0 || text.Length - decimalPoint - 1 <= 2);
    }
}
