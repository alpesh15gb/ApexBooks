using ApexBooks_Windows.Services;
using ApexBooks_Windows.Views;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using System.Net.Http;
using System.Text.Json.Nodes;
using static ApexBooks_Windows.Views.NativeUi;

namespace ApexBooks_Windows;
public sealed partial class MainPage
{
    private async Task EditPayment(string kind, JsonObject? previous = null,JsonObject? document=null)
    {
        var cid=CompanyId;var data=previous?["data"].Object()??new();var panel=Stack();panel.MinWidth=650;
        var name=Input("Party",document?.Text("name")??previous.Text("name"));var number=Input("Reference · automatic when blank",previous.Text("number"));
        var date=new DateInput("Payment date",previous.Text("date") is {Length:>0} day?day:J.Today);var amount=Input("Amount (₹)",document?.Text("outstanding")??previous.Text("amount"));
        var method=Select("Paid through",[("cash","Cash"),("bank","Bank / UPI / card")],data.Text("payment_account"));var bank=BankChoice(selected:data.Text("bank_account_id"));
        var advance=new CheckBox{Content="Advance for later allocation",IsChecked=data.Flag("is_advance")};
        var supply=Select("Advance relates to",[("goods","Goods"),("services","Services")],data.Text("advance_supply"));var tax=Input("Service advance GST rate (%)",data.Text("advance_gst_rate") is {Length:>0} r?r:"18");var state=Input("Place of supply · state code",data.Text("place_of_supply") is {Length:>0} s?s:Company.Text("state_code"));
        var notes=Input("Notes",data.Text("notes"),true);var allocations=Stack();var rows=new List<(ComboBox Target,TextBox Amount)>();
        var original=previous?["allocations"].Array()??new();if(original.Count==0)original=data["allocations"].Array();
        if(original.Count==0&&data.Text("applied_to").Length>0)original=new JsonArray(new JsonObject{["document_id"]=data.Text("applied_to"),["amount"]=previous.Text("amount")});
        var targets=Records.OfType<JsonObject>().Where(r=>r.Flag("posted")&&(kind=="payment_in"?r.Text("kind") is "sales_invoice" or "opening_receivable":r.Text("kind") is "purchase_bill" or "opening_payable")).Where(r=>r.Number("outstanding")>0||original.Any(a=>a.Text("document_id")==r.Text("id"))).ToArray();
        void AddAllocation(JsonNode? initial=null)
        {
            var target=Select("Invoice / bill",new[]{("","Choose document")}.Concat(targets.Select(r=>(r.Text("id"),$"{r.Text("number")} · {r.Text("name")} · {J.Money(r.Number("outstanding")+original.Where(a=>a.Text("document_id")==r.Text("id")).Sum(a=>a.Number("amount")))} available"))),initial.Text("document_id"));
            var allocated=Input("Allocated (₹)",initial.Text("amount"));var row=Columns(target,allocated);rows.Add((target,allocated));allocations.Children.Add(row);
            var remove=Button("Remove",()=>{rows.Remove((target,allocated));allocations.Children.Remove(row);});row.ColumnDefinitions.Add(new ColumnDefinition{Width=GridLength.Auto});Grid.SetColumn(remove,2);row.Children.Add(remove);
            target.SelectionChanged+=(_,_)=>{
                var chosen=targets.FirstOrDefault(r=>r.Text("id")==Value(target));
                if(chosen is null){allocated.Text="";return;}
                if(name.Text.Length==0||rows.Count==1)name.Text=chosen.Text("name");
                var available=Math.Max(0,chosen.Number("outstanding")+original.Where(a=>a.Text("document_id")==chosen.Text("id")).Sum(a=>a.Number("amount")));
                if(amount.Text.Trim().Length==0)amount.Text=available.ToString(System.Globalization.CultureInfo.InvariantCulture);
                decimal ReadAmount(string value)=>decimal.TryParse(value,System.Globalization.NumberStyles.Number,System.Globalization.CultureInfo.InvariantCulture,out var parsed)?parsed:0;
                var others=rows.Where(r=>r.Amount!=allocated).Sum(r=>ReadAmount(r.Amount.Text));
                var remaining=Math.Max(0,ReadAmount(amount.Text)-others);
                allocated.Text=Math.Min(available,remaining).ToString(System.Globalization.CultureInfo.InvariantCulture);
            };
        }
        foreach(var initial in original)AddAllocation(initial);if(document is not null)AddAllocation(new JsonObject{["document_id"]=document.Text("id"),["amount"]=document.Text("outstanding")});if(rows.Count==0)AddAllocation();
        var advanceFields=Stack();advanceFields.Children.Add(Text("Customer service advances include GST in the received amount. Goods advances defer tax until invoicing.",12));foreach(var field in new UIElement[]{supply,tax,state})advanceFields.Children.Add(field);
        var add=Button("Add another allocation",()=>AddAllocation());
        void Visibility(){allocations.Visibility=add.Visibility=advance.IsChecked==true?Microsoft.UI.Xaml.Visibility.Collapsed:Microsoft.UI.Xaml.Visibility.Visible;advanceFields.Visibility=advance.IsChecked==true&&kind=="payment_in"&&Company.Text("tax_mode")=="regular"?Microsoft.UI.Xaml.Visibility.Visible:Microsoft.UI.Xaml.Visibility.Collapsed;bank.Visibility=Value(method)=="bank"?Microsoft.UI.Xaml.Visibility.Visible:Microsoft.UI.Xaml.Visibility.Collapsed;tax.Visibility=state.Visibility=Value(supply)=="services"?Microsoft.UI.Xaml.Visibility.Visible:Microsoft.UI.Xaml.Visibility.Collapsed;}
        advance.Checked+=(_,_)=>Visibility();advance.Unchecked+=(_,_)=>Visibility();method.SelectionChanged+=(_,_)=>Visibility();supply.SelectionChanged+=(_,_)=>Visibility();Visibility();
        foreach(var field in new UIElement[]{Columns(name,number),Columns(date.View,amount),Columns(method,bank),advance,advanceFields,allocations,add,notes})panel.Children.Add(field);
        var key=Guid.NewGuid().ToString();var submission=new RetrySubmission();
        string Signature()=>new JsonObject{["name"]=name.Text,["number"]=number.Text,["date"]=date.Value,["amount"]=amount.Text,["method"]=Value(method),["bank"]=Value(bank),["advance"]=advance.IsChecked==true,["supply"]=Value(supply),["tax"]=tax.Text,["state"]=state.Text,["notes"]=notes.Text,["allocations"]=new JsonArray(rows.Select(r=>(JsonNode)new JsonObject{["id"]=Value(r.Target),["amount"]=r.Amount.Text}).ToArray())}.ToJsonString();var baseline=Signature();
        if(await Dialog(previous is null?"Record "+kind.Replace('_',' '):"Edit "+previous.Text("number"),panel,async()=>{
            var values=new JsonObject{["notes"]=notes.Text,["payment_account"]=Value(method),["is_advance"]=advance.IsChecked==true,["advance_supply"]=Value(supply),["advance_gst_rate"]=tax.Text,["place_of_supply"]=state.Text};
            if(Value(method)=="bank")values["bank_account_id"]=Value(bank);if(previous is not null)values["version"]=data.Number("version");
            var selected=new JsonArray();if(advance.IsChecked!=true){foreach(var row in rows){if(Value(row.Target).Length==0)throw new Exception("Choose a document for every allocation.");selected.Add(new JsonObject{["document_id"]=Value(row.Target),["amount"]=row.Amount.Text});}if(selected.Count==0)throw new Exception("Allocate the payment or record an advance.");}values["allocations"]=selected;
            var wasUnknown=submission.Unresolved;
            try{await Api.SaveRecord(cid,submission.Body(new JsonObject{["kind"]=kind,["name"]=name.Text,["number"]=number.Text,["date"]=date.Value,["amount"]=amount.Text,["data"]=values}),key,previous);submission.Succeeded();}catch(Exception e){WorkflowMasterValues.DocumentWriteFailed(submission,e,false,previous is not null,wasUnknown);NativeUi.SetFormEnabled(panel,!submission.Unresolved);if(submission.Unresolved)throw new Exception("The payment outcome is unknown. Original values are locked; post again to recover the same payment.",e);throw;}
        },previous is null?"Post payment":"Save amendment",unresolved:()=>submission.Unresolved,hasChanges:()=>Signature()!=baseline))if(cid==CompanyId)await Refresh();
    }

