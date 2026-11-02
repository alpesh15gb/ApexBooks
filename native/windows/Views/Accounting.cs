using ApexBooks_Windows.Services;
using ApexBooks_Windows.Views;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using System.Globalization;
using System.Net.Http;
using System.Text.Json.Nodes;
using static ApexBooks_Windows.Views.NativeUi;

namespace ApexBooks_Windows;
public sealed partial class MainPage
{
    private readonly Dictionary<string,string> bankSelections=new();
    private async Task BankPage()
    {
        var cid=CompanyId;var stamp=generation;var sequence=0;var bank=BankChoice(selected:bankSelections.GetValueOrDefault(cid,"default"));var date=new DateInput("Reconcile as of",J.Today);var opening=Input("Statement opening balance (₹)","0");var panel=Stack(18);
        string Query()=>"?bank_account_id="+Uri.EscapeDataString(Value(bank))+"&as_of="+date.Value;
        async Task Load()
        {
            var call=++sequence;var bid=Value(bank);var tasks=new[]{Api.Send(Api.CompanyPath(cid,"/bank-statement"+Query())),Api.Send(Api.CompanyPath(cid,"/bank-reconciliation"+Query()+"&opening_balance="+Uri.EscapeDataString(opening.Text))),Api.Send(Api.CompanyPath(cid,"/bank-reconciliation/reviews?bank_account_id="+Uri.EscapeDataString(bid))),Api.Send(Api.CompanyPath(cid,"/bank-statement?bank_account_id="+Uri.EscapeDataString(bid)))};await Task.WhenAll(tasks);if(stamp!=generation||call!=sequence)return;
            panel.Children.Clear();RenderReport(panel,await tasks[1],"Reconciliation");var lines=(await tasks[0]).Array();var allLines=(await tasks[3]).Array();var used=allLines.SelectMany(l=>l?["allocations"].Array()??new()).GroupBy(a=>a.Text("record_id")).ToDictionary(g=>g.Key,g=>g.Sum(a=>a.Number("amount")));
            foreach(var line in lines.OfType<JsonObject>())
            {
                var card=Stack();card.Children.Add(Text($"{line.Text("date")} · {line.Text("description")} · {J.Money(line.Number("amount"))}",15,true));card.Children.Add(Text(line.Text("reference"),12));
                foreach(var allocation in line["allocations"].Array().OfType<JsonObject>())
                {var a=allocation;var row=Records.FirstOrDefault(r=>r.Text("id")==a.Text("record_id"));var controls=Columns(Text($"{row.Text("number")} · {row.Text("name")} · {J.Money(a.Number("amount"))}"),AsyncButton("Remove match",async()=>{await Api.Send(Api.CompanyPath(cid,"/bank-statement/allocations/"+a.Text("id")),HttpMethod.Delete);await Load();},Error));if(CanWrite)card.Children.Add(controls);}
                if(CanWrite&&line.Text("matched_record_id").Length>0)card.Children.Add(AsyncButton("Unmatch",async()=>{await Api.Send(Api.CompanyPath(cid,$"/bank-statement/{line.Text("id")}/match"),HttpMethod.Delete);await Load();},Error));
                if(CanWrite&&line.Number("remaining_amount")>0&&line.Text("matched_record_id").Length==0)
                {
                    var candidates=Records.OfType<JsonObject>().Where(r=>r.Flag("posted")&&string.CompareOrdinal(r.Text("date"),date.Value)<=0&&BankMovement(r,bid)!=0&&Math.Sign(BankMovement(r,bid))==Math.Sign(line.Number("amount"))&&r.Number("amount")-used.GetValueOrDefault(r.Text("id"))>0&&!allLines.Any(l=>l.Text("matched_record_id")==r.Text("id"))).OrderByDescending(r=>r.Text("number").Length>0&&line.Text("reference").Contains(r.Text("number"),StringComparison.OrdinalIgnoreCase)).ToArray();
                    var choice=Select("Match posted transaction",new[]{("","Choose transaction")}.Concat(candidates.Select(r=>(r.Text("id"),$"{r.Text("number")} · {r.Text("name")} · {J.Money(r.Number("amount")-used.GetValueOrDefault(r.Text("id")))} available"))));var amount=Input("Match amount (₹)",line.Text("remaining_amount"));
                    choice.SelectionChanged+=(_,_)=>{var r=candidates.FirstOrDefault(r=>r.Text("id")==Value(choice));if(r is not null)amount.Text=Math.Min(line.Number("remaining_amount"),r.Number("amount")-used.GetValueOrDefault(r.Text("id"))).ToString(CultureInfo.InvariantCulture);};
                    card.Children.Add(Columns(choice,amount));card.Children.Add(AsyncButton("Allocate match",async()=>{await Api.Send(Api.CompanyPath(cid,$"/bank-statement/{line.Text("id")}/allocations"),HttpMethod.Post,new JsonObject{["record_id"]=Value(choice),["amount"]=amount.Text});await Load();},Error));
                }
                panel.Children.Add(Card(card));
            }
            Table(panel,(await tasks[2]).Array(),"Saved dated reviews");
            panel.Children.Add(Text("Posted bank transactions",20,true));
            foreach(var row in Records.OfType<JsonObject>().Where(r=>r.Flag("posted")&&BankMovement(r,bid)!=0&&string.CompareOrdinal(r.Text("date"),date.Value)<=0))
            {
                var transaction=row;var card=Stack();card.Children.Add(Text($"{row.Text("date")} · {row.Text("number")} · {row.Text("name")} · {J.Money(BankMovement(row,bid))}",14,true));
                if(CanWrite&&row.Text("kind")=="bank_transfer")card.Children.Add(AsyncButton("Edit transfer",async()=>await Transfer(bid,(await Api.Record(cid,transaction.Text("id"))).Object()),Error));
                panel.Children.Add(Card(card));
            }
        }
        Body.Children.Add(Columns(bank,date.View,opening));var actions=new StackPanel{Orientation=Orientation.Horizontal,Spacing=10};actions.Children.Add(AsyncButton("Reconcile",Load,Error,true));
        if(CanWrite){actions.Children.Add(AsyncButton("New bank account",async()=>{await BankAccountForm();await Refresh();},Error));actions.Children.Add(AsyncButton("Cash / bank transfer",()=>Transfer(Value(bank)),Error));actions.Children.Add(AsyncButton("Import statement CSV",async()=>{await ImportStatement(Value(bank));await Load();},Error));actions.Children.Add(AsyncButton("Save review",async()=>{var note=Input("Review note","",true);if(await Dialog("Save reconciliation review",note,async()=>{await Api.Send(Api.CompanyPath(cid,"/bank-reconciliation/reviews"),HttpMethod.Post,new JsonObject{["bank_account_id"]=Value(bank),["as_of"]=date.Value,["opening_balance"]=opening.Text,["note"]=note.Text});},"Save review"))await Load();},Error));}
        actions.Children.Add(AsyncButton("Cash book",CashBook,Error));Body.Children.Add(actions);Body.Children.Add(panel);bank.SelectionChanged+=async(_,_)=>{bankSelections[cid]=Value(bank);await Run(Load);};await Load();
    }

