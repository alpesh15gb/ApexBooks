using ApexBooks_Windows.Models;
using ApexBooks_Windows.Services;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using System.Net.Http;
using System.Text.Json.Nodes;
using static ApexBooks_Windows.Views.NativeUi;

namespace ApexBooks_Windows;

public sealed partial class MainPage
{
    private async Task RecurringDrafts()
    {
        RequireFeature("recurring_drafts");
        var cid=CompanyId;var stamp=generation;var panel=Stack(14);var rows=Stack(12);var loaded=new List<JsonObject>();var sequence=0;var businessDate="";string action="";JsonObject? selected=null;
        var view=Select("Show",[("due","Due for review"),("all","All schedules")]);var asOf=new DateInput("Review as of · blank uses server business date","");var search=Input("Find schedule or party");
        panel.Children.Add(Text("Recurring drafts · review before posting",22,true));panel.Children.Add(Text("Schedules create only estimates, proformas or orders when you explicitly generate a due occurrence. They do not automatically invoice, post expenses, move stock or run in the background.",13));
        void Choose(string command,JsonObject row){action=command;selected=row;CloseDialog();}
        void Draw()
        {
            rows.Children.Clear();var matches=loaded.Where(r=>(r.Text("name")+" "+r.Text("party_name")).Contains(search.Text.Trim(),StringComparison.OrdinalIgnoreCase)).ToList();
            rows.Children.Add(Text($"Showing {Math.Min(matches.Count,100)} of {matches.Count} matching schedules",12));
            foreach(var row in matches.Take(100)){
                var card=Stack(8);card.Children.Add(Text(row.Text("name"),18,true));card.Children.Add(Text($"{Friendly(row.Text("draft_kind"))} · {row.Text("party_name")} · {(!row.Flag("is_active")?"Paused":row.Text("next_due").Length==0?"Completed":"Active")}",13));
                card.Children.Add(Text($"Every {row.Text("interval")} {row.Text("frequency")} · next due {(row.Text("next_due").Length>0?row.Text("next_due"):"none")} · generated {row.Text("generated_count")}",12));
                if(row.Number("overdue_days")>0)card.Children.Add(Text($"{row.Number("overdue_days"):0} days overdue · generate and review one occurrence at a time",12));
                var buttons=new StackPanel{Orientation=Orientation.Horizontal,Spacing=8};buttons.Children.Add(Button("View schedule",()=>Choose("view",row)));
                if(CanWrite){buttons.Children.Add(Button("Edit / pause / resume",()=>Choose("edit",row)));var generate=Button("Generate next due draft",()=>Choose("generate",row),true);generate.IsEnabled=WorkflowMasterValues.RecurringOccurrenceAllowed(row.Flag("is_active"),row.Text("next_due"),businessDate);buttons.Children.Add(generate);}
                card.Children.Add(buttons);rows.Children.Add(Card(card));
            }
            if(matches.Count==0)rows.Children.Add(Text("No schedules match this view. Create one from a saved estimate, proforma, sales order or purchase order. Paused and completed schedules appear in All schedules.",13));
        }
        var calendarLabel=Text("Loading server business calendar…",12);
        async Task Load(){
            var request=++sequence;var filter=Value(view);var query=asOf.Value.Length>0?"?as_of="+asOf.Value:"";
            var dueTask=Api.Send(Api.CompanyPath(cid,"/recurring-templates/due"+query));var listTask=filter=="due"?dueTask:Api.Send(Api.CompanyPath(cid,"/recurring-templates"));await Task.WhenAll(dueTask,listTask);
            if(cid!=CompanyId||stamp!=generation||request!=sequence)return;
            var context=await dueTask;var result=await listTask;businessDate=context.Text("business_date");
            calendarLabel.Text=$"Server business date {businessDate} · {context.Text("timezone")} · review as of {context.Text("as_of")}. Future preview never enables generation.";
            if(asOf.Value.Length==0&&DateTime.TryParseExact(context.Text("as_of"),"yyyy-MM-dd",System.Globalization.CultureInfo.InvariantCulture,System.Globalization.DateTimeStyles.None,out var serverDate))asOf.Picker.Date=new DateTimeOffset(serverDate);
            loaded=result[filter=="due"?"rows":"templates"].Array().OfType<JsonObject>().ToList();Draw();
        }
        panel.Children.Add(calendarLabel);
        panel.Children.Add(Columns(view,asOf.View,AsyncButton("Refresh schedules",Load,Error)));panel.Children.Add(Text("Use Refresh schedules after changing the view or review date. Generate always uses the server’s next due date and never a future occurrence.",12));panel.Children.Add(search);search.TextChanged+=(_,_)=>Draw();panel.Children.Add(rows);
        if(CanWrite){var sources=Select("Source draft",new[]{("","Choose a saved draft")}.Concat(Records.Where(r=>FeatureCatalog.Drafts.Contains(r.Text("kind"))&&r.Text("converted_to").Length==0).Select(r=>(r.Text("id"),r.Text("number")+" · "+r.Text("name")))));panel.Children.Add(sources);panel.Children.Add(Button("Create recurring schedule",()=>{var source=Records.FirstOrDefault(r=>r.Text("id")==Value(sources));if(source is null){Error(new Exception("Choose a saved source draft."));return;}Choose("create",source.Object());},true));}
        else panel.Children.Add(Text("Read-only access · owners and editors can manage schedules and generate drafts.",12));
        await Load();if(cid!=CompanyId||stamp!=generation)return;await Dialog("Recurring drafts",panel,()=>Task.CompletedTask,"Done");if(cid!=CompanyId||stamp!=generation||selected is null)return;
        if(action=="create")await RecurringTemplateForm(selected);
        else if(action=="generate")await GenerateRecurringDraft(selected,businessDate);
        else await RecurringTemplateDetails(selected,action=="edit");
    }

