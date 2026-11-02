using ApexBooks_Windows.Services;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using System.Net.Http;
using System.Text.Json.Nodes;
using static ApexBooks_Windows.Views.NativeUi;

namespace ApexBooks_Windows;
public sealed partial class MainPage
{
    private async Task CommerceMoney(string cid,string connectionId,JsonObject workspace)
    {
        var key=Guid.NewGuid().ToString();var panel=Stack();
        panel.Children.Add(Text("Record confirmed bank/provider transactions or goods receipts. Invoice status alone is not payment evidence."));
        var kind=Select("Action",new[]{("capture","Payment received / captured"),("refund","Cash / gateway refund"),("settlement","Gateway settlement"),("receipt","Goods physically received")});
        var source=Input("Bank / provider / receipt reference");var issued=new DateInput("Accounting date",J.Today);var amount=Input("Amount (₹)");
        var orders=Select("Store order",workspace["orders"].Array().Select(r=>(r.Text("external_id"),r.Text("number"))));
        var target=Select("Original invoice / credit / advance",Array.Empty<(string,string)>());var supply=Select("Advance supply",new[]{("goods","Goods"),("services","Services")});var gst=Select("Advance GST rate",new[]{"0","5","12","18","28"}.Select(r=>(r,r+"%")));var pos=Input("Advance place of supply · state code",(workspace["connection"]?["config"]?["capabilities"].Text("company_state_code")??""));
        var bank=Select("Destination bank",Banks.Where(r=>r.Text("id")!=workspace["connection"]?["config"].Text("gateway_bank_id")).Select(r=>(r.Text("id"),r.Text("name"))));var net=Input("Bank net received (₹)");var fee=Input("Provider fee excluding supplier GST (₹)","0");
        var capturePanel=Stack();var refundPanel=Stack();var receiptPanel=Stack();var receiptFields=new Dictionary<string,TextBox>();
        var captures=new List<(JsonNode Row,CheckBox Check)>();var refunds=new List<(JsonNode Row,CheckBox Check)>();var links=workspace["links"].Array().OfType<JsonObject>().ToArray();
        foreach(var row in links.Where(r=>r.Text("entity_type") is "capture" or "refund" && r["snapshot"].Text("_settled").Length==0)){
            var check=new CheckBox{Content=row.Text("external_id")+" · "+J.Money(row["snapshot"].Number("amount"))};
            if(row.Text("entity_type")=="capture"){captures.Add((row!,check));capturePanel.Children.Add(check);}else{refunds.Add((row!,check));refundPanel.Children.Add(check);}
        }
        foreach(var element in new UIElement[]{kind,source,issued.View,orders,target,amount,supply,gst,pos})panel.Children.Add(element);
        var settlement=Stack();settlement.Children.Add(Text("Captured receipts included in payout",14,true));settlement.Children.Add(capturePanel);settlement.Children.Add(Text("Refunds deducted by provider",14,true));settlement.Children.Add(refundPanel);settlement.Children.Add(Columns(net,fee));settlement.Children.Add(bank);settlement.Children.Add(Text("Captured gross minus selected refunds and fee must equal the bank net. Record provider GST with its supplier bill."));panel.Children.Add(settlement);panel.Children.Add(receiptPanel);
        void Receipt(){receiptPanel.Children.Clear();receiptFields.Clear();if(Value(kind)!="receipt")return;var note=links.FirstOrDefault(r=>r.Text("entity_type")=="credit"&&r.Text("external_id")==Value(target));foreach(var line in note?["snapshot"]?["lines"].Array()??new JsonArray()){var id=line.Text("product_id");var item=workspace["stock"].Array().FirstOrDefault(r=>r.Text("external_id")==id);var field=Input((item?.Text("name")??id)+" · quantity physically received · credited "+line.Text("quantity"));receiptFields[id]=field;receiptPanel.Children.Add(field);}}
        void Targets(){target.Items.Clear();var action=Value(kind);if(action=="capture")target.Items.Add(new ComboBoxItem{Tag="",Content="Unapplied customer advance"});foreach(var row in links.Where(r=>r["snapshot"].Text("order_id")==Value(orders))){var entity=row.Text("entity_type");if(action=="capture"&&entity=="invoice"||action=="receipt"&&entity=="credit"||action=="refund"&&entity is "credit" or "capture")target.Items.Add(new ComboBoxItem{Tag=action=="refund"?entity+":"+row.Text("external_id"):row.Text("external_id"),Content=Friendly(entity)+" "+row.Text("external_id")+" · "+J.Money(row["snapshot"].Number("amount"))});}if(target.Items.Count>0)target.SelectedIndex=0;Receipt();}
        void Show(){var action=Value(kind);orders.Visibility=target.Visibility=action=="settlement"?Visibility.Collapsed:Visibility.Visible;amount.Visibility=action is "capture" or "refund"?Visibility.Visible:Visibility.Collapsed;supply.Visibility=gst.Visibility=pos.Visibility=action=="capture"&&Value(target)==""?Visibility.Visible:Visibility.Collapsed;settlement.Visibility=action=="settlement"?Visibility.Visible:Visibility.Collapsed;receiptPanel.Visibility=action=="receipt"?Visibility.Visible:Visibility.Collapsed;}
        kind.SelectionChanged+=(_,_)=>{Targets();Show();};orders.SelectionChanged+=(_,_)=>{Targets();Show();};target.SelectionChanged+=(_,_)=>{Receipt();Show();};Targets();Show();
        await Dialog("Payments, payouts & returns",panel,async()=>{
            if(source.Text.Trim().Length==0)throw new Exception("Enter the bank, provider or goods receipt reference.");
            var action=Value(kind);var data=new JsonObject{["date"]=issued.Value,["order_id"]=Value(orders)};string operation;
            if(action=="capture"){operation="payment.capture";data["amount"]=amount.Text;if(Value(target).Length>0)data["allocations"]=new JsonArray(new JsonObject{["invoice_id"]=Value(target),["amount"]=amount.Text});else{data["advance_supply"]=Value(supply);data["advance_gst_rate"]=Value(gst);data["place_of_supply"]=pos.Text;}}
            else if(action=="refund"){operation="payment.refund";data["amount"]=amount.Text;var selected=Value(target);var split=selected.IndexOf(':');if(split<0)throw new Exception("Choose the original credit or advance.");data[selected[..split]=="credit"?"credit_id":"capture_id"]=selected[(split+1)..];}
            else if(action=="receipt"){operation="return.receive";data["credit_id"]=Value(target);var lines=new JsonArray();foreach(var pair in receiptFields){if(!decimal.TryParse(pair.Value.Text,out var qty)||qty<=0)continue;lines.Add(new JsonObject{["product_id"]=pair.Key,["quantity"]=qty.ToString(System.Globalization.CultureInfo.InvariantCulture)});}if(lines.Count==0)throw new Exception("Enter quantities physically received.");data["lines"]=lines;}
            else{operation="settlement.record";data.Remove("order_id");data["gross"]=captures.Where(r=>r.Check.IsChecked==true).Sum(r=>r.Row["snapshot"].Number("amount")).ToString(System.Globalization.CultureInfo.InvariantCulture);data["capture_ids"]=new JsonArray(captures.Where(r=>r.Check.IsChecked==true).Select(r=>(JsonNode?)JsonValue.Create(r.Row.Text("external_id"))).ToArray());data["refund_ids"]=new JsonArray(refunds.Where(r=>r.Check.IsChecked==true).Select(r=>(JsonNode?)JsonValue.Create(r.Row.Text("external_id"))).ToArray());data["net"]=net.Text;data["fee"]=fee.Text;data["bank_account_id"]=Value(bank);}
            await Api.Send(Api.CompanyPath(cid,$"/commerce/connections/{connectionId}/commands"),HttpMethod.Post,new JsonObject{["command_id"]=key,["operation"]=operation,["payload"]=new JsonObject{["source_id"]=source.Text.Trim(),["confirmed"]=true,["data"]=data}});
        },"Confirm source & queue");
    }
}


