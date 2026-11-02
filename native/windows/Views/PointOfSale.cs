using ApexBooks_Windows.Services;
using ApexBooks_Windows.Views;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Markup;
using System.Globalization;
using System.Net.Http;
using System.Text.Json.Nodes;
using static ApexBooks_Windows.Views.NativeUi;

namespace ApexBooks_Windows;
public sealed partial class MainPage
{
    private Task PosPage()
    {
        var cid=CompanyId;var stamp=generation;var regular=Company.Text("tax_mode")=="regular";var items=Records.OfType<JsonObject>().Where(r=>r.Text("kind")=="item"&&WorkflowMasterValues.IsActive(r)).ToArray();var root=Columns(new StackPanel(),new StackPanel());root.ColumnDefinitions[0].Width=new GridLength(1.3,GridUnitType.Star);root.ColumnDefinitions[1].Width=new GridLength(1,GridUnitType.Star);var posHost=new ContentControl{Content=root,HorizontalContentAlignment=HorizontalAlignment.Stretch};var catalog=(StackPanel)root.Children[0];catalog.Spacing=14;var checkout=(StackPanel)root.Children[1];checkout.Spacing=14;
        var search=Input("Search products / scan barcode");catalog.Children.Add(search);var products=new ItemsControl();products.ItemsPanel=(ItemsPanelTemplate)XamlReader.Load("<ItemsPanelTemplate xmlns='http://schemas.microsoft.com/winfx/2006/xaml/presentation'><ItemsWrapGrid Orientation='Horizontal' MaximumRowsOrColumns='3'/></ItemsPanelTemplate>");catalog.Children.Add(new ScrollViewer{Content=products,MaxHeight=660,VerticalScrollBarVisibility=ScrollBarVisibility.Auto});
        posDrafts.TryGetValue(cid,out var draft);var saved=draft?.Body["data"].Object()??new();
        var customer=Input("Customer",draft?.Body.Text("name")??"Walk-in customer");var address=Input("Billing address",saved.Text("party_address"));var shipping=Input("Shipping address",saved.Text("shipping_address"),true);var lastShippingDefault="";var phone=Input("Phone",saved.Text("party_phone"));var gstin=Input("GSTIN",saved.Text("party_gstin"));var supply=Input("Place of supply · state code",saved.Text("place_of_supply") is {Length:>0} state?state:Company.Text("state_code"));var buyer=Select("Choose saved customer",new[]{("","Walk-in / entered customer")}.Concat(Records.Where(r=>r.Text("kind")=="party"&&WorkflowMasterValues.IsActive(r)).Select(r=>(r.Text("id"),r.Text("name")))),saved.Text("party_id"));var billing=Stack();foreach(var field in new UIElement[]{buyer,customer,address,shipping,phone,gstin,supply})billing.Children.Add(field);checkout.Children.Add(new Expander{Header="Customer details",Content=billing,HorizontalContentAlignment=HorizontalAlignment.Stretch,HorizontalAlignment=HorizontalAlignment.Stretch});
        var fillingBuyer=false;
        void ClearContact(){address.Text="";if(shipping.Text==lastShippingDefault)shipping.Text="";lastShippingDefault="";phone.Text="";gstin.Text="";supply.Text=Company.Text("state_code");}
        buyer.SelectionChanged+=(_,_)=>{if(fillingBuyer)return;fillingBuyer=true;try{var p=Records.FirstOrDefault(r=>r.Text("id")==Value(buyer));if(p is null){customer.Text="Walk-in customer";ClearContact();return;}customer.Text=p.Text("name");address.Text=p["data"].Text("address");var delivery=WorkflowMasterValues.ShippingAddress(p["data"]);if(shipping.Text.Length==0||shipping.Text==lastShippingDefault)shipping.Text=delivery;lastShippingDefault=delivery;phone.Text=p["data"].Text("phone");gstin.Text=p["data"].Text("gstin");supply.Text=gstin.Text.Length>=2?gstin.Text[..2]:Company.Text("state_code");}finally{fillingBuyer=false;}};
        customer.TextChanged+=(_,_)=>{if(fillingBuyer)return;fillingBuyer=true;try{SelectValue(buyer,"");ClearContact();}finally{fillingBuyer=false;}};
        var cart=Stack();var lines=new List<(string Item,DocumentLine Line,StackPanel Holder)>();checkout.Children.Add(Text("Current sale",23,true));checkout.Children.Add(new ScrollViewer{Content=cart,MaxHeight=420,VerticalScrollBarVisibility=ScrollBarVisibility.Auto});var round=new CheckBox{Content="Round to nearest rupee",IsChecked=saved.Flag("round_total")};var method=Select("Payment",[("cash","Cash"),("bank","Bank / UPI / card")],saved.Text("payment_account"));var bank=BankChoice(selected:saved.Text("bank_account_id"));var tender=Input("Cash tendered (₹)",saved.Text("tender_amount"));var totals=Text("Add an item to start.",21,true);totals.Foreground=Green;var change=Text("");var receipt=Stack();string key=draft?.Key??Guid.NewGuid().ToString();JsonNode? preview=null;CancellationTokenSource? pending=null;
        JsonObject BodyValue()=>new(){["kind"]="pos",["name"]=customer.Text.Trim().Length>0?customer.Text.Trim():"Walk-in customer",["date"]=J.Today,["data"]=new JsonObject{["lines"]=new JsonArray(lines.Select(r=>(JsonNode)r.Line.Data()).ToArray()),["party_id"]=Value(buyer),["party_address"]=address.Text,["shipping_address"]=shipping.Text,["party_phone"]=phone.Text,["party_gstin"]=gstin.Text.Trim().ToUpperInvariant(),["place_of_supply"]=supply.Text,["round_total"]=round.IsChecked==true,["payment_account"]=Value(method),["bank_account_id"]=Value(method)=="bank"?Value(bank):"",["tender_amount"]=Value(method)=="cash"&&tender.Text.Length>0?tender.Text:preview.Text("amount")}};
        void Change(){change.Text="";if(Value(method)=="cash"&&decimal.TryParse(tender.Text,NumberStyles.Number,CultureInfo.InvariantCulture,out var paid)&&preview is not null){var difference=paid-preview.Number("amount");change.Text=(difference<0?"Still due ":"Change ")+J.Money(Math.Abs(difference));}}
        async Task Calculate()
        {
            pending?.Cancel();pending=new CancellationTokenSource();var token=pending.Token;preview=null;change.Text="";
            foreach(var row in lines)row.Line.Amount.Text="—";
            if(lines.Count==0){totals.Text="Add an item to start.";return;}
            if(lines.Any(row=>string.IsNullOrWhiteSpace(row.Line.Description.Text)||string.IsNullOrWhiteSpace(row.Line.Rate.Text))){totals.Text="Enter an item description and rate to calculate the total.";return;}
            totals.Text="Calculating…";
            try
            {
                await Task.Delay(300,token);
                var result=await Api.Send(Api.CompanyPath(cid,"/documents/preview"),HttpMethod.Post,BodyValue(),cancellation:token);
                if(token.IsCancellationRequested||stamp!=generation)return;
                preview=result;totals.Text="Total "+J.Money(result.Number("amount"));
                var calculated=result["data"]?["lines"].Array()??new();
                for(var i=0;i<Math.Min(lines.Count,calculated.Count);i++)lines[i].Line.Amount.Text=J.Money(calculated[i].Number("taxable")+calculated[i].Number("tax"));
                Change();
            }
            catch(OperationCanceledException){}
            catch(Exception e){if(!token.IsCancellationRequested)totals.Text=e.Message;}
        }
        void Add(JsonObject item,JsonObject? restored=null)
        {
            if(!CanWrite)return;var existing=lines.FirstOrDefault(r=>r.Item==item.Text("id"));if(restored is null&&existing.Line is not null){existing.Line.Quantity.Text=(existing.Line.Data().Number("quantity")+1).ToString(CultureInfo.InvariantCulture);return;}
            var d=item["data"];var classification=d.Text("tax_treatment");if(regular&&d.Number("gst_rate")==0&&classification is "" or "taxable")classification="nil_rated";var line=new DocumentLine(items,false,regular,restored??new JsonObject{["item_id"]=item.Text("id"),["description"]=item.Text("name"),["quantity"]="1",["rate"]=d.Text("sale_rate"),["gst_rate"]=regular?d.Text("gst_rate"):"0",["tax_treatment"]=classification.Length>0?classification:"taxable",["hsn"]=d.Text("hsn"),["unit"]=d.Text("unit")});var holder=Stack();holder.Children.Add(line.View);holder.Children.Add(Button("Remove item",()=>{lines.RemoveAll(r=>r.Line==line);cart.Children.Remove(holder);_=Calculate();}));lines.Add((item.Text("id"),line,holder));cart.Children.Add(holder);line.Changed+=()=>_=Calculate();_=Calculate();
        }
        var productSequence=0;async Task Products(){var call=++productSequence;products.Items.Clear();foreach(var item in items.Where(r=>(r.Text("name")+" "+r["data"].Text("barcode")).Contains(search.Text,StringComparison.OrdinalIgnoreCase))){var row=item;var contents=Stack(8);contents.Children.Add(Text(row.Text("name"),14,true));contents.Children.Add(Text(J.Money(row["data"].Number("sale_rate")),17,true));var thumbnail=row["data"].Text("image_thumbnail");if(thumbnail.Length>0){var image=new Image{Height=65,Width=150,Stretch=Microsoft.UI.Xaml.Media.Stretch.Uniform};contents.Children.Insert(0,image);try{image.Source=await Bitmap(thumbnail);}catch{}}if(call!=productSequence||stamp!=generation)return;var button=Button("",()=>Add(row));button.Content=contents;Microsoft.UI.Xaml.Automation.AutomationProperties.SetName(button,"Add "+row.Text("name")+" · "+J.Money(row["data"].Number("sale_rate")));button.Width=178;button.MinHeight=150;button.Margin=new Thickness(0,0,10,10);button.IsEnabled=CanWrite;products.Items.Add(button);}}
        search.TextChanged+=async(_,_)=>await Products();search.KeyDown+=(_,e)=>{if(e.Key!=Windows.System.VirtualKey.Enter)return;var item=items.FirstOrDefault(r=>r["data"].Text("barcode").Length>0&&r["data"].Text("barcode")==search.Text.Trim());if(item is not null){Add(item);search.Text="";}};
        var paymentFields=Columns(method,bank);void PaymentFields(){var cash=Value(method)=="cash";bank.Visibility=cash?Visibility.Collapsed:Visibility.Visible;tender.Visibility=cash?Visibility.Visible:Visibility.Collapsed;Grid.SetColumnSpan(method,cash?2:1);Change();}PaymentFields();foreach(var field in new UIElement[]{round,paymentFields,tender,Card(totals),change})checkout.Children.Add(field);method.SelectionChanged+=(_,_)=>PaymentFields();tender.TextChanged+=(_,_)=>Change();round.Checked+=(_,_)=>_=Calculate();round.Unchecked+=(_,_)=>_=Calculate();gstin.TextChanged+=(_,_)=>_=Calculate();supply.TextChanged+=(_,_)=>_=Calculate();

        var posTabs = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 10 };
        var posTabsHost = new ContentControl { Content = posTabs, HorizontalContentAlignment = HorizontalAlignment.Stretch };
        var historyPanel = Stack();
        var historySearch = Input("Search sales history · name, reference or date");
        var historyRows = Stack();
        historyPanel.Children.Add(Text("POS sales history", 23, true));
        historyPanel.Children.Add(historySearch);
        historyPanel.Children.Add(historyRows);
        void DrawHistory()
        {
            historyRows.Children.Clear();
            var sales = Records.OfType<JsonObject>()
                .Where(r => r.Text("kind") == "pos" && (r.Text("name") + " " + r.Text("number") + " " + r.Text("date")).Contains(historySearch.Text, StringComparison.OrdinalIgnoreCase))
                .OrderByDescending(r => r.Text("date")).ThenByDescending(r => r.Text("number")).ToArray();
            if (sales.Length == 0) historyRows.Children.Add(Card(Text("No sales match this search.")));
            else AddRecordList(sales, historyRows);
        }
        historySearch.TextChanged += (_, _) => DrawHistory();
        posTabs.Children.Add(Button("New sale", () => posHost.Content = root));
        posTabs.Children.Add(Button("Sales history", () => { DrawHistory(); posHost.Content = historyPanel; }));
        var submission=draft?.Submission??new RetrySubmission();
        var save=AsyncButton("Complete sale",async()=>{notice.IsOpen=false;if(preview is null&&!submission.Unresolved)throw new Exception("Wait for a valid total before completing the sale.");navigation.IsEnabled=false;posHost.IsEnabled=false;posTabsHost.IsEnabled=false;try{JsonObject result;try{result=(await Api.SaveRecord(cid,submission.Body(BodyValue()),key)).Object();submission.Succeeded();}catch(Exception e){submission.Failed(e);if(submission.Unresolved)throw new Exception("The sale outcome is unknown. Complete sale again retries the original sale, not subsequent cart edits.",e);throw;}posDrafts.Remove(cid);if(stamp!=generation)return;cart.Children.Clear();lines.Clear();pending?.Cancel();preview=null;tender.Text="";totals.Text="Sale posted · "+result.Text("number");change.Text="";key=Guid.NewGuid().ToString();receipt.Children.Clear();receipt.Children.Add(AsyncButton("View / print receipt",()=>PreviewDocument(result),Error,true));var updated=await Api.Records(cid);if(stamp==generation)Records=updated;}finally{navigation.IsEnabled=true;posHost.IsEnabled=true;posTabsHost.IsEnabled=true;}},Error,true);save.IsEnabled=CanWrite;checkout.Children.Add(save);checkout.Children.Add(receipt);Body.Children.Add(posTabsHost);Body.Children.Add(posHost);
        foreach(var row in saved["lines"].Array().OfType<JsonObject>()){var item=items.FirstOrDefault(r=>r.Text("id")==row.Text("item_id"));if(item is not null)Add(item,row);}
        checkout.Children.Add(Text("Your cart is held for this company while navigating. It posts only on Complete sale; signing out discards it.",12));
        hasUnsavedPage=()=>lines.Count>0||submission.Unresolved;
        hasPendingPage=()=>submission.Unresolved;
        leavePage=()=>{if(lines.Count==0&&!submission.Unresolved)posDrafts.Remove(cid);else{var body=BodyValue();body["data"]!["tender_amount"]=tender.Text;posDrafts[cid]=new PosDraft(body,key,submission);}pending?.Cancel();};
        _=Products();return Task.CompletedTask;
    }
}
