using ApexBooks_Windows.Models;
using ApexBooks_Windows.Services;
using ApexBooks_Windows.Views;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml.Media.Imaging;
using Microsoft.UI.Xaml.Printing;
using System.Text.Json.Nodes;
using Windows.Data.Pdf;
using Windows.Graphics.Printing;
using Windows.Storage.Streams;
using static ApexBooks_Windows.Views.NativeUi;

namespace ApexBooks_Windows;
public sealed partial class MainPage
{
    private async Task ReportsPage()
    {
        var cid=CompanyId;var stamp=generation;var exportAccess=CaptureFileSaveAccess();var sequence=0;
        void Library()
        {
            ++sequence;Body.Children.Clear();var search=Input("Find a report · sales, GST, stock, balances…");var group=Select("Report category",new[]{("all","All reports")}.Concat(FeatureCatalog.Reports.Select(r=>r.Group).Distinct().Select(g=>(g,g))));var list=Stack(14);
            void Draw(){list.Children.Clear();foreach(var report in FeatureCatalog.Reports.Where(r=>(r.Key!="statements"||Supports("financial_statements"))&&(Value(group)=="all"||r.Group==Value(group))&&(r.Title+" "+r.Description+" "+r.Group).Contains(search.Text.Trim(),StringComparison.OrdinalIgnoreCase))){var details=Stack(5);details.Children.Add(Text(report.Group.ToUpperInvariant(),11,true));details.Children.Add(Text(report.Title,19,true));details.Children.Add(Text(report.Description,13));var button=AsyncButton(report.Title,()=>Open(report),Error);button.Content=details;button.HorizontalAlignment=HorizontalAlignment.Stretch;button.HorizontalContentAlignment=HorizontalAlignment.Left;button.Padding=new Thickness(20);if(report.Key.StartsWith("gstr")&&Company.Text("tax_mode")!="regular"){button.IsEnabled=false;details.Children.Add(Text("Requires a regular GST-registered company",12));}list.Children.Add(button);}if(list.Children.Count==0)list.Children.Add(Card(Text("No reports match this search.")));}
            Body.Children.Add(Text("Report library",26,true));if(!Api.Capabilities.HasCoreAdditions)Body.Children.Add(CapabilityNotice());Body.Children.Add(FeatureButton("Low-stock & reorder suggestions","low_stock_reorder",ReorderReport,true));Body.Children.Add(FeatureButton("Recurring draft schedules","recurring_drafts",RecurringDrafts));Body.Children.Add(Text("Choose a report, set its period and export the same figures you review here."));Body.Children.Add(Columns(group,search));Body.Children.Add(list);search.TextChanged+=(_,_)=>Draw();group.SelectionChanged+=(_,_)=>Draw();Draw();
        }
        async Task Open(ReportFeature feature)
        {
            ++sequence;Body.Children.Clear();var key=feature.Key;var gst=key.StartsWith("gstr");var from=new DateInput("From",J.FinancialStart);var to=new DateInput("To / as of",J.Today);var period=new DateInput("Date within month / quarter",J.Today);var mode=Select("GST period",[("month","Full month"),("quarter","Full quarter"),("custom","Custom dates")]);var party=Input("Party filter · optional");var results=Stack(18);var actions=new StackPanel{Orientation=Orientation.Horizontal,Spacing=10};string ready="",filename="";JsonObject? loaded=null;Button? jsonExport=null;
            string Path(){var query=key is "ageing" or "credits" or "advances"?$"as_of={to.Value}":$"from_date={from.Value}&to_date={to.Value}";if(key is "parties" or "ageing")query+="&party="+Uri.EscapeDataString(party.Text);return Api.CompanyPath(cid,feature.Path+(feature.Path.Contains('?')?"&":"?")+query);}
            void Dates(){var custom=Value(mode)=="custom";period.View.Visibility=custom?Visibility.Collapsed:Visibility.Visible;from.View.Visibility=to.View.Visibility=custom?Visibility.Visible:Visibility.Collapsed;if(!custom){if(!DateTime.TryParseExact(period.Value,"yyyy-MM-dd",System.Globalization.CultureInfo.InvariantCulture,System.Globalization.DateTimeStyles.None,out var date))return;var months=Value(mode)=="quarter"?3:1;var first=new DateTime(date.Year,months==3?((date.Month-1)/3)*3+1:date.Month,1);from.Picker.Date=new DateTimeOffset(first);to.Picker.Date=new DateTimeOffset(first.AddMonths(months).AddDays(-1));}}
            async Task Load(){if(gst&&Value(mode)!="custom"&&period.Value.Length==0)throw new Exception("Choose a date within the GST month or quarter.");if(gst)Dates();var request=++sequence;var url=Path();ready="";loaded=null;if(jsonExport is not null)jsonExport.IsEnabled=false;results.Children.Clear();results.Children.Add(Text("Loading report…"));try{var data=await Api.Send(url);if(stamp!=generation||request!=sequence||!Body.Children.Contains(results))return;ready=url;loaded=data.Object();if(jsonExport is not null)jsonExport.IsEnabled=loaded["export_info"].Flag("json_available")==true;filename=(key=="gstr2a"?"gstr2a-purchase-books":gst?key+"-preparation":key)+"-"+from.Value+"-"+to.Value;results.Children.Clear();if(gst)RenderGstReport(results,loaded);else if(key=="statements"&&data["profit_loss"] is not null)RenderStatements(results,data.Object());else RenderReport(results,data);}catch{if(Body.Children.Contains(results)){results.Children.Clear();results.Children.Add(Card(Text("This report could not be loaded. Review the message and apply again.")));}throw;}}
            async Task Export(string format){if(gst&&Value(mode)!="custom"&&period.Value.Length==0)throw new Exception("Choose a date within the GST month or quarter.");if(gst)Dates();if(ready.Length==0||ready!=Path())throw new Exception("Apply the selected dates before exporting.");if(format=="json"&&loaded?["export_info"].Flag("json_available")!=true)throw new Exception("Resolve the preparation checks before exporting draft JSON.");var parts=ready.Split('?',2);await ScopedFileExport.Download(exportAccess,()=>Api.Download(parts[0]+"."+format+"?"+parts[1]),null,async(bytes,verify)=>{if(stamp!=generation||cid!=CompanyId||!Body.Children.Contains(results))return false;if(format=="pdf"){await ShowPdf(bytes,filename+".pdf",originalAccess:verify);return true;}return await ApexFiles.Save(bytes,filename+"."+format,verify);});}
            var back=Button("← Report library",Library);Body.Children.Add(back);Body.Children.Add(Text(feature.Title,26,true));Body.Children.Add(Text(feature.Description));var controls=Stack();if(gst){controls.Children.Add(Columns(mode,period.View));mode.SelectionChanged+=(_,_)=>Dates();period.Picker.DateChanged+=(_,_)=>Dates();Dates();}controls.Children.Add(Columns(from.View,to.View));if(key is "parties" or "ageing")controls.Children.Add(party);actions.Children.Add(AsyncButton("Apply period",Load,Error,true));actions.Children.Add(AsyncButton("PDF / print",()=>Export("pdf"),Error));actions.Children.Add(AsyncButton("Export XLSX",()=>Export("xlsx"),Error));if(key=="gstr1"){jsonExport=AsyncButton("Draft JSON",()=>Export("json"),Error);jsonExport.IsEnabled=false;actions.Children.Add(jsonExport);}var reportActions=actions.Children.Cast<UIElement>().ToArray();actions.Children.Clear();controls.Children.Add(ResponsiveGrid(170,reportActions));Body.Children.Add(Card(controls));Body.Children.Add(results);await Load();
        }
        Library();await Task.CompletedTask;
    }

