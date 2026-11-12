using System.Text.Json.Nodes;
namespace ApexBooks_Windows.Services;

public static class SourceLineChoices
{
    public static List<(string Key,string Label)> Build(IEnumerable<JsonObject> lines,string selected,string number)
    {
        var rows=lines.Where(row=>row.Text("source_line_id").Length>0).ToList();
        var choices=new List<(string,string)>();
        if(selected.Length==0)choices.Add(("","Choose source line or match item/description"));
        choices.AddRange(rows.Select(row=>(row.Text("source_line_id"),$"Line {row.Text("source_line_number")} · {row.Text("description")} · source qty {row.Text("quantity")} · additional return qty {(row.Text("remaining_return_quantity").Length>0?row.Text("remaining_return_quantity"):"needs review")} · GST {row.Text("gst_rate")}% · {row.Text("itc_treatment")}")));
        if(selected.Length>0&&!rows.Any(row=>row.Text("source_line_id")==selected))choices.Add((selected,"Saved source line "+number));
        return choices;
    }
}
