using System.Text.Json.Nodes;

namespace ApexBooks_Windows.Services;

/// <summary>WhatsApp share and payment-reminder text, matching the web and Android wording. Nothing is sent until the user presses send.</summary>
public static class WhatsAppShare
{
    private static readonly Dictionary<string,string> Titles=new(){["sales_invoice"]="Invoice",["pos"]="Bill",["estimate"]="Estimate",["proforma"]="Proforma invoice",["sales_order"]="Sales order",["credit_note"]="Credit note",["payment_in"]="Payment receipt",["purchase_order"]="Purchase order"};
    public static bool Shareable(string kind)=>Titles.ContainsKey(kind);
    public static bool CanRemind(JsonObject row)=>row.Text("kind") is "sales_invoice" or "pos"&&row.Flag("posted")&&!row.Flag("cancelled")&&row.Number("outstanding")>0;

    public static string PartyPhone(JsonObject row,IEnumerable<JsonObject> records)
    {
        var id=row["data"].Text("party_id");
        var party=records.FirstOrDefault(r=>r.Text("kind")=="party"&&(id.Length>0?r.Text("id")==id:string.Equals(r.Text("name").Trim(),row.Text("name").Trim(),StringComparison.OrdinalIgnoreCase)));
        var phone=party?["data"].Text("phone")??"";
        if(!string.IsNullOrWhiteSpace(phone))return phone;
        return row["data"].Text("phone") is {Length:>0} legacy?legacy:row["data"].Text("party_phone");
    }

    public static string Phone(string value)
    {
        var digits=new string(value.Where(char.IsDigit).ToArray()).TrimStart('0');
        return digits.Length==10?"91"+digits:digits.Length is >=11 and <=15?digits:"";
    }

    public static string DocumentMessage(JsonObject row,string company,string upi)
    {
        var data=row["data"];var lines=new List<string>{$"Dear {Name(row)},",$"{Titles.GetValueOrDefault(row.Text("kind"),"Document")} {row.Text("number")} dated {row.Text("date")} for {J.Money(row.Number("amount"))} from {company}."};
        if(row.Text("kind") is "sales_invoice" or "pos"&&row.Flag("posted"))
        {
            var due=row.Number("outstanding");
            lines.Add(due>0?$"Balance due: {J.Money(due)}"+(data.Text("due_date") is {Length:>0} d?$" by {d}":"")+".":"Fully paid. Thank you!");
            if(due>0&&upi.Length>0)lines.Add("Pay by UPI: "+upi);
        }
        lines.Add("Thank you for your business.");return string.Join("\n",lines);
    }

    public static string ReminderMessage(JsonObject row,string company,string upi,string today)
    {
        var due=row["data"].Text("due_date");var overdue=due.Length>0&&string.CompareOrdinal(due,today)<0;
        var lines=new List<string>{$"Dear {Name(row)},",$"This is a gentle reminder that {J.Money(row.Number("outstanding"))} is {(overdue?"overdue since "+due:"pending")} against {Titles.GetValueOrDefault(row.Text("kind"),"invoice")} {row.Text("number")} dated {row.Text("date")}."};
        if(upi.Length>0)lines.Add("You can pay by UPI: "+upi);
        lines.Add("Please ignore if already paid.\n– "+company);return string.Join("\n",lines);
    }

    public static Uri Url(string phone,string text)=>new("https://wa.me/"+Phone(phone)+"?text="+Uri.EscapeDataString(text));
    private static string Name(JsonObject row)=>row.Text("name") is {Length:>0} n?n:"Customer";

    public sealed record OverdueGroup(string Name,string Phone,List<JsonObject> Invoices,decimal Total);
    /// <summary>"Remind all overdue": one group per customer, largest overdue balance first.</summary>
    public static List<OverdueGroup> OverdueByParty(JsonArray records,string today)
    {
        var rows=records.OfType<JsonObject>().ToList();
        string PhoneFor(JsonObject invoice)=>PartyPhone(invoice,rows);
        return rows.Where(r=>CanRemind(r)&&r["data"].Text("due_date") is {Length:>0} due&&string.CompareOrdinal(due,today)<0)
            .GroupBy(r=>r.Text("name").Trim().ToLowerInvariant())
            .Select(g=>new OverdueGroup(g.First().Text("name"),g.Select(PhoneFor).FirstOrDefault(p=>p.Length>0)??"",g.ToList(),g.Sum(r=>r.Number("outstanding"))))
            .OrderByDescending(g=>g.Total).ToList();
    }
    public static string PartyReminderMessage(OverdueGroup group,string company,string upi)
    {
        var lines=new List<string>{$"Dear {(group.Name.Length>0?group.Name:"Customer")},",$"This is a gentle reminder that {J.Money(group.Total)} is overdue:"};
        foreach(var invoice in group.Invoices)lines.Add($"• {Titles.GetValueOrDefault(invoice.Text("kind"),"Invoice")} {invoice.Text("number")} dated {invoice.Text("date")}: {J.Money(invoice.Number("outstanding"))} (due {invoice["data"].Text("due_date")})");
        if(upi.Length>0)lines.Add("You can pay by UPI: "+upi);
        lines.Add("Please ignore if already paid.\n– "+company);return string.Join("\n",lines);
    }
}