    private static void RenderGstReport(Panel panel,JsonObject data)
    {
        decimal Total(string field)=>data[field].Object().Sum(p=>p.Value.Number());AddMetrics(panel,("Output GST",Total("output")),("Input from entered bills",Total("book_itc")),("Estimated cash payable",data.Number("cash_total")));
        var info=data["export_info"].Object();var checks=Stack();checks.Children.Add(Text("Export format and preparation checks",19,true));checks.Children.Add(Text(data.Text("standard")=="GSTR-1"?"GSTN "+info.Text("template")+" worksheets. Review XLSX or draft JSON in the current offline tool before upload.":data.Text("standard")=="GSTR-2A"?"Purchase-book reconciliation. Supplier filing details must come from portal GSTR-2A.":"Numbered 3B schedules. External records and actual payments remain blank until reviewed."));
        var issues=info["issues"].Array();var notes=Stack(8);foreach(var issue in issues)notes.Children.Add(Text(issue.Text("document")+": "+issue.Text("message"),13));if(issues.Count>0)checks.Children.Add(new Expander{Header=$"{issues.Count} preparation checks"+(data.Text("standard")=="GSTR-1"?" · JSON unavailable until resolved":" · review before use"),Content=notes,HorizontalAlignment=HorizontalAlignment.Stretch});var review=Stack(8);review.Children.Add(Text(string.Join(" · ",info["schedules"].Array().Select(r=>r.Text("name")+" ("+r.Text("rows")+")")),12));foreach(var warning in info["warnings"].Array())review.Children.Add(Text(warning.Text(),13));checks.Children.Add(new Expander{Header="Included schedules and review notes",Content=review,HorizontalAlignment=HorizontalAlignment.Stretch});panel.Children.Add(Card(checks));
        var tables=data["return_tables"] as JsonArray;if(tables is not null){foreach(var table in tables){var headers=table!["headers"].Array().Select(x=>x.Text()).ToArray();var money=table["money_columns"].Array().Select(x=>(int)x.Number()).ToHashSet();var rows=new JsonArray();foreach(var source in table["rows"].Array().OfType<JsonArray>()){var row=new JsonObject();for(var i=0;i<headers.Length;i++)row[headers[i]]=source[i] is null?"Needs review":money.Contains(i)?J.Money(source[i].Number()):source[i]!.ToString();rows.Add(row);}Table(panel,rows,table.Text("title"),headers);}}
        else{var columns=data["columns"].Array();var rows=new JsonArray();foreach(var source in data["rows"].Array()){var row=new JsonObject();foreach(var column in columns){var key=column.Text("key");var v=source?[key];row[column.Text("label")]=v is null?"Needs review":new[]{"taxable","cgst","sgst","igst","total","proposed_itc","ineligible"}.Contains(key)?J.Money(v.Number()):v.ToString();}rows.Add(row);}Table(panel,rows,data.Text("title"),columns.Select(c=>c.Text("label")));}
        panel.Children.Add(Card(Text(data.Text("note"),13)));if(data["hsn"].Array().Count>0)Table(panel,data["hsn"].Array(),"HSN / SAC summary",["hsn","rate","quantity","taxable","tax"]);
    }

