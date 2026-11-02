using System.Globalization;
using System.Text;

namespace ApexBooks_Windows.Services;
public static class Csv
{
    public static List<string[]> Parse(string text)
    {
        var rows=new List<string[]>();var row=new List<string>();var cell=new StringBuilder();var quoted=false;
        for(var i=0;i<text.Length;i++)
        {
            var c=text[i];if(c=='"'){if(quoted&&i+1<text.Length&&text[i+1]=='"'){cell.Append('"');i++;}else quoted=!quoted;}
            else if(c==','&&!quoted){row.Add(cell.ToString().Trim());cell.Clear();}
            else if((c=='\r'||c=='\n')&&!quoted){if(c=='\r'&&i+1<text.Length&&text[i+1]=='\n')i++;row.Add(cell.ToString().Trim());cell.Clear();if(row.Any(s=>s.Length>0))rows.Add(row.ToArray());row.Clear();}
            else cell.Append(c);
        }
        if(quoted)throw new Exception("The CSV contains an unclosed quoted field.");row.Add(cell.ToString().Trim());if(row.Any(s=>s.Length>0))rows.Add(row.ToArray());if(rows.Count>5001)throw new Exception("Import at most 5,000 transactions at a time.");if(rows.Count>0&&rows[0].Length>0)rows[0][0]=rows[0][0].TrimStart('\uFEFF');return rows;
    }
    public static string Money(string text)
    {
        if(string.IsNullOrWhiteSpace(text)||text.Trim()=="-")return "0";
        var clean=text.Trim().Replace(",","").Replace("₹","").Replace("INR","",StringComparison.OrdinalIgnoreCase);var negative=clean.StartsWith('(')&&clean.EndsWith(')')||clean.EndsWith("Dr",StringComparison.OrdinalIgnoreCase);clean=clean.Trim('(',')');if(clean.EndsWith("Dr",StringComparison.OrdinalIgnoreCase)||clean.EndsWith("Cr",StringComparison.OrdinalIgnoreCase))clean=clean[..^2].Trim();
        if(!decimal.TryParse(clean,NumberStyles.AllowLeadingSign|NumberStyles.AllowDecimalPoint,CultureInfo.InvariantCulture,out var value))throw new Exception("Invalid amount: "+text);if(negative)value=-Math.Abs(value);return value.ToString(CultureInfo.InvariantCulture);
    }
}
