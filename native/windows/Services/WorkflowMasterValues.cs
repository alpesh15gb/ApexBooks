using System.Globalization;
using System.Text.Json.Nodes;
using System.Text.RegularExpressions;

namespace ApexBooks_Windows.Services;

/// <summary>Optional master defaults are validated before any request; the API remains authoritative.</summary>
public static class WorkflowMasterValues
{
    public static JsonNode? PaymentTerms(string text)
    {
        text=text.Trim();if(text.Length==0)return null;
        if(Regex.IsMatch(text,"^[0-9]+$")&&int.TryParse(text,NumberStyles.None,CultureInfo.InvariantCulture,out var days)&&days<=3650)return JsonValue.Create(days);
        throw new FormatException("Payment terms must be a whole number from 0 to 3650 days, or blank.");
    }
    public static JsonNode? LowStockThreshold(string text)
    {
        text=text.Trim();if(text.Length==0)return null;
        if(Regex.IsMatch(text,"^[0-9]+(\\.[0-9]{1,3})?$")&&decimal.TryParse(text,NumberStyles.AllowDecimalPoint,CultureInfo.InvariantCulture,out var quantity)&&quantity<=999999999999.999m)return JsonValue.Create(text);
        throw new FormatException("Low-stock threshold must be nonnegative, at most 999999999999.999 and have no more than 3 decimal places.");
    }
}