    private static void RenderReport(Panel panel,JsonNode? value,string heading="")
    {
        if(value is JsonArray rows){Table(panel,rows,heading);return;}
        if(value is not JsonObject obj)return;
        if(heading.Length>0)panel.Children.Add(Text(Friendly(heading),20,true));
        var scalar=Stack(8);var any=false;
        foreach(var pair in obj.Where(p=>p.Value is JsonValue&&!p.Key.EndsWith("_id")&&p.Key!="id"&&p.Key!="digest"))
        {scalar.Children.Add(Columns(Text(Friendly(pair.Key),13),Text(Display(pair.Key,pair.Value),15,true)));any=true;}
        if(any)panel.Children.Add(Card(scalar));
        foreach(var pair in obj.Where(p=>p.Value is JsonObject or JsonArray))RenderReport(panel,pair.Value,Friendly(pair.Key));
    }

    private async Task PartyStatement(JsonObject party)
    {
        var cid=CompanyId;var stamp=generation;var exportAccess=CaptureFileSaveAccess();var panel=Stack(18);panel.MinWidth=850;var from=new DateInput("From",J.FinancialStart);var to=new DateInput("To",J.Today);var rows=Stack(16);var sequence=0;
        string Query()=>"?from_date="+from.Value+"&to_date="+to.Value;
        string Path()=>Api.CompanyPath(cid,$"/parties/{party.Text("id")}/statement");
        async Task Load()
        {
            var request=++sequence;var asOf=to.Value;var path=Path()+Query();
            async Task<JsonNode?> Credit(){if(!Supports("party_credit_limits"))return null;try{return await Api.Send(Api.CompanyPath(cid,$"/parties/{party.Text("id")}/credit-status?as_of={asOf}&proposed_amount=0"));}catch{return null;}}
            async Task<JsonNode?> Ledger(){try{return await Api.Send(Api.CompanyPath(cid,$"/parties/{party.Text("id")}/ledger")+Query());}catch{return null;}}
            var creditTask=Credit();var ledgerTask=Ledger();var result=await Api.Send(path);var status=await creditTask;var ledger=await ledgerTask;
            if(stamp!=generation||request!=sequence||cid!=CompanyId)return;
            rows.Children.Clear();var balances=result["balances"].Object();AddMetrics(rows,("Receivable",balances.Number("receivable")),("Payable",balances.Number("payable")),("Customer advances",balances.Number("customer_advance")),("Supplier advances",balances.Number("supplier_advance")),("Customer credits",balances.Number("customer_credit")),("Supplier credits",balances.Number("supplier_credit")));
            if(status is not null)rows.Children.Add(new InfoBar{IsOpen=true,IsClosable=false,Severity=status.Flag("exceeded")?InfoBarSeverity.Warning:InfoBarSeverity.Informational,Message=WorkflowMasterValues.CreditStatusText(status,false)});
            else rows.Children.Add(Text(Supports("party_credit_limits")?"Credit status unavailable. Statement balances remain available; this is not credit approval.":Api.Capabilities.Hint,12));
            if(ledger is JsonObject book)
            {
                rows.Children.Add(PartyLedgerView.Build(book));
                var documents=Stack(8);Table(documents,result["transactions"].Array());
                rows.Children.Add(new Expander{Header="Documents, drafts and estimates",Content=documents,HorizontalAlignment=HorizontalAlignment.Stretch,HorizontalContentAlignment=HorizontalAlignment.Stretch});
            }
            else Table(rows,result["transactions"].Array(),"Transactions");
        }
        var actions=new StackPanel{Orientation=Orientation.Horizontal,Spacing=10};actions.Children.Add(AsyncButton("Apply dates",Load,Error,true));
        foreach(var format in new[]{"pdf","xlsx"})actions.Children.Add(AsyncButton("Export "+format.ToUpperInvariant(),async()=>{await ScopedFileExport.Download(exportAccess,()=>Api.Download(Path()+"."+format+Query()),null,async(bytes,verify)=>{if(stamp!=generation||cid!=CompanyId)return false;return await ApexFiles.Save(bytes,"party-statement."+format,verify);});},Error));
        panel.Children.Add(Columns(from.View,to.View));panel.Children.Add(actions);panel.Children.Add(rows);await Load();if(stamp!=generation||cid!=CompanyId)return;await Dialog(party.Text("name")+" · statement",panel,()=>Task.CompletedTask,"Done");
    }

