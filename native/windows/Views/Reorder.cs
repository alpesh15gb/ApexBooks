using ApexBooks_Windows.Services;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using System.Text.Json.Nodes;
using static ApexBooks_Windows.Views.NativeUi;

namespace ApexBooks_Windows;

public sealed partial class MainPage
{
    private async Task ReorderReport()
    {
        var cid=CompanyId;var stamp=generation;var panel=Stack(16);var rows=Stack(12);
        var search=Input("Search low-stock items");var loadedRows=new List<JsonObject>();
        var asOf=new DateInput("Stock as of",J.Today);var selected=new List<(JsonObject Row,CheckBox Choice,TextBox Quantity)>();var loadedDate="";var sequence=0;JsonObject? draft=null;
        panel.Children.Add(Text("Low-stock & reorder review",22,true));
        panel.Children.Add(Text("Uses posted stock balances for tracked goods with a saved threshold. Suggestions do not place orders or change stock. Choose items, then review the supplier, quantities, rates and taxes in a purchase order draft.",13));
        void Draw()
        {
            rows.Children.Clear();selected.Clear();var matches=loadedRows.Where(r=>(r.Text("name")+" "+r.Text("unit")).Contains(search.Text.Trim(),StringComparison.OrdinalIgnoreCase)).ToList();
            rows.Children.Add(Text($"{loadedRows.Count} low-stock items · showing {Math.Min(matches.Count,100)} of {matches.Count} matching · {loadedDate}",16,true));
            rows.Children.Add(Text("Draft selection uses only the visible positive suggestions (up to 100). Changing the search resets selections; narrow your search for other items.",12));
            foreach(var row in matches.Take(100))
            {
                var choice=new CheckBox{Content=row.Text("name"),IsChecked=row.Number("suggested_quantity")>0,IsEnabled=CanWrite};
                var quantity=Input("Draft order quantity",row.Text("suggested_quantity"));quantity.IsEnabled=CanWrite;
                var card=Stack(8);card.Children.Add(choice);card.Children.Add(quantity);card.Children.Add(Text($"On hand {row.Text("on_hand")} {row.Text("unit")} · threshold {row.Text("low_stock_threshold")} · suggested {row.Text("suggested_quantity")}",13));
                card.Children.Add(Text($"Reference purchase rate {J.Money(row.Number("purchase_rate"))} · GST extra; review tax in draft · valuation {row.Text("valuation_status")}",12));
                if(row.Number("suggested_quantity")==0)card.Children.Add(Text("At threshold: no positive quantity suggested. Enter a positive draft quantity and select this item if you want to order.",12));
                rows.Children.Add(Card(card));selected.Add((row,choice,quantity));
            }
            if(selected.Count==0)rows.Children.Add(Text("No items match this review. Set a low-stock threshold in an item master to enable alerts; blank disables alerts.",13));
        }
        async Task Load()
        {
            var request=++sequence;var requestedDate=asOf.Value;
            var result=await Api.Send(Api.CompanyPath(cid,"/reports/reorder?as_of="+requestedDate));
            if(stamp!=generation||cid!=CompanyId||request!=sequence)return;
            loadedDate=requestedDate;loadedRows=result["rows"].Array().OfType<JsonObject>().ToList();Draw();
        }
        search.TextChanged+=(_,_)=>Draw();
        panel.Children.Add(Columns(asOf.View,AsyncButton("Refresh stock review",Load,Error)));panel.Children.Add(search);panel.Children.Add(rows);
        var review=AsyncButton("Review purchase order draft",async()=>{
            if(cid!=CompanyId||stamp!=generation)return;
            if(loadedDate!=asOf.Value)throw new Exception("Refresh stock review for the selected date before preparing a draft.");
            var choices=selected.Where(x=>x.Choice.IsChecked==true).ToList();if(choices.Count==0)throw new Exception("Choose at least one item with a positive suggested quantity.");
            if(choices.Count>100)throw new Exception("Choose at most 100 items for one purchase order draft.");
            var lines=new JsonArray();foreach(var (row,_,quantity) in choices){var master=Records.OfType<JsonObject>().FirstOrDefault(x=>x.Text("id")==row.Text("item_id"))??throw new Exception("An item master is missing from the loaded catalog. Refresh company data before preparing this draft.");var amount=WorkflowMasterValues.LowStockThreshold(quantity.Text);if(amount is null||amount.Number()<=0)throw new Exception("Enter a positive order quantity for every selected item.");var data=master["data"].Object();lines.Add(new JsonObject{["item_id"]=row.Text("item_id"),["description"]=row.Text("name"),["unit"]=row.Text("unit"),["quantity"]=amount.Copy(),["rate"]=row.Text("purchase_rate"),["gst_rate"]=data.Text("gst_rate"),["hsn"]=data.Text("hsn"),["tax_treatment"]=data.Text("tax_treatment"),["itc_treatment"]=data.Text("itc_treatment") is {Length:>0} itc?itc:"pending_review",["price_includes_tax"]=false});}
            draft=new JsonObject{["data"]=new JsonObject{["lines"]=lines,["notes"]="Prepared from low-stock review as of "+loadedDate+". Review supplier, quantity and pricing before saving."}};
            CloseDialog();await Task.CompletedTask;
        },Error,true);review.IsEnabled=CanWrite;panel.Children.Add(review);
        await Load();if(cid!=CompanyId||stamp!=generation)return;
        await Dialog("Reorder suggestions",panel,()=>Task.CompletedTask,"Done");
        if(draft is not null&&cid==CompanyId&&stamp==generation)await EditDocument("purchase_order",draftSeed:draft);
    }
}
