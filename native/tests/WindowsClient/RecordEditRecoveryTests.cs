using System.Net;
using System.Text.Json.Nodes;
using ApexBooks_Windows.Services;

static class RecordEditRecoveryTests
{
    static JsonObject Body(string kind)=>new(){["kind"]=kind,["name"]="Synthetic edit",["amount"]="150",["data"]=new JsonObject{["version"]=0}};
    static async Task<JsonNode?> Attempt(ApexApi api,RetrySubmission submission,JsonObject body,JsonNode? previous,string key)
    {
        var wasUnknown=submission.Unresolved;
        try{var result=await api.SaveRecord("company-a",submission.Body(body),key,previous);submission.Succeeded();return result;}
        catch(Exception error){WorkflowMasterValues.DocumentWriteFailed(submission,error,false,previous is not null,wasUnknown);return null;}
    }
    public static async Task Run(Action<bool,string> check)
    {
        foreach(var kind in new[]{"sales_invoice","estimate","payment_in"}){
            foreach(var status in new[]{403,401,404,422}){
                var transport=new Transport{LoseFirst=true,Status=status};using var api=new ApexApi("https://synthetic-edit-recovery.invalid",transport);
                var submission=new RetrySubmission();var body=Body(kind);var previous=new JsonObject{["id"]="original"};const string key="immutable-edit-key";
                await Attempt(api,submission,body,previous,key);
                check(submission.Unresolved,"interrupted "+kind+" amendment remains unknown");
                body["amount"]="999";body["data"]!["version"]=27;
                await Attempt(api,submission,body,previous,key);
                check(submission.Unresolved,"unknown "+kind+" amendment remains locked after "+status);
                transport.Status=200;var replay=await Attempt(api,submission,body,previous,key);
                check(!submission.Unresolved&&replay!.Number("amount")==175&&replay["data"].Number("version")==2,"HTTP200 with current later revision resolves old edit key without amount/version equality guard");
                check(transport.Bodies.Count==3&&transport.Bodies.Distinct().Count()==1&&JsonNode.Parse(transport.Bodies[2])!.Number("amount")==150&&JsonNode.Parse(transport.Bodies[2])!["data"].Number("version")==0&&transport.Keys.Distinct().Single()==key&&transport.Methods.All(method=>method==HttpMethod.Put),"unknown edit retries preserve exact body key and PUT method");
                check(transport.Paths.Distinct().Single()=="/api/companies/company-a/"+(kind=="estimate"?"drafts":"documents")+"/original","unknown edit preserves original route and identity");
            }
        }
        var fresh=new Transport{Status=422};using(var api=new ApexApi("https://synthetic-edit-recovery.invalid",fresh)){
            var submission=new RetrySubmission();var body=Body("sales_invoice");var previous=new JsonObject{["id"]="original"};
            await Attempt(api,submission,body,previous,"fresh-edit-key");
            check(!submission.Unresolved,"fresh definitive edit rejection remains correctable");
            body["amount"]="175";fresh.Status=200;await Attempt(api,submission,body,previous,"fresh-edit-key");
            check(!submission.Unresolved&&fresh.Bodies.Distinct().Count()==2&&fresh.Keys.Distinct().Count()==1,"fresh rejected edit permits corrected body with same unbound key");
        }
        var create=new RetrySubmission();create.Body(Body("sales_invoice"));WorkflowMasterValues.DocumentWriteFailed(create,new ApiFailure(422,"Validation failed"),false,false,true);
        check(!create.Unresolved,"existing-create failure behavior is unchanged by amendment recovery rule");
        var conflict=new RetrySubmission();conflict.Body(Body("sales_invoice"));WorkflowMasterValues.DocumentWriteFailed(conflict,new ApiFailure(409,"Conflict"),false,true,false);
        check(conflict.Unresolved,"fresh generic amendment409 remains locked");
        foreach(var error in new Exception[]{new InvalidDataException("Malformed replay"),new OperationCanceledException("Scope changed")}){
            var pending=new RetrySubmission();pending.Body(Body("sales_invoice"));WorkflowMasterValues.DocumentWriteFailed(pending,error,false,true,true);
            check(pending.Unresolved,"non-HTTP failure cannot clear an already-unknown edit");
        }
    }
    sealed class Transport:HttpMessageHandler
    {
        public bool LoseFirst;public int Status=200;public List<string> Bodies=[],Keys=[],Paths=[];public List<HttpMethod> Methods=[];
        protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request,CancellationToken cancellation)
        {
            Bodies.Add(await request.Content!.ReadAsStringAsync(cancellation));Keys.Add(request.Headers.GetValues("Idempotency-Key").Single());Paths.Add(request.RequestUri!.AbsolutePath);Methods.Add(request.Method);
            if(LoseFirst&&Bodies.Count==1)throw new HttpRequestException("Synthetic committed response lost");
            return new((HttpStatusCode)Status){Content=new StringContent(Status==200?"{\"id\":\"original\",\"amount\":175,\"data\":{\"version\":2}}":"{\"detail\":\"Synthetic permission or validation rejection\"}")};
        }
    }
}