    private static decimal BankMovement(JsonObject row,string bank)
    {
        var d=row["data"];var kind=row.Text("kind");var source=d.Text("bank_account_id") is {Length:>0} id?id:"default";
        if(kind=="bank_transfer"){if(d.Text("direction")=="bank_to_bank")return d.Text("to_bank_account_id")==bank?row.Number("amount"):source==bank?-row.Number("amount"):0;if(source!=bank)return 0;return d.Text("direction")=="cash_to_bank"?row.Number("amount"):-row.Number("amount");}
        if(d.Text("payment_account")!="bank"||source!=bank)return 0;
        return kind is "payment_in" or "pos" or "supplier_refund"||kind=="advance_refund"&&d.Text("payment_kind")=="payment_out"?row.Number("amount"):kind is "payment_out" or "expense" or "customer_refund" or "advance_refund"?-row.Number("amount"):0;
    }
    private async Task BankAccountForm()
    {var cid=CompanyId;var name=Input("Bank account name");var hint=Input("Account hint · last digits only");var panel=Stack();panel.Children.Add(name);panel.Children.Add(hint);await Dialog("Add bank account",panel,async()=>{var created=await Api.Send(Api.CompanyPath(cid,"/bank-accounts"),HttpMethod.Post,new JsonObject{["name"]=name.Text,["account_hint"]=hint.Text});bankSelections[cid]=created.Text("id");});}
    private async Task Transfer(string selected="default",JsonObject? previous=null)
    {
        var cid=CompanyId;var data=previous?["data"].Object()??new();
        var direction=Select("Direction",[("cash_to_bank","Cash to bank"),("bank_to_cash","Bank to cash"),("bank_to_bank","Bank to bank")],data.Text("direction"));
        var source=BankChoice("Deposit into bank",data.Text("bank_account_id") is {Length:>0} id?id:selected);var target=BankChoice("To bank",data.Text("to_bank_account_id"));
        void ShowDirection(){source.Header=Value(direction) switch{"cash_to_bank"=>"Deposit into bank","bank_to_cash"=>"Withdraw from bank",_=>"From bank"};target.Visibility=Value(direction)=="bank_to_bank"?Visibility.Visible:Visibility.Collapsed;}
        direction.SelectionChanged+=(_,_)=>ShowDirection();ShowDirection();
        var date=new DateInput("Date",previous.Text("date") is {Length:>0} day?day:J.Today);var amount=Input("Amount (₹)",previous.Text("amount"));var memo=Input("Description",previous is null?"Cash / bank transfer":previous.Text("name"));
        var panel=Stack();foreach(var field in new UIElement[]{direction,source,target,date.View,amount,memo})panel.Children.Add(field);var key=Guid.NewGuid().ToString();
        if(await Dialog(previous is null?"Cash and bank transfer":"Edit bank transfer",panel,async()=>{
            var values=new JsonObject{["direction"]=Value(direction),["bank_account_id"]=Value(source)};
            if(Value(direction)=="bank_to_bank")values["to_bank_account_id"]=Value(target);
            if(previous is not null)values["version"]=data["version"].Copy()??JsonValue.Create(0);
            await Api.SaveRecord(cid,new JsonObject{["kind"]="bank_transfer",["name"]=memo.Text,["number"]=previous.Text("number"),["date"]=date.Value,["amount"]=amount.Text,["data"]=values},key,previous);
        },previous is null?"Post transfer":"Save changes"))await Refresh();
    }
    private async Task CashBook()
    {
        var cid=CompanyId;var from=new DateInput("From",J.FinancialStart);var to=new DateInput("To",J.Today);var account=BankChoice("Bank account · cash is included");var panel=Stack();var result=Stack();
        string Path(string extension="")=>Api.CompanyPath(cid,$"/cash-book{extension}?from_date={from.Value}&to_date={to.Value}&bank_account_id={Uri.EscapeDataString(Value(account))}");
        async Task Load(){var value=await Api.Send(Path());result.Children.Clear();RenderReport(result,value);}
        panel.Children.Add(Columns(from.View,to.View,account));panel.Children.Add(AsyncButton("Apply",Load,Error,true));foreach(var fmt in new[]{"pdf","xlsx"})panel.Children.Add(AsyncButton("Export "+fmt,async()=>{await ApexFiles.Save(await Api.Download(Path("."+fmt)),"cash-book."+fmt);},Error));panel.Children.Add(result);await Load();await Dialog("Cash and bank book",panel,()=>Task.CompletedTask,"Done");
    }

