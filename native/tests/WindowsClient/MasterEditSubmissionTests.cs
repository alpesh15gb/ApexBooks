using System.Net;
using System.Text.Json.Nodes;
using ApexBooks_Windows.Services;

static class MasterEditSubmissionTests
{
    static JsonObject Data(bool active=true)=>new(){["version"]=3,["is_active"]=active,["address"]="Entered address"};
    static async Task<Exception?> Failure(Func<Task> action){try{await action();return null;}catch(Exception error){return error;}}
    public static async Task Run(Action<bool,string> check)
    {
        foreach(var active in new[]{false,true}){
            foreach(var status in new[]{0,408,500}){
                var transport=new Transport{Status=status};using var api=new ApexApi("https://synthetic-master-edit.invalid",transport);await api.EnsureCapabilities();
                var command=new MasterEditSubmission(api,"company-a","original","party",Data());var input=Data(active);
                await Failure(async()=>{await command.Save(input,"Original name",()=>true);});
                check(command.ReviewRequired&&!command.Saving&&command.ReviewMessage.Contains("may already have saved"),"uncertain archive/reactivate master PUT requires explicit review");
                input["is_active"]=!active;await Failure(async()=>{await command.Save(input,"Changed name",()=>true);});
                check(transport.Bodies.Count==1&&JsonNode.Parse(transport.Bodies[0])!.Flag("is_active")==active,"unknown master update never resends edited or original state");
            }
        }
        foreach(var response in new[]{"{\"id\":\"original\",\"kind\":\"party\",\"name\":\"Name\"}","{}","[]","{\"id\":\"different\",\"kind\":\"party\"}","{\"id\":\"original\",\"kind\":\"item\"}","{\"id\":123,\"kind\":\"party\"}"}){
            var transport=new Transport{Response=response};using var api=new ApexApi("https://synthetic-master-edit.invalid",transport);await api.EnsureCapabilities();var command=new MasterEditSubmission(api,"company-a","original","party",Data());
            check(await Failure(async()=>{await command.Save(Data(),"Name",()=>true);}) is InvalidDataException&&command.ReviewRequired&&command.ReviewMessage.Contains("unknown"),"malformed successful master identity is not confirmed");
            await Failure(async()=>{await command.Save(Data(),"Name",()=>true);});check(transport.Bodies.Count==1,"malformed master success cannot trigger a replacement PUT");
        }
        var malformedData=new[]{"{\"version\":true,\"is_active\":true}","null","[]","{}","{\"version\":null,\"is_active\":true}","{\"version\":\"4\",\"is_active\":true}","{\"version\":-1,\"is_active\":true}","{\"version\":3,\"is_active\":true}","{\"version\":4.0,\"is_active\":true}","{\"version\":4e0,\"is_active\":true}","{\"version\":4}","{\"version\":4,\"is_active\":\"true\"}","{\"version\":4,\"is_active\":null}"};
        foreach(var bad in malformedData){
            var response=new JsonObject{["id"]="original",["kind"]="party",["name"]="Name",["data"]=JsonNode.Parse(bad)};
            var transport=new Transport{Response=response.ToJsonString()};using var api=new ApexApi("https://synthetic-master-edit.invalid",transport);await api.EnsureCapabilities();var command=new MasterEditSubmission(api,"company-a","original","party",Data());
            check(await Failure(async()=>{await command.Save(Data(),"Name",()=>true);}) is InvalidDataException&&command.ReviewRequired,"malformed master data/revision/active flag requires review");
        }
        foreach(var wrongName in new JsonNode?[]{null,JsonValue.Create(7),JsonValue.Create("Other"),JsonValue.Create(" Name ")}){
            var response=new JsonObject{["id"]="original",["kind"]="party",["name"]=wrongName,["data"]=new JsonObject{["version"]=4,["is_active"]=true}};
            var transport=new Transport{Response=response.ToJsonString()};using var api=new ApexApi("https://synthetic-master-edit.invalid",transport);await api.EnsureCapabilities();var command=new MasterEditSubmission(api,"company-a","original","party",Data());
            check(await Failure(async()=>{await command.Save(Data()," Name ",()=>true);}) is InvalidDataException&&command.ReviewRequired,"master response must match exact trimmed submitted name");
        }
        var later=new Transport();using(var api=new ApexApi("https://synthetic-master-edit.invalid",later)){
            await api.EnsureCapabilities();var command=new MasterEditSubmission(api,"company-a","original","party",Data());
            var result=await command.Save(Data(true)," Name ",()=>true);
            check(!command.ReviewRequired&&result["data"].Number("version")==15&&!result["data"].Flag("is_active"),"later valid revision and changed active value are accepted without state equality guard");
        }
        foreach(var activeJson in new[]{""," ,\"is_active\":\"false\""}){
            var transport=new Transport{Lifecycle=false,Response="{\"id\":\"original\",\"kind\":\"party\",\"name\":\"Name\",\"data\":{\"version\":4"+activeJson+"}}"};
            using var api=new ApexApi("https://synthetic-master-edit.invalid",transport);await api.EnsureCapabilities();var command=new MasterEditSubmission(api,"company-a","original","party",Data());
            var error=await Failure(async()=>{await command.Save(Data(),"Name",()=>true);});
            check(!JsonNode.Parse(transport.Bodies.Single())!.AsObject().ContainsKey("is_active")&&(activeJson.Length==0?error is null&&!command.ReviewRequired:error is InvalidDataException&&command.ReviewRequired),"minimal revision-capable server omits unsupported active field but rejects malformed active when returned");
        }
        var conflict=new Transport{Status=409};using(var api=new ApexApi("https://synthetic-master-edit.invalid",conflict)){
            await api.EnsureCapabilities();var command=new MasterEditSubmission(api,"company-a","original","party",Data());
            var error=await Failure(async()=>{await command.Save(Data(),"Name",()=>true);});
            check(error is ApiFailure {Status:409}&&error.Message=="Exact server conflict"&&command.ReviewRequired&&command.ReviewMessage.Contains("rejected")&&!command.ReviewMessage.Contains("unknown"),"master409 retains exact server error and truthful rejection review wording");
            await Failure(async()=>{await command.Save(Data(),"Corrected",()=>true);});check(conflict.Bodies.Count==1,"master409 requires close review reopen before a new command");
        }
        var fresh=new Transport{Status=422};using(var api=new ApexApi("https://synthetic-master-edit.invalid",fresh)){
            await api.EnsureCapabilities();var opened=Data();var command=new MasterEditSubmission(api,"company-a","original","party",opened);opened["version"]=99;
            await Failure(async()=>{await command.Save(Data(),"Invalid name",()=>true);});check(!command.ReviewRequired&&!command.Saving,"fresh422 is correctable without uncertain-outcome warning");
            fresh.Status=200;var edited=Data();edited["version"]=999;var result=await command.Save(edited," Corrected name ",()=>true);
            check(result.Text("id")=="original"&&fresh.Bodies.Count==2&&JsonNode.Parse(fresh.Bodies[1])!.Number("version")==3&&JsonNode.Parse(fresh.Bodies[1])!.Text("name")=="Corrected name","corrected master PUT preserves original snapshot revision and trims supplied name");
            check(fresh.Paths.All(path=>path=="/api/companies/company-a/masters/original")&&fresh.Methods.All(method=>method==HttpMethod.Put)&&fresh.RecordGets==0,"master edit never fetches a replacement revision");
        }
        var gated=new Transport();using(var api=new ApexApi("https://synthetic-master-edit.invalid",gated)){
            var command=new MasterEditSubmission(api,"company-a","original","party",Data());
            await Failure(async()=>{await command.Save(Data(),"Name",()=>true);});check(!command.ReviewRequired&&gated.Bodies.Count==0,"unverified capability is a preflight failure without review state");
            await api.EnsureCapabilities();await Failure(async()=>{await command.Save(Data(),"Name",()=>false);});check(!command.ReviewRequired&&gated.Bodies.Count==0,"stale company scope rejects before send without unknown state");
            var malformed=new MasterEditSubmission(api,"company-a","original","party",new JsonObject{["version"]="3"});
            await Failure(async()=>{await malformed.Save(Data(),"Name",()=>true);});check(!malformed.ReviewRequired&&gated.Bodies.Count==0,"invalid opened revision rejects before send");
            api.ForgetSession();await api.EnsureCapabilities();await Failure(async()=>{await command.Save(Data(),"Name",()=>true);});check(!command.ReviewRequired&&gated.Bodies.Count==0,"replacement session cannot send an old master edit");
        }
        foreach(var status in new[]{403,422}){
            foreach(var signout in new[]{false,true}){
                var transport=new Transport{Hold=true,Status=status};using var api=new ApexApi("https://synthetic-master-edit.invalid",transport);await api.EnsureCapabilities();
                var command=new MasterEditSubmission(api,"company-a","original","party",Data());var current=true;var pending=command.Save(Data(),"Name",()=>current);await transport.Entered.Task;
                if(signout)api.ForgetSession();else current=false;transport.Release.SetResult(true);
                var error=await Failure(async()=>{await pending;});
                check(error is ApiFailure&&command.ReviewRequired&&!command.Saving&&command.ReviewMessage.Contains("unknown"),"late definitive rejection after company/session change cannot unlock master editor");
                await Failure(async()=>{await command.Save(Data(),"Changed",()=>true);});
                check(transport.Bodies.Count==1,"stale rejected master response requires close/review without a second send");
            }
        }
        foreach(var signout in new[]{false,true}){
            var delayed=new Transport{Hold=true};using var api=new ApexApi("https://synthetic-master-edit.invalid",delayed);await api.EnsureCapabilities();
            var command=new MasterEditSubmission(api,"company-a","original","party",Data());var current=true;var input=Data(false);var pending=command.Save(input,"Frozen name",()=>current);await delayed.Entered.Task;
            check(command.Saving&&!command.ReviewRequired,"master in-flight flag blocks child editing and close");
            input["is_active"]=true;var doubleClick=await Failure(async()=>{await command.Save(input,"New name",()=>true);});check(doubleClick is InvalidOperationException&&delayed.Bodies.Count==1&&command.Saving,"concurrent master click cannot issue second PUT");
            if(signout)api.ForgetSession();else current=false;delayed.Release.SetResult(true);
            check(await Failure(async()=>{await pending;}) is OperationCanceledException&&command.ReviewRequired&&!command.Saving,"late master completion cannot publish to replacement company/session");
            check(!JsonNode.Parse(delayed.Bodies[0])!.Flag("is_active")&&JsonNode.Parse(delayed.Bodies[0])!.Text("name")=="Frozen name","in-flight edits cannot mutate serialized master body");
        }
    }
    sealed class Transport:HttpMessageHandler
    {
        public int Status=200,RecordGets;public bool Hold;public bool Lifecycle=true;
        public string? Response;
        public List<string> Bodies=[],Paths=[];public List<HttpMethod> Methods=[];
        public TaskCompletionSource<bool> Entered=new(TaskCreationOptions.RunContinuationsAsynchronously),Release=new(TaskCreationOptions.RunContinuationsAsynchronously);
        protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request,CancellationToken cancellation)
        {
            if(request.RequestUri!.AbsolutePath=="/api/capabilities")return new(HttpStatusCode.OK){Content=new StringContent(new JsonObject{["capabilities_version"]=1,["supported_features"]=Lifecycle?new JsonArray("master_edit_revisions","master_lifecycle"):new JsonArray("master_edit_revisions")}.ToJsonString())};
            if(request.Method==HttpMethod.Get){RecordGets++;throw new InvalidOperationException("No master revision fetch expected");}
            Bodies.Add(await request.Content!.ReadAsStringAsync(cancellation));Paths.Add(request.RequestUri.AbsolutePath);Methods.Add(request.Method);
            if(Hold){Entered.SetResult(true);await Release.Task.WaitAsync(cancellation);}
            if(Status==0)throw new HttpRequestException("Synthetic committed master response lost");
            return new((HttpStatusCode)Status){Content=new StringContent(Status==200?(Response??new JsonObject{["id"]="original",["kind"]="party",["name"]=JsonNode.Parse(Bodies.Last())!.Text("name"),["data"]=new JsonObject{["version"]=15,["is_active"]=false}}.ToJsonString()):"{\"detail\":\"Exact server conflict\"}")};
        }
    }
}