    private async Task RecurringTemplateForm(JsonObject source)
    {
        RequireFeature("recurring_drafts");
        var writeAccess=CaptureRecurringWriteAccess();
        var cid=CompanyId;var stamp=generation;var calendar=await Api.Send(Api.CompanyPath(cid,"/recurring-templates/due"));if(cid!=CompanyId||stamp!=generation)return;var panel=Stack(12);var name=Input("Schedule name",source.Text("number")+" · "+source.Text("name"));name.MaxLength=120;
        var start=new DateInput("First occurrence",calendar.Text("business_date"));var end=new DateInput("End date · optional","");var frequency=Select("Frequency",[("monthly","Monthly"),("weekly","Weekly")]);var interval=Input("Every · interval (1–12)","1");
        panel.Children.Add(Text("Source: "+Friendly(source.Text("kind"))+" · "+source.Text("number")+" · "+source.Text("name"),15,true));panel.Children.Add(Text("A snapshot of this saved draft is used for future occurrences. Dates are anchored by the server; short months clamp to the final valid day. Schedules never post automatically. To change frequency or dates later, pause this schedule and create a replacement.",13));
        foreach(var field in new UIElement[]{name,Columns(start.View,end.View),Columns(frequency,interval)})panel.Children.Add(field);
        var key=Guid.NewGuid().ToString();var submission=new RetrySubmission();
        string Signature()=>name.Text+"|"+start.Value+"|"+end.Value+"|"+Value(frequency)+"|"+interval.Text;var baseline=Signature();
        var saved=await Dialog("Create recurring draft schedule",panel,async()=>{
            writeAccess();
            if(!submission.Unresolved){if(name.Text.Trim().Length==0)throw new Exception("Enter a schedule name.");WorkflowMasterValues.RecurringInterval(interval.Text);if(start.Value.Length==0)throw new Exception("Choose the first occurrence date.");if(end.Value.Length>0&&string.CompareOrdinal(end.Value,start.Value)<0)throw new Exception("End date must not precede the first occurrence.");}
            var body=new JsonObject{["name"]=name.Text.Trim(),["source_record_id"]=source.Text("id"),["start_date"]=start.Value,["frequency"]=Value(frequency),["interval"]=WorkflowMasterValues.RecurringInterval(interval.Text),["end_date"]=end.Value.Length==0?null:JsonValue.Create(end.Value),["is_active"]=true};
            try{await Api.Send(Api.CompanyPath(cid,"/recurring-templates"),HttpMethod.Post,submission.Body(body),key);submission.Succeeded();}catch(Exception e){WorkflowMasterValues.RecurringWriteFailed(submission,e);SetFormEnabled(panel,!submission.Unresolved);if(submission.Unresolved)throw new Exception("The schedule may already exist. Retry Save with the original details before closing or creating a replacement.",e);throw;}
        },"Save schedule",canSave:()=>CanWrite&&ScopedFileExport.Current(writeAccess),unresolved:()=>submission.Unresolved,hasChanges:()=>Signature()!=baseline);
        if(saved&&cid==CompanyId&&stamp==generation){Success("Recurring draft schedule saved. No transaction has been posted.");await RecurringDrafts();}
    }

