using System.Collections;
using System.Globalization;
using System.Text.Json.Nodes;
using ApexBooks_Windows.Services;

static class MonthChartAggregationTests
{
    // Deliberately retain the old algorithm as an independent equivalence oracle.
    static List<(DateTime Month,decimal Sales,decimal Purchases)> Reference(IEnumerable<JsonNode?> source,DateTime start,DateTime end)
    {
        var rows=new List<(DateTime Month,decimal Sales,decimal Purchases)>();
        for(var m=new DateTime(start.Year,start.Month,1);m<=end&&rows.Count<13;m=m.AddMonths(1)){
            var key=m.ToString("yyyy-MM");var records=source.OfType<JsonObject>().Where(r=>r.Flag("posted")&&r.Text("date").StartsWith(key)&&string.CompareOrdinal(r.Text("date"),start.ToString("yyyy-MM-dd"))>=0&&string.CompareOrdinal(r.Text("date"),end.ToString("yyyy-MM-dd"))<=0).ToArray();
            rows.Add((m,records.Sum(r=>r.Text("kind") is "sales_invoice" or "pos"?r.Number("amount"):r.Text("kind")=="credit_note"?-r.Number("amount"):0),records.Sum(r=>r.Text("kind")=="purchase_bill"?r.Number("amount"):r.Text("kind")=="debit_note"?-r.Number("amount"):0)));
        }
        return rows;
    }
    static bool Same(List<(DateTime Month,decimal Sales,decimal Purchases)> expected,List<(DateTime Month,decimal Sales,decimal Purchases)> actual)=>expected.Count==actual.Count&&expected.Zip(actual).All(pair=>pair.First.Month==pair.Second.Month&&decimal.GetBits(pair.First.Sales).SequenceEqual(decimal.GetBits(pair.Second.Sales))&&decimal.GetBits(pair.First.Purchases).SequenceEqual(decimal.GetBits(pair.Second.Purchases)));
    public static void Run(Action<bool,string> check)
    {
        var rows=new List<JsonNode?>();var kinds=new[]{"sales_invoice","pos","credit_note","purchase_bill","debit_note","expense","payment_in","estimate","party"};
        for(var i=0;i<50000;i++){
            var date=new DateTime(2024,1,1).AddDays(i%1110).ToString("yyyy-MM-dd",CultureInfo.InvariantCulture);
            if(i%101==0)date="";else if(i%137==0)date+="T12:30:00";
            rows.Add(new JsonObject{["kind"]=kinds[i%kinds.Length],["date"]=date,["posted"]=i%7!=0,["amount"]=(i%19==0?0m:(i%10001-5000)/100m).ToString(CultureInfo.InvariantCulture)});
        }
        rows.Add(null);rows.Add(JsonValue.Create("not a record"));
        var periods=new[]{(new DateTime(2024,1,1),new DateTime(2024,12,31)),(new DateTime(2025,11,17),new DateTime(2026,2,9)),(new DateTime(2024,2,28),new DateTime(2024,3,2)),(new DateTime(2024,1,1),new DateTime(2026,12,31)),(new DateTime(2025,4,20),new DateTime(2025,4,10)),(new DateTime(2026,4,1),new DateTime(2025,4,1))};
        foreach(var (start,end) in periods){
            var counted=new CountedRows(rows);var actual=MonthChartAggregation.Aggregate(counted,start,end);var expected=Reference(rows,start,end);
            check(Same(expected,actual),$"chart50k equivalence including decimal bits {start:yyyy-MM-dd} through {end:yyyy-MM-dd}");
            check(counted.Enumerations==(actual.Count==0?0:1)&&counted.Visits==(actual.Count==0?0:rows.Count),"chart scans input at most once without per-month enumeration");
        }
        var empty=MonthChartAggregation.Aggregate(Array.Empty<JsonNode?>(),new DateTime(2025,11,1),new DateTime(2026,2,28));check(empty.Count==4&&empty.All(row=>row.Sales==0&&row.Purchases==0),"empty chart retains ordered zero months across year boundary");
        check(MonthChartAggregation.Aggregate(rows,new DateTime(2024,1,1),new DateTime(2026,12,31)).Count==13,"chart month cap remains13");
        var precision=new List<JsonNode?>();foreach(var amount in new[]{decimal.MaxValue,-decimal.MaxValue,0.0000000000000000000000000001m,0m})precision.Add(new JsonObject{["kind"]="sales_invoice",["posted"]=true,["date"]="2025-01-15",["amount"]=amount.ToString(CultureInfo.InvariantCulture)});
        precision.Add(new JsonObject{["kind"]="expense",["posted"]=true,["date"]="2025-01-15",["amount"]="12"});
        check(Same(Reference(precision,new(2025,1,1),new(2025,1,31)),MonthChartAggregation.Aggregate(precision,new(2025,1,1),new(2025,1,31))),"chart preserves decimal addition order and zero contributions");
    }
    sealed class CountedRows(IEnumerable<JsonNode?> rows):IEnumerable<JsonNode?>
    {
        public int Enumerations,Visits;
        public IEnumerator<JsonNode?> GetEnumerator(){if(++Enumerations>1)throw new InvalidOperationException("Repeated chart scan");foreach(var row in rows){Visits++;yield return row;}}
        IEnumerator IEnumerable.GetEnumerator()=>GetEnumerator();
    }
}
