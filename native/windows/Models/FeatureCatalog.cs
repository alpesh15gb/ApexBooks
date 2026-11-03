using System.Text.Json.Nodes;
using ApexBooks_Windows.Services;

namespace ApexBooks_Windows.Models;

public sealed record MenuFeature(string Key, string Title, string Group);
public sealed record ReportFeature(string Key, string Title, string Path, string Group, string Description);
public static class FeatureCatalog
{
    private static readonly JsonNode Source = JsonNode.Parse(File.ReadAllText(Path.Combine(AppContext.BaseDirectory, "Assets", "features.json")))!;
    public static readonly MenuFeature[] Navigation = Source["navigation"].Array().Select(r => new MenuFeature(r.Text("key"), r.Text("title"), r.Text("group"))).ToArray();
    public static readonly ReportFeature[] Reports = Source["reports"].Array().Select(r => new ReportFeature(r.Text("key"), r.Text("title"), r.Text("path"), r.Text("group"), r.Text("description"))).ToArray();
    public static readonly HashSet<string> Documents = Source["document_kinds"].Array().Select(r => r.Text()).ToHashSet();
    public static readonly HashSet<string> Drafts = Source["draft_kinds"].Array().Select(r => r.Text()).ToHashSet();
    public static string Singular(string key)=>key=="proforma"?"proforma invoice":key=="pos"?"POS sale":key.Replace('_',' ');
    public static string Title(string key) => Navigation.FirstOrDefault(r => r.Key == key)?.Title ?? key.Replace('_', ' ');
}

[Microsoft.UI.Xaml.Data.Bindable]
public sealed class RecordRow(JsonObject source)
{
    public System.Windows.Input.ICommand? EditCommand {get;set;}
    public System.Windows.Input.ICommand? PdfCommand {get;set;}
    public System.Windows.Input.ICommand? OpenCommand {get;set;}
    public Microsoft.UI.Xaml.Visibility PdfVisibility {get;set;}=Microsoft.UI.Xaml.Visibility.Collapsed;
    public JsonObject Source { get; } = source;
    public string Id => Source.Text("id");
    public string Kind => Source.Text("kind");
    public string Name => Source.Text("name");
    public string Reference => Source.Text("number") is { Length: > 0 } number ? number : Source["data"].Text("gstin");
    public string PrimaryText => Kind is "party" or "item" ? Name : Reference;
    public string SecondaryText => Kind == "party" ? Source["data"].Text("gstin") : Kind == "item" ? (Source["data"].Text("hsn") is {Length:>0} hsn ? "HSN / SAC " + hsn : Source["data"].Text("barcode")) : Name;
    public string Date => Source.Text("date");
    public string Category => FeatureCatalog.Title(Kind);
    public string Amount => Kind == "party" ? Source["data"].Text("phone") : Kind == "item" ? J.Money(Source["data"].Number("sale_rate")) : J.Money(Source.Number("amount"));
    public string Balance => Source["outstanding"] is not null ? "Due " + J.Money(Source.Number("outstanding")) : Source["credit_remaining"] is not null ? "Credit " + J.Money(Source.Number("credit_remaining")) : Source["advance_remaining"] is not null ? "Advance " + J.Money(Source.Number("advance_remaining")) : "";
    public string BalanceValue=>Source["outstanding"] is not null?J.Money(Source.Number("outstanding")):Balance;
    public string Status {
        get {
            if(Kind is "party" or "item")return WorkflowMasterValues.IsActive(Source)?"Active":"Archived";
            if(Source.Flag("cancelled"))return "Cancelled";
            if(Source.Text("converted_to").Length>0)return "Converted";
            if(!Source.Flag("posted"))return FeatureCatalog.Drafts.Contains(Kind)?"Draft":"";
            if(Source["data"].Flag("is_advance"))return Source.Number("advance_remaining")>0?"Advance available":"Advance settled";
            if(Kind is "credit_note" or "debit_note")return Source.Number("credit_remaining")>0?"Credit available":"Credit settled";
            if(Kind is "sales_invoice" or "purchase_bill" or "pos"&&Source["outstanding"] is not null)return Source.Number("outstanding")<=0?"Settled":Source.Number("outstanding")<Source.Number("amount")?"Part settled":"Unpaid";
            return "Posted";
        }
    }
    public Microsoft.UI.Xaml.Media.SolidColorBrush StatusBrush => new(Status switch { "Unpaid"=>Windows.UI.Color.FromArgb(255,166,100,24),"Part settled"=>Windows.UI.Color.FromArgb(255,50,104,161),"Draft"=>Windows.UI.Color.FromArgb(255,103,123,134),_=>Windows.UI.Color.FromArgb(255,18,124,102) });
    public override string ToString()=>$"{Name}, {Reference}, {Category}, {Date}, {Amount}, {Status}, {Balance}";
}
