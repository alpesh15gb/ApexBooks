using ApexBooks_Windows.Services;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using System.Globalization;
using System.Net.Http;
using System.Text.Json.Nodes;
using static ApexBooks_Windows.Views.NativeUi;

namespace ApexBooks_Windows;
public sealed partial class MainPage
{
    private async Task ImportStatement(string bank)
    {
        var cid=CompanyId;var access=CaptureFileSaveAccess();var file=await ApexFiles.Pick(".csv");if(file is null||!ScopedFileExport.Current(access))return;var bytes=await ApexFiles.Read(file,5_000_000);if(!ScopedFileExport.Current(access))return;var table=Csv.Parse(Csv.Decode(bytes));if(table.Count<2)throw new Exception("The statement needs a header and transaction rows.");
        var panel=Stack(14);panel.MinWidth=780;panel.Children.Add(Text(file.Name,18,true));panel.Children.Add(Text("Use UTF-8 comma-separated CSV. Quoted commas and line breaks are supported; convert tab or semicolon files before importing."));var header=new NumberBox{Header="Header row number",Minimum=1,Maximum=table.Count-1,Value=1,SpinButtonPlacementMode=NumberBoxSpinButtonPlacementMode.Compact};var format=Select("Date format",[("dd/MM/yyyy","DD/MM/YYYY"),("yyyy-MM-dd","YYYY-MM-DD"),("MM/dd/yyyy","MM/DD/YYYY"),("dd-MM-yyyy","DD-MM-YYYY"),("dd-MMM-yyyy","DD-MMM-YYYY")]);var fields=new Dictionary<string,ComboBox>();var mapping=Stack();var preview=Stack();string reviewed="";bool validating=false,closed=false;int revision=0;
        void Verify(){access();if(closed)throw new InvalidOperationException("This import view is closed.");}
        void Changed(){revision++;reviewed="";preview.Children.Clear();}
        var aliases=new Dictionary<string,string[]>{{"date",["date","transaction date","txn date","value date"]},{"description",["description","narration","particulars","transaction details"]},{"reference",["reference","ref","cheque/ref no","chq/ref no","utr"]},{"amount",["amount","signed amount"]},{"debit",["debit","withdrawal","withdrawals","debit amount"]},{"credit",["credit","deposit","deposits","credit amount"]}};
        void RebuildMapping(){Changed();if(!double.IsFinite(header.Value)||header.Value!=Math.Truncate(header.Value)||header.Value<1||header.Value>=table.Count)return;fields.Clear();mapping.Children.Clear();var names=table[(int)header.Value-1];foreach(var key in aliases.Keys){var auto=Array.FindIndex(names,n=>aliases[key].Contains(n.Trim().ToLowerInvariant()));var box=Select(Friendly(key)+" column",new[]{("","Not mapped")}.Concat(names.Select((n,i)=>(i.ToString(),$"{i+1}. {n}"))),auto<0?"":auto.ToString());fields[key]=box;box.SelectionChanged+=(_,_)=>Changed();mapping.Children.Add(box);}reviewed="";preview.Children.Clear();}
        format.SelectionChanged+=(_,_)=>Changed();header.ValueChanged+=(_,_)=>RebuildMapping();RebuildMapping();
        JsonObject Build()
        {
            Verify();if(!double.IsFinite(header.Value)||header.Value!=Math.Truncate(header.Value)||header.Value<1||header.Value>=table.Count)throw new Exception("Choose a whole header row number within this file.");var output=new JsonArray();var start=(int)header.Value;
            if(Value(fields["date"]).Length==0||Value(fields["description"]).Length==0||Value(fields["amount"]).Length==0&&(Value(fields["debit"]).Length==0||Value(fields["credit"]).Length==0))throw new Exception("Map date, description, and either signed amount or debit and credit.");
            for(var i=start;i<table.Count;i++)
            {
                var cells=table[i];string Get(string key)=>int.TryParse(Value(fields[key]),out var col)&&col<cells.Length?cells[col]:"";
                try{if(!DateTime.TryParseExact(Get("date"),Value(format),CultureInfo.InvariantCulture,DateTimeStyles.None,out var date))throw new Exception("Date does not match the selected format.");var amount=Value(fields["amount"]).Length>0?Csv.Money(Get("amount")):"";if(amount.Length==0){var debit=decimal.Parse(Csv.Money(Get("debit")),CultureInfo.InvariantCulture);var credit=decimal.Parse(Csv.Money(Get("credit")),CultureInfo.InvariantCulture);if(debit<0||credit<0||debit>0&&credit>0)throw new Exception("Use one positive debit or credit.");amount=(credit-debit).ToString(CultureInfo.InvariantCulture);}if(decimal.Parse(amount,CultureInfo.InvariantCulture)==0)throw new Exception("Amount is zero.");if(Get("description").Length==0)throw new Exception("Description is empty.");output.Add(new JsonObject{["date"]=date.ToString("yyyy-MM-dd"),["description"]=Get("description"),["reference"]=Get("reference"),["amount"]=amount});}
                catch(Exception e){throw new Exception($"CSV row {i+1}: {e.Message}");}
            }
            return new JsonObject{["bank_account_id"]=bank,["lines"]=output};
        }
        panel.Children.Add(Columns(header,format));panel.Children.Add(new Expander{Header="Column mapping",Content=mapping,HorizontalContentAlignment=HorizontalAlignment.Stretch,IsExpanded=true,HorizontalAlignment=HorizontalAlignment.Stretch});panel.Children.Add(AsyncButton("Validate and preview",async()=>{if(validating)return;validating=true;var stamp=revision;try{await ScopedFileExport.Run(Verify,async()=>{var body=Build();var dry=body.DeepClone().AsObject();dry["dry_run"]=true;var report=await Api.Send(Api.CompanyPath(cid,"/bank-statement/import"),HttpMethod.Post,dry);Verify();if(stamp!=revision)return false;reviewed=body.ToJsonString();preview.Children.Clear();RenderReport(preview,report,"Import validation");Table(preview,new JsonArray(body["lines"].Array().Take(10).Select(r=>r.Copy()).ToArray()),"First 10 rows");return true;});}catch(Exception)when(stamp!=revision){}finally{validating=false;}},Error,true));panel.Children.Add(preview);
        try{await Dialog("Import bank statement",panel,async()=>{if(validating)throw new Exception("Wait for validation to finish before importing.");var body=Build();if(body.ToJsonString()!=reviewed)throw new Exception("Validate this mapping and review the preview before importing.");await Api.Send(Api.CompanyPath(cid,"/bank-statement/import"),HttpMethod.Post,body);},"Import reviewed rows");}finally{closed=true;}
    }
}
