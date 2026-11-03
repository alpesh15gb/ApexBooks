using System.Net;
using System.Text.Json.Nodes;
using ApexBooks_Windows.Services;

static class JournalSubmissionTests
{
    static JsonObject Body(bool reversal)=>reversal?new(){["date"]="2026-11-03",["reference"]="REV-1",["reason"]="Original reason"}:JsonNode.Parse("{\"date\":\"2026-11-03\",\"reference\":\"JRN-1\",\"memo\":\"Original memo\",\"lines\":[{\"account_id\":\"debit-account\",\"debit\":\"10\",\"credit\":\"0\"},{\"account_id\":\"credit-account\",\"debit\":\"0\",\"credit\":\"10\"}]}")!.AsObject();
    public static async Task Run(Action<bool,string> check)
    {
        foreach(var capability in new[]{ClientCapabilities.Unavailable,ClientCapabilities.Checking,ClientCapabilities.TransientFailure,ClientCapabilities.Parse(new JsonObject{["capabilities_version"]=1,["supported_features"]=new JsonArray()})}){var blocked=false;try{capability.RequireJournalIdempotency();}catch(InvalidOperationException error){blocked=error.Message.Contains(capability.Hint);}check(blocked,"journal posting fails closed with appropriate metadata/retry hint");}
        foreach(var reversal in new[]{false,true}){
            var transport=new Transport{LoseFirst=true,Reversal=reversal};using var api=new ApexApi("https://synthetic-journal.invalid",transport);var submission=new JournalSubmission(api,"company-a",reversal?"original-journal":null);var body=Body(reversal);
            var gated=false;try{await submission.Save(body,()=>true);}catch(InvalidOperationException){gated=true;}check(gated&&transport.Bodies.Count==0&&!submission.Unresolved,"unsupported journal command sends nothing and does not create pending state");
            await api.EnsureCapabilities();try{await submission.Save(body,()=>true);}catch(ApiFailure error)when(error.Status==0){}check(submission.Unresolved&&!submission.InputsEditable,"interrupted journal command retains unknown close/input lock");
            body["date"]="2026-11-04";body["reference"]="CHANGED";if(reversal)body["reason"]="Changed reason";else body["lines"]![0]!["debit"]="999";
            var result=await submission.Save(body,()=>true);
            check(!submission.Unresolved&&submission.InputsEditable&&result.Text("id")=="same-journal","201 replay confirms original journal and unlocks form");
            check(transport.Bodies.Count==2&&transport.Bodies.Distinct().Count()==1&&transport.Keys.Distinct().Count()==1&&transport.Keys.All(key=>key.Length is >=1 and <=80),"journal retry preserves exact date reference lines/reason and stable key");
            check(transport.Paths.Distinct().Single()==(reversal?"/api/companies/company-a/journals/original-journal/reverse":"/api/companies/company-a/journals"),"journal retry preserves company and original operation identity");
        }
        foreach(var status in new[]{409,500,422,403}){
            var transport=new Transport{Status=status};using var api=new ApexApi("https://synthetic-journal.invalid",transport);await api.EnsureCapabilities();var command=new JournalSubmission(api,"company-a");try{await command.Save(Body(false),()=>true);}catch(ApiFailure){}
            check(command.Unresolved==(status is 409 or 500)&&command.InputsEditable==(status is 422 or 403),"journal status "+status+" retains conservative409/unknown or permits definitive correction");
        }
        var rejections=new[]{
            "Journal retry key was used for a different request",
            "Journal reference already exists",
            "Journal is already reversed or is itself a reversal",
            "Reference already exists or journal was already reversed",
            "Date is in a locked accounting period",
            "Reverse source documents through their document workflow"};
        foreach(var message in rejections){
            foreach(var priorUnknown in new[]{false,true}){
                var transport=new Transport{Status=409,Detail=message,LoseFirst=priorUnknown};
                using var api=new ApexApi("https://synthetic-journal.invalid",transport);await api.EnsureCapabilities();var command=new JournalSubmission(api,"company-a");
                if(priorUnknown){try{await command.Save(Body(false),()=>true);}catch(ApiFailure){}}
                try{await command.Save(Body(false),()=>true);}catch(ApiFailure){}
                var review=priorUnknown||message==rejections[0];
                check(!command.Unresolved&&command.InputsEditable&&command.ReviewRequired==review,"exact journal rejection clears close lock and requires reconciliation when key bound or earlier outcome unknown: "+message);
                if(review){
                    var sent=transport.Bodies.Count;var blocked=false;
                    try{await command.Save(Body(false),()=>true);}catch(InvalidOperationException error){blocked=error.Message.Contains("may already have saved");}
                    check(blocked&&transport.Bodies.Count==sent,"journal review-required command cannot send or silently rotate its key");
                }else{
                    transport.Status=201;var corrected=Body(false);corrected["reference"]="CORRECTED";corrected["date"]="2026-11-04";
                    await command.Save(corrected,()=>true);
                    check(transport.Bodies.Count==2&&transport.Keys.Distinct().Count()==1&&JsonNode.Parse(transport.Bodies[1])!.Text("reference")=="CORRECTED","fresh definitive journal rejection permits edited correction with same unbound key");
                }
            }
        }
        foreach(var detail in new[]{"Unrelated financial conflict","Journal reference already exists ","journal reference already exists"}){
            var transport=new Transport{Status=409,Detail=detail};using var api=new ApexApi("https://synthetic-journal.invalid",transport);await api.EnsureCapabilities();var command=new JournalSubmission(api,"company-a");try{await command.Save(Body(false),()=>true);}catch(ApiFailure){}
            check(command.Unresolved&&!command.ReviewRequired&&!command.InputsEditable,"non-exact journal409 remains unknown and locked");
        }
        var wrongDate=new Transport{WrongDate=true};using(var api=new ApexApi("https://synthetic-journal.invalid",wrongDate)){
            await api.EnsureCapabilities();var command=new JournalSubmission(api,"company-a");var rejected=false;try{await command.Save(Body(false),()=>true);}catch(InvalidDataException){rejected=true;}
            check(rejected&&command.Unresolved&&!command.InputsEditable,"mismatched successful-create date remains unverified and unknown");
            wrongDate.WrongDate=false;await command.Save(Body(false),()=>true);
            check(!command.Unresolved&&wrongDate.Keys.Distinct().Count()==1&&wrongDate.Bodies.Distinct().Count()==1,"bad-date response recovery replays exact original command");
        }
        var delayed=new Transport{Hold=true};using(var api=new ApexApi("https://synthetic-journal.invalid",delayed)){
            await api.EnsureCapabilities();var command=new JournalSubmission(api,"company-a");var pending=command.Save(Body(false),()=>true);await delayed.Entered.Task;
            check(command.Saving&&!command.InputsEditable&&command.Unresolved,"journal in-flight request locks inputs and close state");var duplicateBlocked=false;try{await command.Save(Body(false),()=>true);}catch(InvalidOperationException){duplicateBlocked=true;}check(duplicateBlocked&&delayed.Bodies.Count==1,"journal concurrent double-submit is blocked");delayed.Release.SetResult(true);await pending;
        }
        foreach(var signout in new[]{false,true}){
            var transport=new Transport{Hold=true};using var api=new ApexApi("https://synthetic-journal.invalid",transport);await api.EnsureCapabilities();var command=new JournalSubmission(api,"company-a","original-journal");transport.Reversal=true;var current=true;var pending=command.Save(Body(true),()=>current);await transport.Entered.Task;if(signout)api.ForgetSession();else current=false;transport.Release.SetResult(true);var rejected=false;try{await pending;}catch(OperationCanceledException){rejected=true;}check(rejected&&command.Unresolved,"late journal completion cannot update replacement "+(signout?"session":"company/view"));
        }
        var scopeTransport=new Transport();using(var api=new ApexApi("https://synthetic-journal.invalid",scopeTransport)){
            await api.EnsureCapabilities();var command=new JournalSubmission(api,"company-a");try{await command.Save(Body(false),()=>false);}catch(OperationCanceledException){}check(scopeTransport.Bodies.Count==0,"stale company or withdrawn write role prevents journal send");api.ForgetSession();await api.EnsureCapabilities();try{await command.Save(Body(false),()=>true);}catch(OperationCanceledException){}check(scopeTransport.Bodies.Count==0,"old journal intent cannot send under replacement session");
        }
    }
    sealed class Transport:HttpMessageHandler
    {
        public bool LoseFirst,Hold,Reversal,WrongDate;public string Detail="Unrelated financial conflict";public int Status=201;public List<string> Bodies=[],Keys=[],Paths=[];
        public TaskCompletionSource<bool> Entered=new(TaskCreationOptions.RunContinuationsAsynchronously),Release=new(TaskCreationOptions.RunContinuationsAsynchronously);
        protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request,CancellationToken cancellation)
        {
            if(request.RequestUri!.AbsolutePath=="/api/capabilities")return new(HttpStatusCode.OK){Content=new StringContent("{\"capabilities_version\":1,\"supported_features\":[\"journal_idempotency\"]}")};
            if(request.Method!=HttpMethod.Post)throw new InvalidOperationException("Unexpected journal method");var body=await request.Content!.ReadAsStringAsync(cancellation);Bodies.Add(body);Keys.Add(request.Headers.GetValues("Idempotency-Key").Single());Paths.Add(request.RequestUri.AbsolutePath);
            if(Hold){Entered.SetResult(true);await Release.Task.WaitAsync(cancellation);}if(LoseFirst&&Bodies.Count==1)throw new HttpRequestException("synthetic response lost after commit");
            if(Status!=201)return new((HttpStatusCode)Status){Content=new StringContent(new JsonObject{["detail"]=Detail}.ToJsonString())};
            var result=new JsonObject{["id"]="same-journal",["reference"]=JsonNode.Parse(body)!.Text("reference").Trim()};if(Reversal)result["reversal_of"]="original-journal";else result["date"]=WrongDate?"2026-11-05":JsonNode.Parse(body)!.Text("date");return new(HttpStatusCode.Created){Content=new StringContent(result.ToJsonString())};
        }
    }
}