    private async Task RecurringTemplateDetails(JsonObject summary,bool edit)
    {
        var cid=CompanyId;var stamp=generation;var id=summary.Text("id");var row=(await Api.Send(Api.CompanyPath(cid,"/recurring-templates/"+Uri.EscapeDataString(id)))).Object();if(cid!=CompanyId||stamp!=generation)return;
        var panel=Stack(12);var name=Input("Schedule name",row.Text("name"));name.MaxLength=120;var active=new CheckBox{Content="Active schedule",IsChecked=row.Flag("is_active")};
        panel.Children.Add(Text($"{Friendly(row.Text("draft_kind"))} · {row.Text("party_name")} · next due {row.Text("next_due")}",16,true));panel.Children.Add(Text($"Every {row.Text("interval")} {row.Text("frequency")} from {row.Text("start_date")} through {(row.Text("end_date").Length>0?row.Text("end_date"):"no end date")}",13));panel.Children.Add(Text("Schedule dates and frequency cannot be changed. Pause and create a replacement for a different schedule. Generating requires a separate explicit action.",12));
        panel.Children.Add(name);panel.Children.Add(active);var refresh=new CheckBox{Content="Refresh future draft snapshot from a saved draft",IsChecked=false};var source=Select("Future snapshot source",new[]{("","Keep existing snapshot")}.Concat(Records.Where(r=>r.Text("kind")==row.Text("draft_kind")&&r.Text("converted_to").Length==0).Select(r=>(r.Text("id"),r.Text("number")+" · "+r.Text("name")))),row.Text("source_record_id"));panel.Children.Add(refresh);panel.Children.Add(source);panel.Children.Add(Text("Refreshing affects only future occurrences; generated drafts and posted records are not rewritten.",12));
        var draft=row["draft"].Object();foreach(var line in draft["data"]?["lines"].Array()??new())panel.Children.Add(Text(line.Text("description")+" · "+line.Text("quantity")+" × "+J.Money(line.Number("rate")),12));
        if(!edit||!CanWrite){SetFormEnabled(panel,false);await Dialog("Recurring draft snapshot",panel,()=>Task.CompletedTask,"Done");return;}
        var writeAccess=CaptureRecurringWriteAccess();
        var key=Guid.NewGuid().ToString();var submission=new RetrySubmission();string Signature()=>name.Text+"|"+active.IsChecked+"|"+refresh.IsChecked+"|"+Value(source);var baseline=Signature();
        var saved=await Dialog("Manage recurring schedule",panel,async()=>{
            writeAccess();
            if(!submission.Unresolved&&name.Text.Trim().Length==0)throw new Exception("Enter a schedule name.");var body=new JsonObject{["version"]=row["version"].Copy(),["name"]=name.Text.Trim(),["is_active"]=active.IsChecked==true};
            if(refresh.IsChecked==true){if(Value(source).Length==0)throw new Exception("Choose the saved draft whose snapshot should be used.");body["source_record_id"]=Value(source);}
            try{await Api.Send(Api.CompanyPath(cid,"/recurring-templates/"+Uri.EscapeDataString(id)),HttpMethod.Put,submission.Body(body),key);submission.Succeeded();}catch(Exception e){WorkflowMasterValues.RecurringWriteFailed(submission,e);SetFormEnabled(panel,!submission.Unresolved);if(submission.Unresolved)throw new Exception("The schedule change has an unknown outcome. Retry the original change before closing.",e);throw;}
        },"Save schedule changes",canSave:()=>CanWrite&&ScopedFileExport.Current(writeAccess),unresolved:()=>submission.Unresolved,hasChanges:()=>Signature()!=baseline);
        if(saved&&cid==CompanyId&&stamp==generation)await RecurringDrafts();
    }

