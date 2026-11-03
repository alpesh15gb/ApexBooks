using System.Text.Json.Nodes;

namespace ApexBooks_Windows.Services;

/// <summary>Pure chart buckets; never caches or publishes partial company data.</summary>
public static class MonthChartAggregation
{
    public static List<(DateTime Month,decimal Sales,decimal Purchases)> Aggregate(IEnumerable<JsonNode?> records,DateTime start,DateTime end)
    {
        var rows=new List<(DateTime Month,decimal Sales,decimal Purchases)>();
        var months=new Dictionary<string,int>(StringComparer.Ordinal);
        // Preserve original month ordering, zero buckets and13-month cap, even
        // when reversed bounds fall within the same calendar month.
        for(var month=new DateTime(start.Year,start.Month,1);month<=end&&rows.Count<13;month=month.AddMonths(1)){
            months.Add(month.ToString("yyyy-MM"),rows.Count);rows.Add((month,0m,0m));
        }
        if(rows.Count==0)return rows;
        var lower=start.ToString("yyyy-MM-dd");var upper=end.ToString("yyyy-MM-dd");
        foreach(var node in records){
            if(node is not JsonObject record||!record.Flag("posted"))continue;
            var date=record.Text("date");
            if(date.Length<7||string.CompareOrdinal(date,lower)<0||string.CompareOrdinal(date,upper)>0||!months.TryGetValue(date[..7],out var index))continue;
            var kind=record.Text("kind");var amount=kind is "sales_invoice" or "pos" or "credit_note" or "purchase_bill" or "debit_note"?record.Number("amount"):0m;
            var sales=kind is "sales_invoice" or "pos"?amount:kind=="credit_note"?-amount:0m;
            var purchases=kind=="purchase_bill"?amount:kind=="debit_note"?-amount:0m;
            var previous=rows[index];
            // Add both contributions, including zeros, in input order so decimal
            // precision/scale follows the original per-month LINQ sums.
            rows[index]=(previous.Month,previous.Sales+sales,previous.Purchases+purchases);
        }
        return rows;
    }
}
