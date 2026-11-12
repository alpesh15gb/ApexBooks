using System.Globalization;
using System.Text;

namespace ApexBooks_Windows.Services;
public static class Csv
{
    public static string Decode(byte[] bytes)
    {
        try { return new UTF8Encoding(false,true).GetString(bytes); }
        catch(DecoderFallbackException) { throw new Exception("CSV encoding is invalid. Save the file as UTF-8 and try again."); }
    }
    public static List<string[]> Parse(string text)
    {
        text=text.TrimStart('\uFEFF');
        var rows=new List<string[]>();var row=new List<string>();var cell=new StringBuilder();var quoted=false;var closed=false;var line=1;
        void Cell(){row.Add(cell.ToString().Trim());cell.Clear();closed=false;}
        void Row(){Cell();if(row.Any(s=>s.Length>0))rows.Add(row.ToArray());row.Clear();}
        for(var i=0;i<text.Length;i++)
        {
            var c=text[i];
            if(quoted){if(c=='"'){if(i+1<text.Length&&text[i+1]=='"'){cell.Append('"');i++;}else{quoted=false;closed=true;}}else{cell.Append(c);if(c=='\n')line++;}continue;}
            if(c==','){Cell();continue;}
            if(c=='\r'||c=='\n'){if(c=='\r'&&i+1<text.Length&&text[i+1]=='\n')i++;Row();line++;continue;}
            if(closed){if(c==' '||c=='\t')continue;throw new Exception($"CSV row {line}: unexpected text after a closing quote.");}
            if(c=='"'){if(cell.Length>0)throw new Exception($"CSV row {line}: quote must begin a field.");quoted=true;}else cell.Append(c);
        }
        if(quoted)throw new Exception($"CSV row {line}: unclosed quoted field.");Row();
        if(rows.Count>5001)throw new Exception("Import at most 5,000 transactions at a time.");return rows;
    }
    public static void ValidateColumns(List<string[]> table,string[] headers,HashSet<string> supported)
    {
        if(headers.Where(h=>h.Length>0).Distinct().Count()!=headers.Count(h=>h.Length>0))throw new Exception("CSV headers must be unique.");
        for(var i=1;i<table.Count;i++)for(var j=0;j<table[i].Length;j++)
            if(table[i][j].Length>0&&(j>=headers.Length||headers[j].Length==0||!supported.Contains(headers[j])))
                throw new Exception($"CSV row {i+1}, column {j+1}: populated column has no supported header.");
    }
    public static bool Boolean(string value) => value.Trim().ToLowerInvariant() switch {
        "true" or "1" or "yes" => true, "" or "false" or "0" or "no" => false,
        _ => throw new Exception("CSV track_stock must be true/false, yes/no or 1/0.")
    };
    public static string Money(string text)
    {
        if(string.IsNullOrWhiteSpace(text)||text.Trim()=="-")return "0";
        var clean=text.Trim().Replace(",","").Replace("₹","").Replace("INR","",StringComparison.OrdinalIgnoreCase);var negative=clean.StartsWith('(')&&clean.EndsWith(')')||clean.EndsWith("Dr",StringComparison.OrdinalIgnoreCase);clean=clean.Trim('(',')');if(clean.EndsWith("Dr",StringComparison.OrdinalIgnoreCase)||clean.EndsWith("Cr",StringComparison.OrdinalIgnoreCase))clean=clean[..^2].Trim();
        if(!decimal.TryParse(clean,NumberStyles.AllowLeadingSign|NumberStyles.AllowDecimalPoint,CultureInfo.InvariantCulture,out var value))throw new Exception("Invalid amount: "+text);if(negative)value=-Math.Abs(value);return value.ToString(CultureInfo.InvariantCulture);
    }
}