    private async Task GenerateRecurringDraft(JsonObject template,string businessDate)
    {
        var writeAccess=CaptureRecurringWriteAccess();
        var cid=CompanyId;var stamp=generation;var date=template.Text("next_due");if(!WorkflowMasterValues.RecurringOccurrenceAllowed(template.Flag("is_active"),date,businessDate))throw new Exception("Only an active schedule's next due occurrence, on or before the server business date, can be generated.");
        var panel=Stack(12);panel.Children.Add(Text(template.Text("name"),20,true));panel.Children.Add(Text($"Generate {Friendly(template.Text("draft_kind"))} dated {date} for {template.Text("party_name")}. Server business date: {businessDate} (Asia/Kolkata). This creates a draft only; no invoice, expense or stock movement is posted.",14));panel.Children.Add(Text("After generation, review the saved draft in the editor. Convert or post it only through its normal explicit workflow.",12));
        var key=Guid.NewGuid().ToString();var submission=new RetrySubmission();JsonObject? generated=null;
        var saved=await Dialog("Generate next due draft",panel,async()=>{
            writeAccess();
            try{var response=await Api.Send(Api.CompanyPath(cid,$"/recurring-templates/{Uri.EscapeDataString(template.Text("id"))}/occurrences"),HttpMethod.Post,submission.Body(new JsonObject{["occurrence_date"]=date}),key);generated=response["record"].Object();if(generated.Text("id").Length==0||!FeatureCatalog.Drafts.Contains(generated.Text("kind")))throw new ApiFailure(502,"The server did not return the generated draft. Retry to recover the same occurrence.");submission.Succeeded();}catch(Exception e){WorkflowMasterValues.RecurringWriteFailed(submission,e);if(submission.Unresolved)throw new Exception("The draft may already have been generated. Retry this original date to recover it; do not create another occurrence.",e);throw;}
        },"Generate draft for review",canSave:()=>CanWrite&&ScopedFileExport.Current(writeAccess),unresolved:()=>submission.Unresolved);
        if(saved&&generated is not null&&cid==CompanyId&&stamp==generation)await ReviewGeneratedRecurringDraft(generated);
    }
    private async Task ReviewGeneratedRecurringDraft(JsonObject generated)
    {
        var cid=CompanyId;var workspace=workspaceGeneration;var session=Api.SessionGeneration;var page=CurrentPage;var navigation=generation;
        var id=generated.Text("id");var reference=generated.Text("number");if(reference.Length==0)reference=id;
        bool Current()=>Api.SignedIn&&Api.SessionGeneration==session&&cid==CompanyId&&workspace==workspaceGeneration&&page==CurrentPage&&navigation==generation;
        JsonObject? fresh=null;
        async Task Reload(){
            if(!Current())return;
            var before=navigation;
            try{await Refresh();}finally{if(generation==before+1&&CurrentPage==page)navigation=generation;}
            if(!Current())return;
            var access=saveAccessEpoch;
            var result=(await Api.Record(cid,id)).Object();if(!Current()||access!=saveAccessEpoch||!recordsReady)return;
            if(result.Text("id")!=id||!FeatureCatalog.Drafts.Contains(result.Text("kind")))throw new ApiFailure(409,"The saved record needs review in the document list.");
            fresh=result;
        }
        try{await Reload();}
        catch(OperationCanceledException){throw;}
        catch(Exception error){
            if(!Current())return;
            var panel=Stack(12);panel.Children.Add(Text("Draft "+reference+" is saved. No invoice or stock posting occurred. Do not generate another occurrence to recover it.",16,true));
            panel.Children.Add(Text("The saved draft could not be opened: "+error.Message,13));
            panel.Children.Add(Text("Refresh and open only reads company data and this saved draft. You can also cancel and find it later in its document list.",13));
            if(!await Dialog("Scheduled draft saved · review pending",panel,async()=>{
                try{await Reload();}catch(OperationCanceledException){throw;}catch(Exception retryError){if(Current())throw new ApiFailure((retryError as ApiFailure)?.Status??0,"Draft "+reference+" remains saved. Refresh/open failed; no occurrence was generated again. "+retryError.Message);}
            },"Refresh and open saved draft",canSave:Current))return;
        }
        if(!Current()||fresh is null)return;
        if(CanWrite&&!fresh.Flag("cancelled")&&fresh.Text("converted_to").Length==0)await EditDocument(fresh.Text("kind"),previous:fresh);
        else await TransactionDetails(fresh);
    }

}
