using ApexBooks_Windows.Models;
using ApexBooks_Windows.Services;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using System.Text.Json.Nodes;
using static ApexBooks_Windows.Views.NativeUi;

namespace ApexBooks_Windows;

public sealed partial class MainPage
{
    private async Task TransactionDetails(JsonObject initial)
    {
        var cid=CompanyId;var stamp=generation;
        var row=(await Api.Record(cid,initial.Text("id"))).Object();
        if(stamp!=generation||cid!=CompanyId)return;
        var data=row["data"].Object();var kind=row.Text("kind");var panel=Stack(16);panel.MinWidth=620;
        var summary=Stack(8);summary.Children.Add(Text(new RecordRow(row).Status,12,true));
        summary.Children.Add(Text(row.Text("number") is {Length:>0} number?number:Friendly(kind),28,true));
        summary.Children.Add(Text(row.Text("name"),18,true));summary.Children.Add(Text(J.Money(kind=="item"?data.Number("sale_rate"):row.Number("amount")),30,true));
        summary.Children.Add(Text("Document date  ·  "+row.Text("date"),12));
        if(data.Text("due_date").Length>0){summary.Children.Add(Text("Due date  ·  "+data.Text("due_date"),12));if(row.Number("outstanding")>0&&string.CompareOrdinal(data.Text("due_date"),J.Today)<0)summary.Children.Add(Text("Overdue · record a collection or review the customer balance.",13,true));}
        if(kind=="item"){summary.Children.Add(Text("Sale price · "+data.Text("unit"),12));summary.Children.Add(Text("HSN / SAC  ·  "+data.Text("hsn"),12));}
        if(row["outstanding"] is not null)summary.Children.Add(Text("Outstanding  ·  "+J.Money(row.Number("outstanding")),16,true));
        if(data.Flag("is_advance")){summary.Children.Add(Text("Available advance  ·  "+J.Money(row.Number("advance_remaining")),16,true));summary.Children.Add(Text("An advance does not settle an invoice until it is applied.",12));}
        if(kind is "credit_note" or "debit_note")summary.Children.Add(Text("Available note credit  ·  "+J.Money(row.Number("credit_remaining")),16,true));
        if(row.Text("converted_to")=="source-converted")summary.Children.Add(Text("Converted in the source system · the destination document was not included in this import.",12));
        panel.Children.Add(Card(summary));
        string action="",linkedId="";
        var actions=new StackPanel{Orientation=Orientation.Horizontal,Spacing=8};
        void Action(string label,string key,bool primary=false)=>actions.Children.Add(Button(label,()=>{action=key;CloseDialog();},primary));
        if(kind is "purchase_bill" or "expense"){if(Supports("document_attachments"))Action("Retained receipts","receipts");else panel.Children.Add(CapabilityNotice());}
        var printable=FeatureCatalog.Documents.Contains(kind)||kind is "payment_in" or "payment_out" or "customer_refund" or "supplier_refund" or "advance_refund";
        if(printable)Action("PDF / print / share","pdf");
        var cancelled=row.Flag("cancelled");
        if(cancelled)panel.Children.Add(Card(Text("Cancelled"+(data["cancelled"].Text("reason") is {Length:>0} why?" · "+why:"")+". The number stays in your records; its ledger, stock and balance effects were reversed.",13)));
        if(CanWrite&&!cancelled&&row.Text("converted_to").Length==0&&(FeatureCatalog.Documents.Contains(kind)||kind is "payment_in" or "payment_out" or "bank_transfer"))Action("Edit","edit");
        panel.Children.Add(actions);
        var next=Stack(8);
        void Next(string label,string key)=>next.Children.Add(Button(label,()=>{action=key;CloseDialog();},true));
        if(CanWrite&&row.Number("outstanding")>0&&kind is "sales_invoice" or "purchase_bill")Next(kind=="sales_invoice"?"Record payment received":"Record supplier payment","payment");
        if(CanWrite&&kind is "estimate" or "proforma"&&row.Text("converted_to").Length==0)Next("Convert to sales order","sales_order");
        if(CanWrite&&Supports("recurring_drafts")&&FeatureCatalog.Drafts.Contains(kind)&&row.Text("converted_to").Length==0)Next("Create recurring draft schedule","recurring");
        if(CanWrite&&FeatureCatalog.Drafts.Contains(kind)&&row.Text("converted_to").Length==0)Next(kind=="purchase_order"?"Convert to purchase bill":"Convert to invoice","convert");
        if(CanWrite&&row.Flag("posted")&&kind is "sales_invoice" or "pos" or "purchase_bill")Next(kind=="purchase_bill"?"Create purchase return / debit note":"Create sales return / credit note","return");
        if(CanWrite&&(row.Number("advance_remaining")>0||row.Number("credit_remaining")>0))Next("Apply / refund available balance","settle");
        if(Supports("document_cancellation")&&CanWrite&&!cancelled&&row.Flag("posted")&&kind is "sales_invoice" or "pos" or "purchase_bill" or "payment_in" or "payment_out" or "expense" or "credit_note" or "debit_note" or "bank_transfer")next.Children.Add(Button("Cancel this document",()=>{action="cancel";CloseDialog();}));
        if(next.Children.Count>0){panel.Children.Add(Text("Next steps",18,true));panel.Children.Add(next);}
        if(!CanWrite)panel.Children.Add(Text("Read-only access · ask an owner for editor access to record payments, returns or changes.",12));
        foreach(var (label,id) in new[]{("Posted document",row.Text("converted_to")),("Source document",data.Text("source_document_id")),("Original invoice / bill",data.Text("applied_to"))}.Where(x=>x.Item2.Length>0&&x.Item2!="source-converted")){
            var linked=Records.FirstOrDefault(r=>r.Text("id")==id);var reference=linked.Text("number");
            panel.Children.Add(Button(label+"  ·  "+(reference.Length>0?reference:id[..Math.Min(8,id.Length)])+"  →",()=>{linkedId=id;action="linked";CloseDialog();}));
        }
        var allocations=row["allocations"].Array();if(allocations.Count==0)allocations=data["allocations"].Array();
        if(allocations.Count>0){panel.Children.Add(Text("Payment allocation",18,true));foreach(var allocation in allocations){var id=allocation.Text("document_id");var target=Records.FirstOrDefault(r=>r.Text("id")==id);panel.Children.Add(Button(target.Text("number")+"  ·  "+J.Money(allocation.Number("amount"))+"  →",()=>{linkedId=id;action="linked";CloseDialog();}));}panel.Children.Add(Text("Allocation settles the document. Bank matching is a separate reconciliation step.",12));}
        if(data["lines"].Array().Count>0){panel.Children.Add(Text("Items",18,true));foreach(var line in data["lines"].Array()){var item=Stack(4);item.Children.Add(Text(line.Text("description"),14,true));item.Children.Add(Text(line.Text("quantity")+" "+line.Text("unit")+" × "+J.Money(line.Number("rate"))+"  ·  "+J.Money(line.Number("taxable")+line.Number("tax")),12));if(line is JsonObject lineValues&&lineValues.ContainsKey("discount_amount"))item.Children.Add(Text("Fixed line discount · "+J.Money(line.Number("discount_amount")),12));else if(line.Number("discount_percent")>0)item.Children.Add(Text("Line discount · "+line.Text("discount_percent")+"%",12));if(line.Number("document_discount")>0)item.Children.Add(Text("Document discount allocated to this line · "+J.Money(line.Number("document_discount")),12));panel.Children.Add(Card(item));}}
        if(data.Text("notes").Length>0){panel.Children.Add(Text("Notes",16,true));panel.Children.Add(Text(data.Text("notes")));}
        await Dialog("Transaction details",panel,()=>Task.CompletedTask,"Done");
        if(stamp!=generation||cid!=CompanyId)return;
        switch(action){
            case "receipts":await RetainedReceipts(row);break;
            case "recurring":await RecurringTemplateForm(row);break;
            case "pdf":await PreviewDocument(row);break;
            case "edit":await EditRow(row);break;
            case "payment":await EditPayment(kind=="sales_invoice"?"payment_in":"payment_out",document:row);break;
            case "sales_order":await EditDocument("sales_order",conversion:row);break;
            case "convert":await EditDocument(kind=="purchase_order"?"purchase_bill":"sales_invoice",conversion:row);break;
            case "return":await EditDocument(kind=="purchase_bill"?"debit_note":"credit_note",returnSource:row);break;
            case "settle":await SettleBalance(row.Number("credit_remaining")>0,row.Text("id"));break;
            case "cancel":await CancelDocument(row);break;
            case "linked":if(linkedId.Length>0)await TransactionDetails(new JsonObject{["id"]=linkedId});break;
        }
    }
}
