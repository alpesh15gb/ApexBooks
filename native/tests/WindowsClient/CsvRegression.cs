using ApexBooks_Windows.Services;
using System.Text;

static class CsvRegression
{
    static void Reject(Action action,string text){try{action();}catch(Exception e){if(e.Message.Contains(text))return;throw;}throw new Exception("CSV should reject: "+text);}
    public static void Run()
    {
        var valid=Csv.Parse(Csv.Decode(Encoding.UTF8.GetPreamble().Concat(Encoding.UTF8.GetBytes("name,phone\r\n\"A, B\n\"\"quoted\"\"\",00123\r\n")).ToArray()));
        if(valid[1][0]!="A, B\n\"quoted\""||valid[1][1]!="00123")throw new Exception("CSV quoted/BOM/text fidelity");
        Reject(()=>Csv.Parse("name\n\"A\"junk"),"row 2");
        Reject(()=>Csv.Parse("name\nA\"B"),"row 2");
        Reject(()=>Csv.Parse("name\n\"A"),"unclosed");
        Reject(()=>Csv.Decode(new byte[]{0x41,0x96,0x42}),"UTF-8");
        var supported=new HashSet<string>{"name","phone"};
        foreach(var input in new[]{"name,,phone\nA,lost data,00123","name,phone\nA,00123,extra","name,unknown\nA,lost","name,name\nA,B"})
        {var rows=Csv.Parse(input);Reject(()=>Csv.ValidateColumns(rows,rows[0],supported),input.StartsWith("name,name")?"unique":"row 2");}
        var blank=Csv.Parse("name,,phone\nA,,00123");Csv.ValidateColumns(blank,blank[0],supported);
        if(!Csv.Boolean("YES")||Csv.Boolean("no"))throw new Exception("CSV Boolean values");Reject(()=>Csv.Boolean("perhaps"),"track_stock");
        Console.WriteLine("CSV strict parsing, UTF-8, headers and Boolean regressions passed.");
    }
}
