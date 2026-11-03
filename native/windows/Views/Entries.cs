using ApexBooks_Windows.Services;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media.Imaging;
using System.Net.Http;
using System.Text.Json.Nodes;
using Windows.Storage.Streams;
using static ApexBooks_Windows.Views.NativeUi;

namespace ApexBooks_Windows;

public sealed partial class MainPage
{
    private async Task CompanyForm(bool edit = false)
    {
        var original = Company.Copy().Object(); var panel = Stack(); panel.MinWidth = 440;
        var name = Input("Company legal name", edit ? original.Text("name") : "");
        var bookLabel=Input("Book label · optional",edit?original.Text("book_label"):"");bookLabel.MaxLength=80;bookLabel.IsEnabled=Supports("company_book_labels");
        var mode = Select("Tax registration", [("unregistered", "Not GST registered"), ("regular", "GST registered · regular"), ("composition", "GST registered · composition")], edit ? original.Text("tax_mode") : "unregistered"); mode.IsEnabled = !edit;
        var gstin = Input("GSTIN · required for regular GST", edit ? original.Text("gstin") : ""); gstin.MaxLength = 15;
        var state = Input("State code", edit ? original.Text("state_code") : ""); state.MaxLength = 2;
        var address = Input("Address", edit ? original.Text("address") : "", true);
        foreach (var control in new UIElement[] { name, mode, gstin, state, address }) panel.Children.Add(control);if(Supports("company_book_labels"))panel.Children.Insert(1,bookLabel);
        panel.Children.Add(Text("Book labels distinguish workspaces in the company picker/search only; they do not change the legal name printed on invoices or tax documents.",12));if(!Supports("company_book_labels"))panel.Children.Add(CapabilityNotice());
        panel.Children.Add(Text("Each company keeps separate books. Choose the tax mode carefully; it cannot be changed here after creation.",12));
        string Signature()=>new JsonObject{["name"]=name.Text,["book_label"]=bookLabel.Text,["mode"]=Value(mode),["gstin"]=gstin.Text,["state"]=state.Text,["address"]=address.Text}.ToJsonString();var baseline=Signature();
        var saved = await Dialog(edit ? "Edit company details" : "Create company", panel, async () =>
        {
            if (string.IsNullOrWhiteSpace(name.Text)) throw new Exception("Enter a company name.");
            Api.Capabilities.RequireBookLabelSupported(edit?original.Text("book_label"):"",bookLabel.Text);
            var body = new JsonObject { ["name"] = name.Text.Trim(), ["gstin"] = gstin.Text.Trim().ToUpperInvariant(), ["state_code"] = state.Text.Trim(), ["address"] = address.Text.Trim() };
            if(Supports("company_book_labels"))body["book_label"]=ClientCapabilities.BookLabel(bookLabel.Text);
            if (!edit) body["tax_mode"] = Value(mode);
            var response = await Api.Send(edit ? Api.CompanyPath(original.Text("id")) : "/api/companies", edit ? HttpMethod.Patch : HttpMethod.Post, body);
            CompanyId = response.Text("id");
        }, edit ? "Save details" : "Create company",hasChanges:()=>Signature()!=baseline);
        if (saved) await LoadCompanies();
    }

