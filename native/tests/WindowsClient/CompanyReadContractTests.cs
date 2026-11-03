using System.Net;
using System.Text.Json.Nodes;
using ApexBooks_Windows.Services;

static class CompanyReadContractTests
{
    static string Page(int start,int count)
    {
        var rows=new JsonArray();
        for(var i=start;i<start+count;i++)rows.Add(new JsonObject{["id"]="row-"+i,["future_field"]="preserved"});
        return rows.ToJsonString();
    }
    static async Task<bool> Invalid(Func<Task> read)
    {
        try{await read();return false;}catch(InvalidDataException error){return error.Message.Contains("Refresh");}
    }
    public static async Task Run(Action<bool,string> check)
    {
        var malformed=new[]{"null","{}","true","123","\"array\"","[null]","[false]","[42]","[\"row\"]","[{}]","[{\"id\":null}]","[{\"id\":0}]","[{\"id\":true}]","[{\"id\":{}}]","[{\"id\":[]}]","[{\"id\":\"\"}]","[{\"id\":\" \\t\"}]"};
        foreach(var bad in malformed.Append(Page(0,501))){
            foreach(var later in new[]{false,true}){
                var transport=new Transport{First=later?Page(0,500):bad,Later=bad};
                using var api=new ApexApi("https://synthetic-company-read.invalid",transport);
                check(await Invalid(async()=>{await api.Records("company-a");})&&transport.Offsets.SequenceEqual(later?new[]{0,500}:new[]{0}),"malformed "+(later?"later":"first")+" record page rejects whole scan without overlap retry");
            }
        }
        foreach(var bad in malformed){
            var transport=new Transport{Companies=bad,Banks=bad};using var api=new ApexApi("https://synthetic-company-read.invalid",transport);
            check(await Invalid(async()=>{await api.Companies();}),"malformed company list rejects envelope or identity");
            check(await Invalid(async()=>{await api.BankAccounts("company-a");}),"malformed bank list rejects envelope or identity");
        }
        var valid=new Transport{First=Page(0,500),Later=Page(500,1),Companies="[{\"id\":\" company \",\"extra\":true}]",Banks="[{\"id\":\"default\"}]"};
        using(var api=new ApexApi("https://synthetic-company-read.invalid",valid)){
            var loaded=await api.LoadCompanyCore("company-a");var companies=await api.Companies();
            check(loaded.Records.Count==501&&valid.Offsets.SequenceEqual(new[]{0,500}),"valid 500 plus 1 records retain stable two-page path");
            check(loaded.Records[500].Text("future_field")=="preserved"&&companies[0].Text("id")==" company "&&loaded.Banks[0].Text("id")=="default","strict reads preserve exact identities extra fields and built-in bank default");
        }
        foreach(var recordsBad in new[]{false,true}){
            var transport=new Transport{First=recordsBad?Page(0,500):Page(0,1),Later="{}",Banks=recordsBad?"[{\"id\":\"default\"}]":"{}"};
            using var api=new ApexApi("https://synthetic-company-read.invalid",transport);
            var oldRecords=JsonNode.Parse("[{\"id\":\"confirmed-record\"}]")!.AsArray();var oldBanks=JsonNode.Parse("[{\"id\":\"confirmed-bank\"}]")!.AsArray();
            var records=oldRecords;var banks=oldBanks;
            var failed=await Invalid(async()=>{var loaded=await api.LoadCompanyCore("company-a");records=loaded.Records;banks=loaded.Banks;});
            check(failed&&ReferenceEquals(records,oldRecords)&&ReferenceEquals(banks,oldBanks),"core tuple rejects "+(recordsBad?"malformed later records":"malformed banks")+" before either confirmed local is replaced");
        }
        var empty=new Transport();using(var api=new ApexApi("https://synthetic-company-read.invalid",empty)){
            var core=await api.LoadCompanyCore("company-a");
            check(core.Records.Count==0&&core.Banks.Count==0&&(await api.Companies()).Count==0,"valid empty lists remain supported");
        }
        var fullPage=new Transport{First=Page(0,500),Companies=Page(0,501),Banks=Page(0,501)};
        using(var api=new ApexApi("https://synthetic-company-read.invalid",fullPage)){
            check((await api.Records("company-a")).Count==500&&fullPage.Offsets.SequenceEqual(new[]{0,500}),"full record page followed by valid empty terminal page remains complete");
            check((await api.Companies()).Count==501&&(await api.BankAccounts("company-a")).Count==501,"record page limit is not imposed on unpaginated company or bank lists");
        }
        var exact=new Transport{First="[{\"id\":\" x \"},{\"id\":\"x\"}]"};
        using(var api=new ApexApi("https://synthetic-company-read.invalid",exact))
            check((await api.Records("company-a")).Count==2,"identity validation does not normalize distinct exact IDs");
    }
    sealed class Transport:HttpMessageHandler
    {
        public string First="[]",Later="[]",Companies="[]",Banks="[]";
        public List<int> Offsets=[];
        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request,CancellationToken cancellation)
        {
            var uri=request.RequestUri!;string value;
            if(uri.AbsolutePath=="/api/capabilities")value="{\"capabilities_version\":1,\"supported_features\":[]}";
            else if(uri.AbsolutePath=="/api/companies")value=Companies;
            else if(uri.AbsolutePath.EndsWith("/bank-accounts"))value=Banks;
            else if(uri.AbsolutePath.EndsWith("/records")){
                var offset=int.Parse(uri.Query.TrimStart('?').Split('&').Single(part=>part.StartsWith("offset=")).Split('=')[1]);Offsets.Add(offset);value=offset==0?First:Later;
            }else throw new InvalidOperationException("Unexpected synthetic read route");
            return Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK){Content=new StringContent(value)});
        }
    }
}
