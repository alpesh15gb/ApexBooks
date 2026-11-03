using System.Net;
using System.Text.Json.Nodes;
using ApexBooks_Windows.Services;

static class ConversionRevisionTests
{
    public static async Task Run(Action<bool,string> check)
    {
        check(WorkflowMasterValues.SourceDocumentVersion(new())==0,"legacy conversion source captures explicit revision zero");
        foreach(var kind in new[]{"estimate","proforma","sales_order","purchase_order"}){
            var source=new JsonObject{["kind"]=kind,["data"]=new JsonObject{["version"]=4}};var captured=WorkflowMasterValues.SourceDocumentVersion(source["data"].Object());source["data"]!["version"]=9;
            check(captured==4,"conversion preserves opened "+kind+" revision independently of later source changes");
        }
        foreach(var value in new[]{"null","-1","1.5","true","\"1\"","1e0"}){var rejected=false;try{WorkflowMasterValues.SourceDocumentVersion(JsonNode.Parse("{\"version\":"+value+"}")!.AsObject());}catch(InvalidOperationException){rejected=true;}check(rejected,"conversion rejects malformed source revision "+value);}
        foreach(var capability in new[]{ClientCapabilities.Unavailable,ClientCapabilities.Checking,ClientCapabilities.TransientFailure,ClientCapabilities.Parse(new JsonObject{["capabilities_version"]=1,["supported_features"]=new JsonArray()})}){
            var rejected=false;try{capability.RequireDocumentConversionSupport();}catch(InvalidOperationException error){rejected=error.Message.Contains("not submitted")&&error.Message.Contains(capability.Hint);}check(rejected,"old or unverified conversion API fails closed with appropriate feature hint");
        }
        var definitiveMessages=new[]{"Conversion source revision required; update the app and reopen the source document before converting","Conversion source changed; reopen it and review the conversion again"};
        foreach(var message in definitiveMessages){var pending=new RetrySubmission();pending.Body(new JsonObject{["name"]="Retained draft"});check(WorkflowMasterValues.DocumentWriteFailed(pending,new ApiFailure(409,message),true)&&!pending.Unresolved,"exact conversion revision409 clears pending without replacing entered draft");}
        foreach(var scenario in new[]{(Conversion:true,Status:409,Message:"Document number already exists"),(Conversion:true,Status:409,Message:definitiveMessages[1]+" extra"),(Conversion:false,Status:409,Message:definitiveMessages[1]),(Conversion:true,Status:500,Message:definitiveMessages[1])}){
            var pending=new RetrySubmission();pending.Body(new JsonObject{["name"]="Original command"});check(!WorkflowMasterValues.DocumentWriteFailed(pending,new ApiFailure(scenario.Status,scenario.Message),scenario.Conversion)&&pending.Unresolved,"unrelated/prefixed/nonconversion/unknown failure preserves financial retry lock");
        }
        var transport=new ConversionTransport();using var api=new ApexApi("https://synthetic-conversion.invalid",transport);
        var body=JsonNode.Parse("{\"kind\":\"sales_invoice\",\"name\":\"Synthetic\",\"date\":\"2026-11-03\",\"data\":{\"source_document_id\":\"source\",\"source_document_version\":4}}")!.AsObject();
        var gated=false;try{await api.SaveRecord("company",body,"stable-key");}catch(InvalidOperationException){gated=true;}check(gated&&transport.Methods.Count==0,"conversion capability guard blocks network write before metadata verification");
        await api.SaveRecord("company",new JsonObject{["kind"]="sales_invoice",["data"]=new JsonObject()},"ordinary-key");check(transport.Methods.Count==1,"ordinary document creation remains available on unverified API");
        await api.EnsureCapabilities();var retry=new RetrySubmission();
        try{await api.SaveRecord("company",retry.Body(body),"stable-key");}catch(ApiFailure error)when(error.Status==0){retry.Failed(error);}check(retry.Unresolved,"unknown conversion result preserves financial retry lock");
        body["data"]!["source_document_version"]=99;body["date"]="2026-11-04";await api.SaveRecord("company",retry.Body(body),"stable-key");retry.Succeeded();
        check(transport.ConversionBodies.Count==2&&transport.ConversionBodies.Distinct().Count()==1&&transport.Keys.Distinct().Single()=="stable-key"&&JsonNode.Parse(transport.ConversionBodies[1])!["data"].Number("source_document_version")==4,"conversion retry sends exact opened revision date body and key");
        check(transport.Methods.Count(method=>method==HttpMethod.Get)==1&&transport.Paths.Single(path=>path.EndsWith("capabilities"))=="/api/capabilities","conversion save never fetches a fresh source token");
    }
    sealed class ConversionTransport:HttpMessageHandler
    {
        public List<HttpMethod> Methods=[];public List<string> Paths=[],ConversionBodies=[],Keys=[];
        protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request,CancellationToken cancellation)
        {
            Methods.Add(request.Method);Paths.Add(request.RequestUri!.AbsolutePath);
            if(request.RequestUri.AbsolutePath=="/api/capabilities")return new(HttpStatusCode.OK){Content=new StringContent("{\"capabilities_version\":1,\"supported_features\":[\"document_conversion_revisions\"]}")};
            var text=await request.Content!.ReadAsStringAsync(cancellation);var value=JsonNode.Parse(text)!;
            if(value["data"].Text("source_document_id").Length>0){ConversionBodies.Add(text);Keys.Add(request.Headers.GetValues("Idempotency-Key").Single());if(ConversionBodies.Count==1)throw new HttpRequestException("synthetic response interrupted after commit");}
            return new(HttpStatusCode.OK){Content=new StringContent("{\"id\":\"converted\"}")};
        }
    }
}