    private Task PreviewDocument(JsonObject row)=>ShowDocumentPdf(row,"");
    private async Task ShowDocumentPdf(JsonObject row,string template)
    {
        var cid=CompanyId;var stamp=generation;var exportAccess=CaptureFileSaveAccess();var path=Api.CompanyPath(cid,$"/documents/{row.Text("id")}.pdf")+(template.Length>0?"?template="+template:"");await ScopedFileExport.Download(exportAccess,()=>Api.Download(path),null,async(bytes,verify)=>{if(stamp!=generation||cid!=CompanyId)return false;await ShowPdf(bytes,Friendly(row.Text("kind"))+" "+row.Text("number")+".pdf",row,verify);return true;});
    }

    private async Task ShowPdf(byte[] bytes,string filename,JsonObject? record=null,Action? originalAccess=null)
    {
        async Task<BitmapImage> Render(byte[] source,int page){var png=(await ApexPrinter.Raster(source,1400,page))[0];using var bitmapStream=new InMemoryRandomAccessStream();using(var writer=new DataWriter(bitmapStream)){writer.WriteBytes(png);await writer.StoreAsync();writer.DetachStream();}bitmapStream.Seek(0);var bitmap=new BitmapImage();await bitmap.SetSourceAsync(bitmapStream);return bitmap;}
        var cid=CompanyId;var stamp=generation;var exportAccess=originalAccess??CaptureFileSaveAccess();bool closed=false;
        void PreviewAccess(){exportAccess();if(closed||stamp!=generation||cid!=CompanyId)throw new InvalidOperationException("This PDF preview is no longer active.");}
        bool Current()=>ScopedFileExport.Current(PreviewAccess);
        if(!Current())return;
        var count=await ApexPrinter.PageCount(bytes);if(!Current())return;var image=new Image{Source=await Render(bytes,0),Width=720,Stretch=Stretch.Uniform};var caption=Text($"Page 1 of {count}");var index=0;var renderSequence=0;var panel=Stack();panel.MinWidth=760;var toolbar=new StackPanel{Orientation=Orientation.Horizontal,Spacing=10};
        Button? previousButton=null,nextButton=null;string? externalAction=null;
        void Paging(){if(previousButton is not null)previousButton.IsEnabled=index>0;if(nextButton is not null)nextButton.IsEnabled=index+1<count;}
        async Task Draw(){if(!Current())return;var current=++renderSequence;try{var result=await Render(bytes,index);if(current!=renderSequence||!Current())return;image.Source=result;caption.Text=$"Page {index+1} of {count}";Paging();}catch(Exception)when(!Current()) {}}
        previousButton=AsyncButton("Previous",async()=>{if(index>0){index--;await Draw();}},Error);nextButton=AsyncButton("Next",async()=>{if(index+1<count){index++;await Draw();}},Error);
        toolbar.Children.Add(previousButton);toolbar.Children.Add(caption);toolbar.Children.Add(nextButton);Paging();
        toolbar.Children.Add(AsyncButton("Save PDF",async()=>{await ScopedFileExport.Run(PreviewAccess,()=>ApexFiles.Save(bytes,filename,PreviewAccess));},Error));
        toolbar.Children.Add(Button("Share PDF",()=>{if(!Current())return;externalAction="share";CloseDialog();}));
        toolbar.Children.Add(Button("Print",()=>{if(!Current())return;externalAction="print";CloseDialog();}));panel.Children.Add(toolbar);
        if(record is not null){var template=Select("Document format",[("","Company default"),("modern","Modern"),("vintage","Vintage"),("mrp_discount","MRP + discount"),("elegant","Elegant"),("evergreen","Evergreen")]);panel.Children.Add(template);var loadedIndex=template.SelectedIndex;var reverting=false;template.SelectionChanged+=async(_,_)=>{if(reverting||!Current())return;template.IsEnabled=false;++renderSequence;foreach(var action in toolbar.Children.OfType<Button>())action.IsEnabled=false;caption.Text="Loading format…";try{var selection=Value(template);var next=await Api.Download(Api.CompanyPath(cid,$"/documents/{record.Text("id")}.pdf")+(selection.Length>0?"?template="+selection:""));if(!Current())return;var bitmap=await Render(next,0);if(!Current())return;var pageCount=await ApexPrinter.PageCount(next);if(!Current())return;loadedIndex=template.SelectedIndex;bytes=next;count=pageCount;index=0;image.Source=bitmap;}catch(Exception e){if(Current()){reverting=true;template.SelectedIndex=loadedIndex;reverting=false;Error(e);}}finally{if(Current()){template.IsEnabled=true;caption.Text=$"Page {index+1} of {count}";foreach(var action in toolbar.Children.OfType<Button>())action.IsEnabled=true;Paging();}}};}
        panel.Children.Add(image);if(!Current())return;
        void Invalidate(){++renderSequence;bytes=Array.Empty<byte>();image.Source=null;foreach(var action in toolbar.Children.OfType<Button>())action.IsEnabled=false;panel.Children.Clear();panel.Children.Add(Text("Company access removed or unavailable. Close this preview and reopen it after access is restored."));}
        ReadAccessInvalidated+=Invalidate;
        try{await Dialog(filename,panel,()=>Task.CompletedTask,"Done");}finally{closed=true;ReadAccessInvalidated-=Invalidate;}
        // Release the WinUI modal before opening a separate OS modal surface.
        if(stamp!=generation||cid!=CompanyId||!ScopedFileExport.Current(exportAccess))return;
        if(externalAction=="share")await ScopedFileExport.Run(exportAccess,async()=>{await ApexShare.Show(bytes,filename,exportAccess);return true;});
        else if(externalAction=="print")await ScopedFileExport.Run(exportAccess,async()=>{await ApexPrinter.Print(bytes,filename,exportAccess);return true;});
    }

}
