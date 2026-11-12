using System.Globalization;
using System.Text.Json.Nodes;
using System.Text.RegularExpressions;

namespace ApexBooks_Windows.Services;

/// <summary>Optional master defaults are validated before any request; the API remains authoritative.</summary>
public static class WorkflowMasterValues
{
    /// <summary>Only active postings contribute to financial summaries; optional as-of bounds exclude future entries.</summary>
    public static bool IsPostedRecord(JsonNode? row,string? asOf=null)=>row.Flag("posted")&&!row.Flag("cancelled")&&(asOf is null||row.Text("date").Length>0&&string.CompareOrdinal(row.Text("date"),asOf)<=0);
    public static bool IsActive(JsonNode? row)=>row?["data"]?["is_active"] is null || row["data"].Flag("is_active");
    public static string ShippingAddress(JsonNode? data)=>data.Text("shipping_address") is {Length:>0} delivery?delivery:data.Text("address");
    public static int RecurringInterval(string text)
    {
        if(int.TryParse(text.Trim(),NumberStyles.None,CultureInfo.InvariantCulture,out var value)&&value is >=1 and <=12)return value;
        throw new FormatException("Recurring interval must be a whole number from 1 to 12.");
    }
    public static bool RecurringOccurrenceAllowed(bool active,string nextDue,string today)=>active&&DateOnly.TryParseExact(nextDue,"yyyy-MM-dd",CultureInfo.InvariantCulture,DateTimeStyles.None,out var due)&&DateOnly.TryParseExact(today,"yyyy-MM-dd",CultureInfo.InvariantCulture,DateTimeStyles.None,out var now)&&due<=now;
    public static void RecurringWriteFailed(RetrySubmission submission,Exception error)
    {
        // This API serializes writes and checks replay before version/schedule conditions.
        // Its received 409 is a definitive non-commit, not an in-progress response.
        if(error is ApiFailure{Status:409})submission.Succeeded();else submission.Failed(error);
    }
    public static JsonNode? CreditLimit(string text)
    {
        text=text.Trim();if(text.Length==0)return null;
        if(Regex.IsMatch(text,"^[0-9]+(\\.[0-9]+)?$")&&decimal.TryParse(text,NumberStyles.AllowDecimalPoint,CultureInfo.InvariantCulture,out var amount)&&amount<=9999999999999.99m&&decimal.Round(amount,2)==amount)return JsonValue.Create(amount.ToString("0.##",CultureInfo.InvariantCulture));
        throw new FormatException("Credit limit must be nonnegative, at most 9999999999999.99 with no more than 2 meaningful decimal places, or blank to disable.");
    }
    public static bool CreditProjectionApplies(string kind,bool amendment)=>!amendment&&kind is "sales_invoice" or "estimate" or "proforma" or "sales_order";
    public static string CreditStatusText(JsonNode status,bool projected)
    {
        var basis=$"Net customer exposure as of {status.Text("as_of")}: receivables less available customer credits and advances.";
        if(status["credit_limit"] is null)return basis+$" Current exposure {J.Money(status.Number("current_exposure"))}. No credit limit configured. Informational only; not credit approval.";
        return basis+$" Limit {J.Money(status.Number("credit_limit"))} · exposure {J.Money(status.Number("current_exposure"))}"+(projected?$" · proposed {J.Money(status.Number("proposed_amount"))} · projected {J.Money(status.Number("projected_exposure"))}":"")+$" · remaining {J.Money(status.Number("remaining_credit"))}. "+(status.Flag("exceeded")?"Credit limit exceeded. ":"")+"Warning only; saving is not blocked and this is not credit approval.";
    }
    public static JsonNode? PaymentTerms(string text)
    {
        text=text.Trim();if(text.Length==0)return null;
        if(Regex.IsMatch(text,"^[0-9]+$")&&int.TryParse(text,NumberStyles.None,CultureInfo.InvariantCulture,out var days)&&days<=3650)return JsonValue.Create(days);
        throw new FormatException("Payment terms must be a whole number from 0 to 3650 days, or blank.");
    }
    public static JsonNode? LowStockThreshold(string text)
    {
        text=text.Trim();if(text.Length==0)return null;
        if(Regex.IsMatch(text,"^[0-9]+(\\.[0-9]+)?$")&&decimal.TryParse(text,NumberStyles.AllowDecimalPoint,CultureInfo.InvariantCulture,out var quantity)&&quantity<=999999999999.999m&&decimal.Round(quantity,3)==quantity)return JsonValue.Create(quantity.ToString("0.###",CultureInfo.InvariantCulture));
        throw new FormatException("Low-stock threshold must be nonnegative, at most 999999999999.999 and have no more than 3 decimal places.");
    }
}
