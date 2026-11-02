using ApexBooks_Windows.Services;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using System.Net.Http;
using System.Text.Json.Nodes;
using static ApexBooks_Windows.Views.NativeUi;

namespace ApexBooks_Windows;
public sealed partial class MainPage
{
    private async Task CommercePage()
    {
        var cid=CompanyId;var stamp=generation;var root=Api.CompanyPath(cid,"/commerce/connections");
        var connections=(await Api.Send(root)).Array();if(stamp!=generation)return;
        var selection=Select("Bagisto store channel",connections.Select(c=>(c.Text("id"),c.Text("name")+" · "+c.Text("channel"))));
        var category=Select("Workspace",new[]{("overview","Overview"),("catalogue","Catalogue & mappings"),("orders","Store orders"),("payments","Payments, payouts & returns"),("deliveries","Delivery queues"),("reconciliation","Reconciliation")});
        JsonObject workspace=new();var loading=false;var loadVersion=0;
        var content=Stack(18);var tools=Stack();tools.Orientation=Orientation.Horizontal;
        tools.Children.Add(AsyncButton("Refresh",async()=>await Load(),Error));
        if(IsOwner)tools.Children.Add(AsyncButton("Connect Bagisto",async()=>{await CommerceConnect(cid);if(CompanyId==cid)await Navigate("commerce");},Error,true));
        Body.Children.Add(Text("Independent store channels and inventory pools for "+Company.Text("name")+". All transactions post through the shared accounting API.",13));
        Body.Children.Add(Columns(selection,category));Body.Children.Add(tools);Body.Children.Add(content);
        async Task Command(string operation,JsonObject? payload=null){await Api.Send(Api.CompanyPath(cid,$"/commerce/connections/{Value(selection)}/commands"),HttpMethod.Post,new JsonObject{["command_id"]=Guid.NewGuid().ToString(),["operation"]=operation,["payload"]=payload??new()});Success("Action queued. Delivery and accounting results appear below.");await Load();}
        async Task Load(){var selectedId=Value(selection);if(selectedId.Length==0){content.Children.Clear();content.Children.Add(Card(Text("Connect a Bagisto store to begin.")));return;}var current=++loadVersion;loading=true;try{var data=(await Api.Send(Api.CompanyPath(cid,$"/commerce/connections/{selectedId}/workspace"))).Object();if(stamp!=generation||current!=loadVersion||selectedId!=Value(selection))return;workspace=data;Draw();}finally{if(current==loadVersion)loading=false;}}
        void Draw(){
            content.Children.Clear();var connection=workspace["connection"].Object();var active=connection.Text("status")=="active";
            var status=Stack();status.Children.Add(Text(connection.Text("name")+" · "+Friendly(connection.Text("status")),20,true));status.Children.Add(Text(connection.Text("base_url")+" · INR · "+connection.Text("channel"),12));
            if(IsOwner){var actions=Stack();actions.Orientation=Orientation.Horizontal;actions.Children.Add(AsyncButton("Verify bridge",async()=>{await Api.Send(Api.CompanyPath(cid,$"/commerce/connections/{Value(selection)}/verify"),HttpMethod.Post);await Load();},Error));actions.Children.Add(AsyncButton(active?"Pause connection":"Activate connection",async()=>{await Api.Send(Api.CompanyPath(cid,$"/commerce/connections/{Value(selection)}/state"),HttpMethod.Put,new JsonObject{["status"]=active?"paused":"active"});await Load();},Error));status.Children.Add(actions);}content.Children.Add(Card(status));
            var kind=Value(category);
            if(kind=="overview"){
                var row=Stack();row.Children.Add(Text(workspace["orders"].Array().Count+" orders  ·  "+workspace["stock"].Array().Count+" mapped SKUs",20,true));row.Children.Add(Text("Checkout reserves stock first. Invoices post sales, GST and cost. Captures enter clearing; settlements transfer bank net and fees. Exceptions remain in the delivery review queue."));if(CanWrite){row.Children.Add(AsyncButton("Repair / scan store history",()=>Command("history.scan",new JsonObject{["after_id"]=0}),Error));row.Children.Add(AsyncButton("Reconcile store",()=>Command("reconcile.snapshot"),Error));}content.Children.Add(Card(row));
            }else if(kind=="catalogue"){
                var panel=Stack();panel.Children.Add(Text("Map products and customers",20,true));panel.Children.Add(Text("Use the exact source identity and SKU. Mappings can only select records in this company."));
                if(CanWrite){panel.Children.Add(AsyncButton("Read store catalogue",()=>Command("catalogue.scan"),Error));panel.Children.Add(AsyncButton("Add / review mapping",async()=>{await CommerceMap(cid,Value(selection),workspace);await Load();},Error));panel.Children.Add(AsyncButton("Publish prices & sellable stock",()=>Command("catalogue.publish"),Error));}
                foreach(var item in workspace["stock"].Array()){var line=Stack(5);line.Children.Add(Text(item.Text("name")+" · "+item.Text("sku"),14,true));line.Children.Add(Text("Book "+item.Text("book_quantity")+"  ·  Reserved "+item.Text("reserved_quantity")+"  ·  Sellable "+item.Text("available_quantity")+"  ·  "+J.Money(item.Number("sale_rate")),12));panel.Children.Add(Card(line));}
                var scan=workspace["outbox"].Array().FirstOrDefault(r=>r.Text("operation")=="catalogue.scan"&&r.Text("status")=="done");foreach(var item in scan?["result"]?["products"].Array()??new JsonArray())panel.Children.Add(Text("Store "+item.Text("external_id")+" · "+item.Text("sku")+" · "+item.Text("name"),12));content.Children.Add(Card(panel));
            }else if(kind=="orders"){
                foreach(var row in workspace["orders"].Array()){var order=row.Object();var panel=Stack(8);panel.Children.Add(Text(order.Text("number")+" · "+J.Money(order.Number("amount")),18,true));panel.Children.Add(Text(Friendly(order.Text("status"))+" · Source "+order.Text("external_id")));panel.Children.Add(AsyncButton("Open order",async()=>{await CommerceOrder(cid,Value(selection),order);await Load();},Error));content.Children.Add(Card(panel));}
                if(workspace["orders"].Array().Count==0)content.Children.Add(Card(Text("Accepted store orders will appear here after delivery.")));
            }else if(kind=="payments"){
                var panel=Stack();panel.Children.Add(Text("Payments, payouts & physical returns",20,true));panel.Children.Add(Text("Record confirmed captures, customer advances, cash refunds, gateway settlements and goods receipts. Source references prevent duplicate postings."));if(CanWrite)panel.Children.Add(AsyncButton("Record a source transaction",async()=>{await CommerceMoney(cid,Value(selection),workspace);await Load();},Error,true));content.Children.Add(Card(panel));
            }else if(kind=="deliveries"){
                foreach(var direction in new[]{"inbox","outbox"}){var panel=Stack();panel.Children.Add(Text(direction=="inbox"?"Store → Books":"Books → Store",20,true));foreach(var row in workspace[direction].Array()){var message=row.Object();var line=Stack(5);line.Children.Add(Text(Friendly(message.Text(direction=="inbox"?"event_type":"operation"))+" · "+Friendly(message.Text("status")),14,true));line.Children.Add(Text(message.Text(direction=="inbox"?"entity_id":"command_id"),11));if(message.Text("error").Length>0)line.Children.Add(Text(message.Text("error")));if(CanWrite&&message.Text("status") is "review" or "retry")line.Children.Add(AsyncButton("Retry delivery",async()=>{await Api.Send(Api.CompanyPath(cid,$"/commerce/connections/{Value(selection)}/retry/{direction}/{message.Text("id")}"),HttpMethod.Post);await Load();},Error));line.Children.Add(Text("Attempts: "+message.Text("attempts"),11));panel.Children.Add(Card(line));}content.Children.Add(Card(panel));}
            }else{
                var panel=Stack();panel.Children.Add(Text("Store reconciliation",20,true));if(CanWrite)panel.Children.Add(AsyncButton("Reconcile now",()=>Command("reconcile.snapshot"),Error,true));foreach(var row in workspace["reconciliations"].Array()){var r=row.Object();var report=r["report"].Object();panel.Children.Add(Text(Friendly(r.Text("status"))+" · "+r.Text("created_at"),14,true));panel.Children.Add(Text(report["stock_differences"].Array().Count+" stock differences · Source invoices "+J.Money(report["store"].Number("invoice_total"))+" · credits "+J.Money(report["store"].Number("credit_total"))));foreach(var diff in report["stock_differences"].Array())panel.Children.Add(Text("Product "+diff.Text("product_id")+": expected "+diff.Text("expected")+", store "+diff.Text("actual")));}content.Children.Add(Card(panel));
            }
        }
        selection.SelectionChanged+=async(_,_)=>{workspace=new();content.Children.Clear();await Run(Load);};category.SelectionChanged+=(_,_)=>Draw();
        var timer=new DispatcherTimer{Interval=TimeSpan.FromSeconds(5)};timer.Tick+=async(_,_)=>{if(!loading&&stamp==generation)await Run(Load);};leavePage=()=>timer.Stop();
        await Load();if(stamp==generation)timer.Start();
    }
    private async Task CommerceConnect(string cid)
    {
        var name=Input("Store name");var url=Input("Store HTTPS origin · https://shop.example.com");var channel=Input("Bagisto channel code","default");var bank=Select("Gateway clearing account",new[]{("default","Default bank clearing")}.Concat(Banks.Select(b=>(b.Text("id"),b.Text("name")))));
        var panel=Stack();panel.Children.Add(Text("This channel belongs to "+Company.Text("name")+". Other companies need separate channels and exclusive inventory sources."));foreach(var field in new UIElement[]{name,url,channel,bank})panel.Children.Add(field);JsonObject result=new();
        if(!await Dialog("Connect Bagisto",panel,async()=>{result=(await Api.Send(Api.CompanyPath(cid,"/commerce/connections"),HttpMethod.Post,new JsonObject{["name"]=name.Text.Trim(),["base_url"]=url.Text.Trim(),["channel"]=channel.Text.Trim(),["gateway_bank_id"]=Value(bank)})).Object();},"Create connection"))return;
        var setup=Stack();setup.Children.Add(Text("Shown once. Configure the Bagisto server, then verify and activate the connection."));var identity=Input("Connection ID",result.Text("id"));identity.IsReadOnly=true;setup.Children.Add(identity);var secret=new PasswordBox{Header="Server connection secret",Password=result.Text("setup_secret")};setup.Children.Add(secret);setup.Children.Add(Button("Copy server setup",()=>{var data=new Windows.ApplicationModel.DataTransfer.DataPackage();data.SetText(new JsonObject{["connection_id"]=result.Text("id"),["secret"]=secret.Password,["channel"]=result.Text("channel")}.ToJsonString());Windows.ApplicationModel.DataTransfer.Clipboard.SetContent(data);}));await Dialog("Save server setup",setup,()=>Task.CompletedTask,"I have saved this");secret.Password="";result.Clear();
    }
    private async Task CommerceMap(string cid,string connectionId,JsonObject workspace)
    {
        var kind=Select("Mapping type",new[]{("product","Product → Item"),("customer","Customer → Party")});var source=Input("Store identity");var sku=Input("Exact store SKU");var target=Select("Accounting record",Array.Empty<(string,string)>());var panel=Stack();
        void Targets(){target.Items.Clear();foreach(var row in Records.Where(r=>r.Text("kind")== (Value(kind)=="product"?"item":"party")))target.Items.Add(new ComboBoxItem{Tag=row.Text("id"),Content=row.Text("name")});if(target.Items.Count>0)target.SelectedIndex=0;sku.Visibility=Value(kind)=="product"?Visibility.Visible:Visibility.Collapsed;}
        kind.SelectionChanged+=(_,_)=>Targets();Targets();foreach(var field in new UIElement[]{kind,source,sku,target})panel.Children.Add(field);
        await Dialog("Store mapping",panel,async()=>{await Api.Send(Api.CompanyPath(cid,$"/commerce/connections/{connectionId}/links"),HttpMethod.Post,new JsonObject{["entity_type"]=Value(kind),["external_id"]=source.Text.Trim(),["record_id"]=Value(target),["sku"]=Value(kind)=="product"?sku.Text.Trim():""});});
    }
    private async Task CommerceOrder(string cid,string connectionId,JsonObject order)
    {
        var key=Guid.NewGuid().ToString();
        var panel=Stack();panel.Children.Add(Text(order.Text("number")+" · "+J.Money(order.Number("amount")),20,true));panel.Children.Add(Text("Enter quantities for one action. Source stock and invoiced balances are checked before posting."));
        var fields=new Dictionary<string,TextBox>();foreach(var line in order["snapshot"]?["items"].Array()??new JsonArray()){var field=Input(line.Text("name")+" · ordered "+line.Text("quantity")+", invoiced "+line.Text("invoiced")+", shipped "+line.Text("shipped"));fields[line.Text("id")]=field;panel.Children.Add(field);}
        var operation=Select("Order action",new[]{("order.invoice","Create invoice"),("order.ship","Create shipment"),("order.refund","Create credit / refund"),("order.cancel","Cancel unfulfilled order")});var carrier=Input("Carrier");var tracking=Input("Tracking number");foreach(var field in new UIElement[]{operation,carrier,tracking})panel.Children.Add(field);
        if(!CanWrite){await Dialog("Store order",panel,()=>Task.CompletedTask,"Close");return;}
        await Dialog("Store order",panel,async()=>{var items=new JsonObject();foreach(var pair in fields){if(string.IsNullOrWhiteSpace(pair.Value.Text))continue;if(!int.TryParse(pair.Value.Text,out var qty)||qty<0)throw new Exception("Enter whole-unit action quantities.");if(qty>0)items[pair.Key]=qty;}if(Value(operation)!="order.cancel"&&items.Count==0)throw new Exception("Enter at least one action quantity.");await Api.Send(Api.CompanyPath(cid,$"/commerce/connections/{connectionId}/commands"),HttpMethod.Post,new JsonObject{["command_id"]=key,["operation"]=Value(operation),["payload"]=new JsonObject{["order_id"]=order.Text("external_id"),["items"]=items,["carrier"]=carrier.Text,["tracking"]=tracking.Text}});},"Queue action");
    }
}