    private async Task LedgerPage()
    {
        var cid=CompanyId;var stamp=generation;var accountsTask=Api.Send(PathFor("/accounts"));var journalTask=Api.Send(PathFor("/journals"));var trialTask=Api.Send(PathFor("/trial-balance"));await Task.WhenAll(accountsTask,journalTask,trialTask);if(stamp!=generation)return;
        var accounts=(await accountsTask).Array();var journals=(await journalTask).Array();var actions=new StackPanel{Orientation=Orientation.Horizontal,Spacing=12};
        if(CanWrite){actions.Children.Add(AsyncButton("Add ledger account",async()=>{var code=Input("Account code");var name=Input("Account name");var category=Select("Category",new[]{"asset","liability","equity","income","expense"}.Select(x=>(x,Friendly(x))));var panel=Stack();foreach(var field in new UIElement[]{code,name,category})panel.Children.Add(field);if(await Dialog("Add account",panel,async()=>{await Api.Send(Api.CompanyPath(cid,"/accounts"),HttpMethod.Post,new JsonObject{["code"]=code.Text,["name"]=name.Text,["category"]=Value(category)});}))await Refresh();},Error));actions.Children.Add(AsyncButton("New journal",()=>JournalForm(accounts),Error,true));}
        Body.Children.Add(actions);RenderReport(Body,await trialTask,"Trial balance");Table(Body,accounts,"Chart of accounts");
        foreach(var journal in journals.OfType<JsonObject>()){var card=Stack();card.Children.Add(Text($"{journal.Text("date")} · {journal.Text("reference")}",16,true));card.Children.Add(Text(journal.Text("memo")));var lines=new JsonArray();foreach(var line in journal["lines"].Array()){var row=line.Object().DeepClone().AsObject();row["account"]=accounts.FirstOrDefault(a=>a.Text("id")==line.Text("account_id")).Text("name");lines.Add(row);}Table(card,lines,columns:["account","debit","credit"]);if(CanWrite&&journal.Text("source_record_id").Length==0&&journal.Text("reversed_by").Length==0&&journal.Text("reversal_of").Length==0)card.Children.Add(AsyncButton("Reverse journal",()=>ReverseJournal(journal),Error));Body.Children.Add(Card(card));}
    }
    private async Task JournalForm(JsonArray accounts)
    {
        var cid=CompanyId;var panel=Stack();panel.MinWidth=700;var date=new DateInput("Date",J.Today);var reference=Input("Unique reference");var memo=Input("Memo");panel.Children.Add(Columns(date.View,reference));panel.Children.Add(memo);var rows=new List<(ComboBox Account,TextBox Debit,TextBox Credit)>();var holder=Stack();
        void Add(){var account=Select("Account",accounts.Select(a=>(a.Text("id"),a.Text("code")+" · "+a.Text("name"))));var debit=Input("Debit (₹)","0");var credit=Input("Credit (₹)","0");var row=Columns(account,debit,credit);rows.Add((account,debit,credit));holder.Children.Add(row);var remove=Button("Remove line",()=>{rows.Remove((account,debit,credit));holder.Children.Remove(row);});row.ColumnDefinitions.Add(new ColumnDefinition{Width=GridLength.Auto});Grid.SetColumn(remove,3);row.Children.Add(remove);}
        Add();Add();panel.Children.Add(holder);panel.Children.Add(Button("Add line",Add));if(await Dialog("Balanced journal entry",panel,async()=>{await Api.Send(Api.CompanyPath(cid,"/journals"),HttpMethod.Post,new JsonObject{["date"]=date.Value,["reference"]=reference.Text,["memo"]=memo.Text,["lines"]=new JsonArray(rows.Select(r=>(JsonNode)new JsonObject{["account_id"]=Value(r.Account),["debit"]=r.Debit.Text,["credit"]=r.Credit.Text}).ToArray())});},"Post journal"))await Refresh();
    }
    private async Task ReverseJournal(JsonObject journal)
    {var cid=CompanyId;var panel=Stack();var date=new DateInput("Reversal date",J.Today);var reference=Input("Reversal reference");var reason=Input("Reason","",true);panel.Children.Add(Text("The original journal stays in the audit history. This posts an equal opposite journal."));foreach(var field in new UIElement[]{date.View,reference,reason})panel.Children.Add(field);if(await Dialog("Reverse "+journal.Text("reference"),panel,async()=>{await Api.Send(Api.CompanyPath(cid,$"/journals/{journal.Text("id")}/reverse"),HttpMethod.Post,new JsonObject{["date"]=date.Value,["reference"]=reference.Text,["reason"]=reason.Text});},"Post reversal"))await Refresh();}
}
