using ApexBooks_Windows.Models;
using ApexBooks_Windows.Services;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using System.Text.Json.Nodes;
using static ApexBooks_Windows.Views.NativeUi;

namespace ApexBooks_Windows;

public sealed partial class MainPage
{
    private async Task OpenWhatsApp(JsonObject row,bool reminder)
    {
        var cid=CompanyId;var stamp=generation;var session=Api.SessionGeneration;
        var snapshot=(JsonObject)row.DeepClone();var companyName=Company.Text("name");
        var phone=WhatsAppShare.PartyPhone(snapshot,Records.OfType<JsonObject>());
        await ScopedExternalAction.Run(
            async()=>(await Api.Send(Api.CompanyPath(cid,"/document-branding"))).Text("upi_id"),
            ()=>Api.SignedIn&&Api.SessionGeneration==session&&cid==CompanyId&&stamp==generation,
            upi=>WhatsAppShare.Url(phone,reminder?WhatsAppShare.ReminderMessage(snapshot,companyName,upi,J.Today):WhatsAppShare.DocumentMessage(snapshot,companyName,upi)),
            async uri=>{await Windows.System.Launcher.LaunchUriAsync(uri);});
    }

    private async Task TransactionDetails(JsonObject initial)
    {
        var cid=CompanyId;var stamp=generation;
        var row=(await Api.Record(cid,initial.Text("id"))).Object();
        if(stamp!=generation||cid!=CompanyId)return;
        var data=row["data"].Object();var kind=row.Text("kind");var panel=Stack(16);panel.MinWidth=620;
        var supportsReceiving=kind=="purchase_order"&&Supports("purchase_order_receiving");
        JsonObject? receiving=null;
        string receivingError="";
        if(supportsReceiving)
        {
            try { receiving=(await Api.Send(Api.CompanyPath(cid,$"/purchase-orders/{Uri.EscapeDataString(row.Text("id"))}/receiving"))).Object(); }
            catch(Exception error){receivingError=error.Message;}
            if(stamp!=generation||cid!=CompanyId)return;
        }
        var lockedOrder=PurchaseReceivingStarted(row)||receiving?["receipts"].Array().Count>0;
        var summary=Stack(12);
        var identity=Stack(6);var display=new RecordRow(row);
        identity.Children.Add(Text(row.Text("number") is {Length:>0} number?number:Friendly(kind),22,true));
        if(row.Text("name") is {Length:>0} name)identity.Children.Add(Text(name,15,true));
        if(display.Status.Length>0)
        {
            var status=Text(display.Status,12,true);status.Foreground=display.StatusBrush;
            identity.Children.Add(status);
        }
        if(row.Text("date") is {Length:>0} date)identity.Children.Add(Text("Document date  ·  "+date,12));
        if(data.Text("due_date") is {Length:>0} dueDate)identity.Children.Add(Text("Due date  ·  "+dueDate,12));
        if(kind=="item"&&data.Text("hsn") is {Length:>0} hsn)identity.Children.Add(Text("HSN / SAC  ·  "+hsn,12));

        var money=Stack(6);
        var amountLabel=Text(kind=="item"?"Sale price"+(data.Text("unit") is {Length:>0} unit?$" per {unit}":""):"Document total",12,true);
        amountLabel.Foreground=Muted;money.Children.Add(amountLabel);
        money.Children.Add(Text(J.Money(kind=="item"?data.Number("sale_rate"):row.Number("amount")),24,true));
        if(row["outstanding"] is not null)money.Children.Add(Text("Outstanding  ·  "+J.Money(row.Number("outstanding")),15,true));
        if(data.Flag("is_advance"))money.Children.Add(Text("Available advance  ·  "+J.Money(row.Number("advance_remaining")),15,true));
        if(kind is "credit_note" or "debit_note")money.Children.Add(Text("Available note credit  ·  "+J.Money(row.Number("credit_remaining")),15,true));
        summary.Children.Add(ResponsiveGrid(235,identity,money));
        if(data.Text("due_date") is {Length:>0} deadline&&row.Number("outstanding")>0&&string.CompareOrdinal(deadline,J.Today)<0)
            summary.Children.Add(Text(kind=="purchase_bill"?"Overdue · record a supplier payment or review the supplier balance.":"Overdue · record a collection or review the customer balance.",13,true));
        if(data.Flag("is_advance"))summary.Children.Add(Text("An advance does not settle an invoice until it is applied.",12));
        if(row.Text("converted_to")=="source-converted")summary.Children.Add(Text("Converted in the source system · the destination document was not included in this import.",12));
        panel.Children.Add(Card(summary));
        string action="",linkedId="";
        var secondaryActions=new List<UIElement>();
        void Action(string label,string key)=>secondaryActions.Add(Button(label,()=>{action=key;CloseDialog();}));
        if(kind is "purchase_bill" or "expense"){if(Supports("document_attachments"))Action("Retained receipts","receipts");else panel.Children.Add(CapabilityNotice());}
        var printable=FeatureCatalog.Documents.Contains(kind)||kind is "payment_in" or "payment_out" or "customer_refund" or "supplier_refund" or "advance_refund";
        if(printable)Action("PDF / print / share","pdf");
        if(printable&&Supports("thermal_receipts")&&kind is "sales_invoice" or "pos" or "payment_in" or "estimate" or "proforma" or "sales_order" or "credit_note"){Action("Receipt 80 mm","thermal_80");Action("Receipt 58 mm","thermal_58");}
        var cancelled=row.Flag("cancelled");
        if(!cancelled&&WhatsAppShare.Shareable(kind))Action("Share on WhatsApp","whatsapp");
        if(WhatsAppShare.CanRemind(row))Action("Send reminder","remind");
        if(cancelled)panel.Children.Add(Card(Text("Cancelled"+(data["cancelled"].Text("reason") is {Length:>0} why?" · "+why:"")+". The number stays in your records; its ledger, stock and balance effects were reversed.",13)));
        if(CanWrite&&!cancelled&&!lockedOrder&&row.Text("converted_to").Length==0&&(FeatureCatalog.Documents.Contains(kind)||kind is "payment_in" or "payment_out" or "bank_transfer"))Action("Edit","edit");
        var next=new List<UIElement>();
        void Next(string label,string key)=>next.Add(Button(label,()=>{action=key;CloseDialog();},next.Count==0));
        if(CanWrite&&WorkflowMasterValues.IsPostedRecord(row)&&row.Number("outstanding")>0&&kind is "sales_invoice" or "purchase_bill")Next(kind=="sales_invoice"?"Record payment received":"Record supplier payment","payment");
        if(CanWrite&&kind is "estimate" or "proforma"&&row.Text("converted_to").Length==0)Next("Convert to sales order","sales_order");
        if(CanWrite&&!cancelled&&receiving.Text("status") is "open" or "partial")Next("Receive stock","receive_po");
        if(supportsReceiving&&receivingError.Length>0)Next("Reload receiving details","reload_detail");
        if(CanWrite&&!lockedOrder&&Supports("recurring_drafts")&&FeatureCatalog.Drafts.Contains(kind)&&row.Text("converted_to").Length==0)Next("Create recurring draft schedule","recurring");
        var useLegacyConversion=!supportsReceiving||receiving.Text("status")=="unavailable";
        if(CanWrite&&!lockedOrder&&FeatureCatalog.Drafts.Contains(kind)&&row.Text("converted_to").Length==0&&useLegacyConversion)Next(kind=="purchase_order"?"Convert to purchase bill":"Convert to invoice","convert");
        if(CanWrite&&row.Flag("posted")&&kind is "sales_invoice" or "pos" or "purchase_bill")Next(kind=="purchase_bill"?"Create purchase return / debit note":"Create sales return / credit note","return");
        if(CanWrite&&(row.Number("advance_remaining")>0||row.Number("credit_remaining")>0))Next("Apply / refund available balance","settle");
        if(next.Count>0){panel.Children.Add(Text("Next steps",15,true));panel.Children.Add(ResponsiveGrid(238,next.ToArray()));}
        if(secondaryActions.Count>0)panel.Children.Add(ResponsiveGrid(170,secondaryActions.ToArray()));
        if(!CanWrite)panel.Children.Add(Text("Read-only access · ask an owner for editor access to record payments, returns or changes.",12));
        foreach(var (label,id) in new[]{("Posted document",row.Text("converted_to")),("Source document",data.Text("source_document_id")),("Purchase order",data.Text("purchase_order_id")),("Original invoice / bill",data.Text("applied_to"))}.Where(x=>x.Item2.Length>0&&x.Item2!="source-converted")){
            var linked=Records.FirstOrDefault(r=>r.Text("id")==id);var reference=linked.Text("number");
            panel.Children.Add(Button(label+"  ·  "+(reference.Length>0?reference:id[..Math.Min(8,id.Length)])+"  →",()=>{linkedId=id;action="linked";CloseDialog();}));
        }
        if(receiving is not null)panel.Children.Add(PurchaseReceivingSummary(receiving,id=>{linkedId=id;action="linked";CloseDialog();}));
        if(receivingError.Length>0)panel.Children.Add(Card(Text("Receiving details unavailable. "+receivingError)));
        var allocations=row["allocations"].Array();if(allocations.Count==0)allocations=data["allocations"].Array();
        if(allocations.Count>0){panel.Children.Add(Text("Payment allocation",15,true));foreach(var allocation in allocations){var id=allocation.Text("document_id");var target=Records.FirstOrDefault(r=>r.Text("id")==id);panel.Children.Add(Button(target.Text("number")+"  ·  "+J.Money(allocation.Number("amount"))+"  →",()=>{linkedId=id;action="linked";CloseDialog();}));}panel.Children.Add(Text("Allocation settles the document. Bank matching is a separate reconciliation step.",12));}
        if(data["lines"].Array().Count>0){panel.Children.Add(Text("Items",15,true));foreach(var line in data["lines"].Array()){var item=Stack(4);item.Children.Add(Text(line.Text("description"),14,true));item.Children.Add(Text(line.Text("quantity")+" "+line.Text("unit")+" × "+J.Money(line.Number("rate"))+"  ·  "+J.Money(line.Number("taxable")+line.Number("tax")),12));if(line is JsonObject lineValues&&lineValues.ContainsKey("discount_amount"))item.Children.Add(Text("Fixed line discount · "+J.Money(line.Number("discount_amount")),12));else if(line.Number("discount_percent")>0)item.Children.Add(Text("Line discount · "+line.Text("discount_percent")+"%",12));if(line.Number("document_discount")>0)item.Children.Add(Text("Document discount allocated to this line · "+J.Money(line.Number("document_discount")),12));panel.Children.Add(Card(item));}}
        if(data.Text("notes").Length>0){panel.Children.Add(Text("Notes",16,true));panel.Children.Add(Text(data.Text("notes")));}
        if(Supports("document_cancellation")&&CanWrite&&!cancelled&&row.Flag("posted")&&kind is "sales_invoice" or "pos" or "purchase_bill" or "payment_in" or "payment_out" or "expense" or "credit_note" or "debit_note" or "bank_transfer")
            panel.Children.Add(Button("Cancel this document",()=>{action="cancel";CloseDialog();}));
        await Dialog("Transaction details",panel,()=>Task.CompletedTask,"Done");
        if(stamp!=generation||cid!=CompanyId)return;
        switch(action){
            case "receipts":await RetainedReceipts(row);break;
            case "recurring":await RecurringTemplateForm(row);break;
            case "pdf":await PreviewDocument(row);break;
            case "thermal_80":case "thermal_58":await ShowDocumentPdf(row,action);break;
            case "whatsapp":case "remind":await OpenWhatsApp(row,action=="remind");break;
            case "edit":await EditRow(row);break;
            case "payment":await EditPayment(kind=="sales_invoice"?"payment_in":"payment_out",document:row);break;
            case "receive_po":if(receiving is not null)await ReceivePurchaseOrder(row,receiving);break;
            case "reload_detail":await TransactionDetails(row);break;
            case "sales_order":await EditDocument("sales_order",conversion:row);break;
            case "convert":await EditDocument(kind=="purchase_order"?"purchase_bill":"sales_invoice",conversion:row);break;
            case "return":await EditDocument(kind=="purchase_bill"?"debit_note":"credit_note",returnSource:row);break;
            case "settle":await SettleBalance(row.Number("credit_remaining")>0,row.Text("id"));break;
            case "cancel":await CancelDocument(row);break;
            case "linked":if(linkedId.Length>0)await TransactionDetails(new JsonObject{["id"]=linkedId});break;
        }
    }
}