    private async Task SettleBalance(bool credits,string selectedId="")
    {
        var cid=CompanyId;var choices=Records.OfType<JsonObject>().Where(r=>credits?r.Number("credit_remaining")>0:r.Number("advance_remaining")>0).ToArray();
        if(choices.Length==0){Success(credits?"No unallocated note credit is available.":"No unapplied advance is available.");return;}
        var source=Select(credits?"Credit / debit note":"Advance",choices.Select(r=>(r.Text("id"),$"{r.Text("number")} · {r.Text("name")} · {J.Money(r.Number(credits?"credit_remaining":"advance_remaining"))}")),selectedId);
        var action=Select("Action",[("apply","Apply to invoice / bill"),("refund","Refund")]);var target=Select("Apply to",[("","Choose document")]);var amount=Input("Amount (₹)");var date=new DateInput("Date",J.Today);var method=Select("Refund through",[("cash","Cash"),("bank","Bank / UPI / card")]);var bank=BankChoice();
        void Update(){var row=choices.First(r=>r.Text("id")==Value(source));var customer=row.Text("kind") is "credit_note" or "payment_in";target.Items.Clear();foreach(var r in Records.OfType<JsonObject>().Where(r=>r.Flag("posted")&&r.Text("kind")== (customer?"sales_invoice":"purchase_bill")&&r.Text("name").Trim().Equals(row.Text("name").Trim(),StringComparison.OrdinalIgnoreCase)&&r.Number("outstanding")>0))target.Items.Add(new ComboBoxItem{Content=$"{r.Text("number")} · {J.Money(r.Number("outstanding"))}",Tag=r.Text("id")});if(target.Items.Count>0)target.SelectedIndex=0;amount.Text=row.Text(credits?"credit_remaining":"advance_remaining");}
        source.SelectionChanged+=(_,_)=>Update();Update();void ShowSettlement(){var refund=Value(action)=="refund";target.Visibility=refund?Microsoft.UI.Xaml.Visibility.Collapsed:Microsoft.UI.Xaml.Visibility.Visible;method.Visibility=refund?Microsoft.UI.Xaml.Visibility.Visible:Microsoft.UI.Xaml.Visibility.Collapsed;bank.Visibility=refund&&Value(method)=="bank"?Microsoft.UI.Xaml.Visibility.Visible:Microsoft.UI.Xaml.Visibility.Collapsed;}action.SelectionChanged+=(_,_)=>ShowSettlement();method.SelectionChanged+=(_,_)=>ShowSettlement();ShowSettlement();
        var panel=Stack();foreach(var field in new UIElement[]{source,action,target,Columns(date.View,amount),Columns(method,bank)})panel.Children.Add(field);var key=Guid.NewGuid().ToString();var submission=new RetrySubmission();
        string Signature()=>new JsonObject{["source"]=Value(source),["action"]=Value(action),["target"]=Value(target),["amount"]=amount.Text,["date"]=date.Value,["method"]=Value(method),["bank"]=Value(bank)}.ToJsonString();var baseline=Signature();
        if(await Dialog(credits?"Apply or refund note credit":"Apply or refund advance",panel,async()=>{var row=choices.First(r=>r.Text("id")==Value(source));var values=new JsonObject{["action"]=Value(action),["applied_to"]=Value(target),["payment_account"]=Value(method),["bank_account_id"]=Value(bank)};try{await Api.Send(Api.CompanyPath(cid,credits?$"/credits/{row.Text("id")}/settle":$"/advances/{row.Text("id")}/{Value(action)}"),HttpMethod.Post,submission.Body(new JsonObject{["kind"]="advance_application",["name"]=row.Text("name"),["date"]=date.Value,["amount"]=amount.Text,["data"]=values}),key);submission.Succeeded();}catch(Exception e){submission.Failed(e);NativeUi.SetFormEnabled(panel,!submission.Unresolved);if(submission.Unresolved)throw new Exception("The settlement outcome is unknown. Original values are locked; post again to recover it safely.",e);throw;}},"Post settlement",unresolved:()=>submission.Unresolved,hasChanges:()=>Signature()!=baseline))if(cid==CompanyId)await Refresh();
    }
}
