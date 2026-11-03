using ApexBooks_Windows.Services;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using System.Text.Json.Nodes;
using static ApexBooks_Windows.Views.NativeUi;

namespace ApexBooks_Windows;
public sealed partial class MainPage
{
    private (StackPanel Panel,InlineMasterSubmission Submission) InlineMasterEditor(string kind,string cid,Func<bool> current,Action<JsonObject> created,Action cancelled)
    {
        var command=new InlineMasterSubmission(Api,cid);var date=J.Today;var panel=Stack(12);var inputs=Stack(10);var saving=false;
        panel.Children.Add(Text(kind=="party"?"Create customer for this invoice":"Create item for this invoice",22,true));
        panel.Children.Add(Text("This creates a saved master only. Your invoice remains an unsaved draft, with its existing entries preserved. A duplicate name is never selected automatically.",12));
        var name=Input(kind=="party"?"New customer name":"New item name");name.MaxLength=120;inputs.Children.Add(name);
        var phone=Input("New customer phone");phone.MaxLength=32;var address=Input("New customer billing address","",true);address.MaxLength=500;var gstin=Input("New customer GSTIN");gstin.MaxLength=15;
        var type=Select("New item type",[("services","Service · no stock"),("goods","Goods")],"services");var unit=Input("New item unit");unit.MaxLength=24;var rate=Input("New item sale rate (₹)","0");var gst=Input("New item GST rate (%)","0");
        var tracked=new CheckBox{Content="Track stock for goods · no opening stock is posted here",IsChecked=false,IsEnabled=false};
        var treatment=Select("New item supply classification",[("taxable","Taxable"),("nil_rated","Nil rated"),("exempt","Exempt"),("non_gst","Non-GST")],"nil_rated");
        void StockMode(){var goods=Value(type)=="goods";tracked.IsEnabled=InlineMasterSubmission.CanTrackStock(Value(type),InlineMasterSubmission.CanEditInputs(saving,command.Unresolved));if(!goods)tracked.IsChecked=false;}type.SelectionChanged+=(_,_)=>StockMode();StockMode();
        if(kind=="party"){inputs.Children.Add(phone);inputs.Children.Add(address);inputs.Children.Add(gstin);}else{inputs.Children.Add(type);inputs.Children.Add(unit);inputs.Children.Add(rate);inputs.Children.Add(gst);inputs.Children.Add(treatment);inputs.Children.Add(tracked);inputs.Children.Add(Text("Services cannot track stock. For goods choose tracking now; no opening quantity is posted. Review the new invoice line's rate, classification and GST before saving.",12));}
        void UpdateInputs(){var editable=InlineMasterSubmission.CanEditInputs(saving,command.Unresolved);inputs.IsHitTestVisible=editable;SetFormEnabled(inputs,editable);StockMode();}
        panel.Children.Add(inputs);var error=new InfoBar{IsClosable=false};panel.Children.Add(error);
        void ShowError(Exception failure){error.Severity=InfoBarSeverity.Error;error.Message=command.Unresolved?"The create outcome is unknown. Values are locked. Retry Create and use to recover the same master before leaving; do not create a replacement.":failure is ApiFailure{Status:409}?"That name is already used. Choose another name, or cancel and explicitly select the existing master after reviewing it.":failure.Message;error.IsOpen=true;}
        panel.Children.Add(AsyncButton("Create and use "+(kind=="party"?"customer":"item"),async()=>{
            if(!current()||!CanWrite)throw new InvalidOperationException("The original editable company is no longer active.");
            error.IsOpen=false;
            if(string.IsNullOrWhiteSpace(name.Text))throw new InvalidOperationException("Enter a name.");
            var values=kind=="party"?new JsonObject{["party_type"]="customer",["phone"]=phone.Text.Trim(),["address"]=address.Text.Trim(),["gstin"]=gstin.Text.Trim().ToUpperInvariant()}:new JsonObject{["item_type"]=Value(type),["unit"]=unit.Text.Trim(),["sale_rate"]=rate.Text.Trim(),["purchase_rate"]="0",["gst_rate"]=gst.Text.Trim(),["track_stock"]=Value(type)=="goods"&&tracked.IsChecked==true,["tax_treatment"]=Value(treatment)};
            values["is_active"]=true;
            saving=true;UpdateInputs();
            try{var result=await command.Save(new JsonObject{["kind"]=kind,["name"]=name.Text.Trim(),["date"]=date,["data"]=values},current);created(result);}
            finally{saving=false;UpdateInputs();}
        },ShowError,true));
        panel.Children.Add(AsyncButton("Cancel inline create",()=>{if(command.Unresolved)throw new InvalidOperationException("Recover the pending creation before leaving.");cancelled();return Task.CompletedTask;},ShowError));
        panel.Loaded+=(_,_)=>name.Focus(FocusState.Programmatic);return(panel,command);
    }
}
