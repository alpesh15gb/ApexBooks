using System.Globalization;
using System.Text.Json.Nodes;

namespace ApexBooks_Windows.Services;

public sealed class ClientCapabilities
{
    private static readonly HashSet<string> Known=["low_stock_reorder","party_price_history","party_payment_terms","master_lifecycle","party_shipping_address","party_credit_limits","recurring_drafts","company_book_labels","document_attachments","chunked_backups","master_edit_revisions","document_conversion_revisions","bank_match_revisions"];
    private readonly HashSet<string> features;
    private JsonObject limits=new();
    public string ApiVersion {get;private set;}="unknown";
    public string BuildRevision {get;private set;}="unknown";
    static string VersionLabel(string value)=>value.Length is >0 and <=64&&value.All(c=>char.IsAsciiLetterOrDigit(c)||c is '.' or '-' or '+')?value:"unknown";
    public long Limit(string name,long fallback,long maximum){var value=limits[name];return value is JsonValue json&&json.TryGetValue<long>(out var number)&&number>0?Math.Min(number,maximum):fallback;}
    public static ClientCapabilities Unavailable { get; }=new(false,[]);
    public static ClientCapabilities Checking { get; }=new(false,[],false,true);
    public static ClientCapabilities TransientFailure { get; }=new(false,[],true);
    private ClientCapabilities(bool valid,IEnumerable<string> supported,bool retryable=false,bool pending=false){Valid=valid;Retryable=retryable;Pending=pending;features=new(supported.Where(Known.Contains),StringComparer.Ordinal);}
    public bool Valid { get; }
    public bool Retryable { get; }
    public bool Pending { get; }
    public string Hint=>Pending?"Checking optional server features… Core accounting is ready independently.":Retryable?"Unable to check features. Core accounting remains available. Retry the feature check when your connection is available.":UpgradeHint;
    public bool Supports(string feature)=>Valid&&features.Contains(feature);
    public bool HasCoreAdditions=>new[]{"low_stock_reorder","party_price_history","party_payment_terms","master_lifecycle","party_shipping_address","party_credit_limits","recurring_drafts"}.All(Supports);
    public const string UpgradeHint="This server has not confirmed support for this newer feature. Core accounting remains available; upgrade the API and sign in again to refresh capabilities.";
    public static ClientCapabilities Parse(JsonNode? payload)
    {
        if(payload is not JsonObject obj||obj["capabilities_version"] is not JsonValue version||!version.TryGetValue<int>(out var value)||value!=1||obj["supported_features"] is not JsonArray list)return Unavailable;
        var features=new List<string>();foreach(var item in list){if(item is not JsonValue entry||!entry.TryGetValue<string>(out var name))return Unavailable;features.Add(name);}return new(true,features){ApiVersion=VersionLabel(obj.Text("api_version")),BuildRevision=BuildIdentity.Normalize(obj.Text("build_revision")),limits=obj["limits"] is JsonObject bounds?(JsonObject)bounds.DeepClone():new()};
    }
    public void RequireBankMatchRevisionSupport()
    {
        if(!Supports("bank_match_revisions"))throw new InvalidOperationException(Hint+" Exact unmatch requires verified bank match revision protection. No unmatch was submitted.");
    }
    public void RequireDocumentConversionSupport()
    {
        if(!Supports("document_conversion_revisions"))throw new InvalidOperationException(Hint+" Converting documents requires verified source revision protection. This conversion was not submitted.");
    }
    public void RequireMasterRevisionSupport()
    {
        if(!Supports("master_edit_revisions"))throw new InvalidOperationException(Hint+" Editing existing parties and items requires verified master revision support. Your edits were not submitted.");
    }
    public void RequireMasterEditsSupported(JsonObject original,JsonObject candidate)
    {
        foreach(var (field,feature) in new[]{("low_stock_threshold","low_stock_reorder"),("payment_terms_days","party_payment_terms"),("is_active","master_lifecycle"),("shipping_address","party_shipping_address"),("credit_limit","party_credit_limits")}){
            if(Supports(feature))continue;
            var changed=field=="is_active"?(original[field] is null||original.Flag(field))!=(candidate[field] is null||candidate.Flag(field)):original.Text(field).Trim()!=candidate.Text(field).Trim();
            if(changed)throw new InvalidOperationException(Hint+" Your entered "+field.Replace('_',' ')+" was not saved.");
        }
    }
    public void RequireBookLabelSupported(string original,string candidate){if(!Supports("company_book_labels")&&original.Trim()!=candidate.Trim())throw new InvalidOperationException(Hint+" Your entered book label was not saved.");}
    public JsonObject MasterData(JsonObject original)
    {
        var copy=(JsonObject)original.DeepClone();
        foreach(var (field,feature) in new[]{("low_stock_threshold","low_stock_reorder"),("payment_terms_days","party_payment_terms"),("is_active","master_lifecycle"),("shipping_address","party_shipping_address"),("credit_limit","party_credit_limits")})if(!Supports(feature))copy.Remove(field);
        return copy;
    }
    public static string CompanyLabel(JsonNode? company)=>company.Text("name")+(company.Text("book_label").Trim() is {Length:>0} label?" · "+label:"");
    public static string BookLabel(string value){value=value.Trim();if(value.Length>80)throw new FormatException("Book label must be at most 80 characters.");return value;}
}

public static class BusinessCalendar
{
    public static DateTime IndiaDate(DateTimeOffset instant)=>instant.ToOffset(TimeSpan.FromMinutes(330)).Date;
    public static DateTime Today=>IndiaDate(DateTimeOffset.UtcNow);
    public static string FinancialStart(DateTimeOffset instant){var date=IndiaDate(instant);return $"{(date.Month>=4?date.Year:date.Year-1)}-04-01";}
}
