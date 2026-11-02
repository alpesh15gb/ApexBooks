using System.Text.Json.Nodes;

namespace ApexBooks_Windows.Services;

/// <summary>The API returns fixed discounts alongside a zero percent field. Preserve the
/// explicit fixed field on reopen; never derive or prorate it from quantity or totals.</summary>
public sealed class LineDiscountState
{
    public string Mode {get;private set;}
    public string Value {get;set;}
    public LineDiscountState(JsonObject? line){Mode=line?.ContainsKey("discount_amount")==true?"amount":"percent";Value=line.Text(Mode=="amount"?"discount_amount":"discount_percent") is {Length:>0} value?value:"0";}
    public void Select(string mode){if(mode is not ("amount" or "percent"))throw new ArgumentException("Choose percent or fixed rupee discount.",nameof(mode));if(mode==Mode)return;Mode=mode;Value="0";}
    public void WriteTo(JsonObject line){line.Remove("discount_amount");line.Remove("discount_percent");line[Mode=="amount"?"discount_amount":"discount_percent"]=Value.Trim().Length>0?Value.Trim():"0";}
}

/// <summary>Review is tied to monotonic UI revisions, so changing quantity/discount and
/// changing it back never silently restores an earlier acknowledgement.</summary>
public sealed class FixedDiscountReview
{
    string? reviewed;
    public void Acknowledge(string signature)=>reviewed=signature;
    public void Clear()=>reviewed=null;
    public bool IsAcknowledged(string signature)=>reviewed==signature;
    public static bool Needed(bool linkedReturn,IEnumerable<JsonObject> lines)=>linkedReturn&&lines.Any(line=>line.ContainsKey("discount_amount")&&line.Number("discount_amount")>0);
}