    private async Task MasterForm(string kind, JsonObject? existing = null)
    {
        var cid = CompanyId; var panel = Stack(); panel.MinWidth = 580;
        var data = existing?["data"].Copy().Object() ?? new JsonObject();var initialMasterData=data.Copy().Object();
        var revisionVerifiedAtOpen=Supports("master_edit_revisions");
        if(existing is not null&&!revisionVerifiedAtOpen){panel.Children.Add(Text("Editing this existing party or item is disabled until the server confirms master revision protection. Check features, then close and reopen this editor. Creating and viewing masters remains available.",12));panel.Children.Add(CapabilityNotice());}
        var name = Input(kind == "party" ? "Party name" : "Item name", existing.Text("name")); name.MaxLength=120;name.IsReadOnly = existing is not null; panel.Children.Add(name);
        var active=new CheckBox{Content="Active · available for new documents",IsChecked=WorkflowMasterValues.IsActive(existing),IsEnabled=Supports("master_lifecycle")};panel.Children.Add(active);if(!Api.Capabilities.HasCoreAdditions)panel.Children.Add(CapabilityNotice());panel.Children.Add(Text("Archiving removes this master from new-entry pickers without deleting its historical records. Reactivate here when needed.",12));
        var fields = new Dictionary<string, TextBox>(); ComboBox? partyType = null, itemType = null, treatment = null; CheckBox? tracked = null;
        if (kind == "party")
        {
            partyType = Select("Party type", [("both", "Customer and supplier"), ("customer", "Customer"), ("supplier", "Supplier")], data.Text("party_type") is { Length: > 0 } t ? t : "both");
            foreach (var (key, label) in new[] { ("phone", "Phone"), ("email", "Email"), ("gstin", "GSTIN"), ("address", "Billing address"), ("shipping_address", "Default shipping address") }) fields[key]=Input(label,data.Text(key),key is "address" or "shipping_address");
            fields["gstin"].MaxLength=15;fields["phone"].MaxLength=32;fields["address"].MaxLength=500;fields["shipping_address"].MaxLength=500;fields["shipping_address"].IsEnabled=Supports("party_shipping_address");
            panel.Children.Add(Columns(partyType,fields["phone"]));panel.Children.Add(Columns(fields["email"],fields["gstin"]));panel.Children.Add(fields["address"]);panel.Children.Add(fields["shipping_address"]);panel.Children.Add(Text("Blank shipping address falls back to billing when selecting this party. Document addresses stay editable.",12));
            fields["credit_limit"]=Input("Customer credit limit (₹) · blank disables",data.Text("credit_limit"));fields["credit_limit"].MaxLength=32;fields["credit_limit"].IsEnabled=Supports("party_credit_limits");panel.Children.Add(fields["credit_limit"]);panel.Children.Add(Text("Warning only, based on receivables less available credits and advances. Zero is a valid limit; it does not block saving.",12));
            fields["payment_terms_days"]=Input("Payment terms · days (blank disables)",data.Text("payment_terms_days"));fields["payment_terms_days"].IsEnabled=Supports("party_payment_terms");panel.Children.Add(fields["payment_terms_days"]);panel.Children.Add(Text("0 means due on the document date. Due dates are suggested for review, never silently replaced.",12));
        }
        else
        {
            itemType = Select("Item type", [("goods", "Goods"), ("services", "Services")], data.Text("item_type") is { Length: > 0 } t ? t : "goods");
            foreach (var (key, label) in new[] { ("barcode", "Barcode"), ("hsn", "HSN / SAC"), ("unit", "Unit"), ("sale_rate", "Sale rate (₹)"), ("purchase_rate", "Purchase rate (₹)"), ("gst_rate", "GST rate (%)") }) fields[key]=Input(label,data.Text(key));
            fields["hsn"].MaxLength=16;fields["unit"].MaxLength=24;
            panel.Children.Add(Columns(itemType,fields["barcode"]));panel.Children.Add(Columns(fields["hsn"],fields["unit"]));panel.Children.Add(Columns(fields["sale_rate"],fields["purchase_rate"],fields["gst_rate"]));
            treatment = Select("GST treatment", [("taxable", "Taxable"), ("nil_rated", "Nil rated"), ("exempt", "Exempt"), ("non_gst", "Non-GST supply")], data.Text("tax_treatment") is { Length: > 0 } value ? value : Company.Text("tax_mode") == "regular" ? "taxable" : "nil_rated"); panel.Children.Add(treatment);
            fields["low_stock_threshold"]=Input("Low-stock threshold · quantity (blank disables)",data.Text("low_stock_threshold"));fields["low_stock_threshold"].IsEnabled=Supports("low_stock_reorder");panel.Children.Add(fields["low_stock_threshold"]);panel.Children.Add(Text("Reorder suggestions apply only to stock-tracked goods. Review quantities before creating a purchase order draft.",12));
            tracked = new CheckBox { Content = "Track stock quantities", IsChecked = data.Flag("track_stock"), IsEnabled = existing is null }; panel.Children.Add(tracked);
            var preview = new Image { MaxWidth = 180, MaxHeight = 120, HorizontalAlignment = HorizontalAlignment.Left };
            if (data.Text("image_thumbnail").Length > 0) preview.Source = await Bitmap(data.Text("image_thumbnail")); panel.Children.Add(preview);
            var buttons = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 10 };
            buttons.Children.Add(AsyncButton("Choose item image", async () =>
            {
                var file = await ApexFiles.Pick(".png", ".jpg", ".jpeg", ".webp"); if (file is null) return;
                var full = await ApexFiles.Image(file); var thumb = await ApexFiles.Image(file, 160, 15000); data["image_data_url"] = full; data["image_thumbnail"] = thumb; preview.Source = await Bitmap(thumb);
            }, Error));
            buttons.Children.Add(Button("Remove image", () => { data["image_data_url"] = ""; data["image_thumbnail"] = ""; preview.Source = null; })); panel.Children.Add(buttons);
        }
        string Signature(){var values=data.Copy().Object();values["name"]=name.Text;values["is_active"]=active.IsChecked==true;foreach(var field in fields)values[field.Key]=field.Value.Text;if(partyType is not null)values["party_type"]=Value(partyType);if(itemType is not null)values["item_type"]=Value(itemType);if(treatment is not null)values["tax_treatment"]=Value(treatment);if(tracked is not null)values["track_stock"]=tracked.IsChecked==true;return values.ToJsonString();}var baseline=Signature();
        var saved = await Dialog((existing is null ? "New " : "Edit ") + kind, panel, async () =>
        {
            if (string.IsNullOrWhiteSpace(name.Text)) throw new Exception("Enter a name.");
            Api.Capabilities.RequireMasterEditsSupported(initialMasterData,JsonNode.Parse(Signature()).Object());
            foreach (var (key, field) in fields) data[key] = field.Text.Trim();
            data["is_active"]=active.IsChecked==true;
            if(kind=="party"){if(Supports("party_payment_terms"))data["payment_terms_days"]=WorkflowMasterValues.PaymentTerms(fields["payment_terms_days"].Text);if(Supports("party_credit_limits"))data["credit_limit"]=WorkflowMasterValues.CreditLimit(fields["credit_limit"].Text);}
            else if(Supports("low_stock_reorder"))data["low_stock_threshold"]=WorkflowMasterValues.LowStockThreshold(fields["low_stock_threshold"].Text);
            if (partyType is not null) data["party_type"] = Value(partyType);
            if (itemType is not null) data["item_type"] = Value(itemType);
            if (treatment is not null) data["tax_treatment"] = Value(treatment);
            if (tracked is not null) data["track_stock"] = tracked.IsChecked == true;
            if (kind == "item") foreach (var key in new[] { "sale_rate", "purchase_rate", "gst_rate" }) if (data.Text(key).Length == 0) data[key] = "0";
            if(existing is null)await Api.Send(Api.CompanyPath(cid,"/records"),HttpMethod.Post,new JsonObject{["kind"]=kind,["name"]=name.Text.Trim(),["date"]=J.Today,["data"]=data.Copy()});
            else await Api.SaveMaster(cid,existing.Text("id"),initialMasterData,data,name.Text);
        },canSave:()=>existing is null||revisionVerifiedAtOpen&&Supports("master_edit_revisions"),hasChanges:()=>Signature()!=baseline);
        if (saved && cid == CompanyId) await Refresh();
    }

    internal static async Task<BitmapImage?> Bitmap(string uri)
    {
        if (!uri.StartsWith("data:image/") || !uri.Contains(',')) return null;
        var bytes = Convert.FromBase64String(uri.Split(',', 2)[1]); using var stream = new InMemoryRandomAccessStream();
        using (var writer = new DataWriter(stream.GetOutputStreamAt(0))) { writer.WriteBytes(bytes); await writer.StoreAsync(); writer.DetachStream(); }
        stream.Seek(0); var bitmap = new BitmapImage(); await bitmap.SetSourceAsync(stream); return bitmap;
    }

    private ComboBox ItemChoice(string label = "Item") => Select(label, Records.OfType<JsonObject>().Where(r => r.Text("kind") == "item").Select(r => (r.Text("id"), r.Text("name"))));
    private ComboBox BankChoice(string label = "Bank account", string selected = "default") => Select(label, Banks.OfType<JsonObject>().Select(r => (r.Text("id"), r.Text("name"))), selected);
    private async Task StockOpening()
    {
        var cid = CompanyId; var panel = Stack(); panel.MinWidth = 420; var item = ItemChoice(); var date = new DateInput("As of date", J.Today); var quantity = Input("Opening quantity"); var cost = Input("Cost per unit (₹)");var key=Guid.NewGuid().ToString();
        foreach (var field in new UIElement[] { item, date.View, quantity, cost }) panel.Children.Add(field);
        if (await Dialog("Opening stock", panel, async () => { await Api.Send(Api.CompanyPath(cid, "/stock/opening"), HttpMethod.Post, new JsonObject { ["item_id"] = Value(item), ["date"] = date.Value, ["quantity"] = quantity.Text, ["unit_cost"] = cost.Text }, key); }, "Post opening")) await Refresh();
    }
    private async Task StockAdjust()
    {
        var cid = CompanyId; var panel = Stack(); var item = ItemChoice(); var date = new DateInput("Date", J.Today); var direction = Select("Adjustment", [("increase", "Increase stock"), ("decrease", "Decrease stock")]); var quantity = Input("Quantity"); var cost = Input("Unit cost for an increase (₹)"); var reason = Input("Reason", "", true); var key = Guid.NewGuid().ToString();
        foreach (var field in new UIElement[] { item, date.View, direction, quantity, cost, reason }) panel.Children.Add(field);
        if (await Dialog("Stock adjustment", panel, async () => { var body = new JsonObject { ["item_id"] = Value(item), ["date"] = date.Value, ["direction"] = Value(direction), ["quantity"] = quantity.Text, ["reason"] = reason.Text }; if (cost.Text.Length > 0) body["unit_cost"] = cost.Text; await Api.Send(Api.CompanyPath(cid, "/stock/adjustments"), HttpMethod.Post, body, key); }, "Post adjustment")) await Refresh();
    }
}
