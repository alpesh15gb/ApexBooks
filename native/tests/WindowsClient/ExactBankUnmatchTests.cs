using System.Net;
using System.Text.Json.Nodes;
using ApexBooks_Windows.Services;

static class ExactBankUnmatchTests
{
    static JsonObject Line()=>new(){["id"]="line-a",["matched_record_id"]="record-a",["match_revision"]=7};
    public static async Task Run(Action<bool,string> check)
    {
        var legacy=Line();legacy.Remove("match_revision");var missingRejected=false;try{ExactBankUnmatch.CaptureBody(legacy);}catch(InvalidOperationException){missingRejected=true;}check(missingRejected,"exact unmatch refuses missing displayed revision without assuming zero");
        foreach(var malformed in new[]{"null","-1","1.5","true","\"7\"","1e0"}){var row=Line();row["match_revision"]=JsonNode.Parse(malformed);var rejected=false;try{ExactBankUnmatch.CaptureBody(row);}catch(InvalidOperationException){rejected=true;}check(rejected,"exact unmatch refuses malformed revision "+malformed);}
        var zero=Line();zero["match_revision"]=0;check(ExactBankUnmatch.CaptureBody(zero).Number("expected_match_revision")==0,"explicit server revision zero is valid");
        foreach(var capability in new[]{ClientCapabilities.Unavailable,ClientCapabilities.Checking,ClientCapabilities.TransientFailure,ClientCapabilities.Parse(new JsonObject{["capabilities_version"]=1,["supported_features"]=new JsonArray()})}){var rejected=false;try{capability.RequireBankMatchRevisionSupport();}catch(InvalidOperationException error){rejected=error.Message.Contains(capability.Hint);}check(rejected,"unverified exact-unmatch capability fails closed with metadata guidance");}
        var transport=new Transport{InterruptFirst=true};using(var api=new ApexApi("https://synthetic-unmatch.invalid",transport)){
            var row=Line();var intent=new ExactBankUnmatch(api,"company-a",row);var blocked=false;try{await intent.Remove(()=>true);}catch(InvalidOperationException){blocked=true;}check(blocked&&transport.Bodies.Count==0,"old server receives no unsafe exact-unmatch DELETE");
            await api.EnsureCapabilities();try{await intent.Remove(()=>true);}catch(ApiFailure error)when(error.Status==0){}
            row["matched_record_id"]="replacement-record";row["match_revision"]=9;row["id"]="replacement-line";await intent.Remove(()=>true);
            check(transport.Bodies.Count==2&&transport.Bodies.Distinct().Count()==1&&transport.Paths.All(path=>path=="/api/companies/company-a/bank-statement/line-a/match"),"exact-unmatch retry keeps immutable company line and byte-identical DELETE body");
            var captured=JsonNode.Parse(transport.Bodies[1])!;check(captured.Text("expected_record_id")=="record-a"&&captured.Number("expected_match_revision")==7&&transport.GetPaths.SequenceEqual(new[]{"/api/capabilities"}),"exact-unmatch never refreshes displayed match token before retry");
            transport.Conflict=true;var rejected=false;try{await intent.Remove(()=>true);}catch(ApiFailure error)when(error.Status==409){rejected=true;}check(rejected&&JsonNode.Parse(transport.Bodies.Last())!.Number("expected_match_revision")==7,"replacement or ABA match409 is surfaced without adopting newer token");
            var before=transport.Bodies.Count;var stale=new ExactBankUnmatch(api,"company-a",Line());try{await stale.Remove(()=>false);}catch(OperationCanceledException){}check(before==transport.Bodies.Count,"changed company or statement scope prevents exact unmatch before send");
            api.ForgetSession();await api.EnsureCapabilities();try{await stale.Remove(()=>true);}catch(OperationCanceledException){}check(before==transport.Bodies.Count,"replacement session prevents old exact-unmatch intent before send");
        }
        foreach(var signout in new[]{false,true}){
            var delayed=new Transport{Hold=true};using var api=new ApexApi("https://synthetic-unmatch.invalid",delayed);await api.EnsureCapabilities();var intent=new ExactBankUnmatch(api,"company-a",Line());var current=true;var pending=intent.Remove(()=>current);await delayed.Entered.Task;if(signout)api.ForgetSession();else current=false;delayed.Release.SetResult(true);var rejected=false;try{await pending;}catch(OperationCanceledException){rejected=true;}check(rejected,"late exact-unmatch completion cannot refresh another "+(signout?"session":"company view"));
        }
    }
    sealed class Transport:HttpMessageHandler
    {
        public bool InterruptFirst,Conflict,Hold;public List<string> Bodies=[],Paths=[],GetPaths=[];
        public TaskCompletionSource<bool> Entered=new(TaskCreationOptions.RunContinuationsAsynchronously),Release=new(TaskCreationOptions.RunContinuationsAsynchronously);
        protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request,CancellationToken cancellation)
        {
            if(request.Method==HttpMethod.Get){GetPaths.Add(request.RequestUri!.AbsolutePath);return new(HttpStatusCode.OK){Content=new StringContent("{\"capabilities_version\":1,\"supported_features\":[\"bank_match_revisions\"]}")};}
            if(request.Method!=HttpMethod.Delete)throw new InvalidOperationException("Expected DELETE");Paths.Add(request.RequestUri!.AbsolutePath);Bodies.Add(await request.Content!.ReadAsStringAsync(cancellation));
            if(Hold){Entered.SetResult(true);await Release.Task.WaitAsync(cancellation);}
            if(InterruptFirst&&Bodies.Count==1)throw new HttpRequestException("synthetic response lost");
            return Conflict?new(HttpStatusCode.Conflict){Content=new StringContent("{\"detail\":\"Bank match changed; reload the statement and review its current match\"}")}:new(HttpStatusCode.OK){Content=new StringContent("{\"matched_record_id\":null,\"match_revision\":8}")};
        }
    }
}
