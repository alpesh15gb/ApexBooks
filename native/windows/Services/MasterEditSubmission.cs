using System.Net.Http;
using System.Globalization;
using System.Text.Json.Nodes;

namespace ApexBooks_Windows.Services;

/// <summary>Existing-master edits are revision guarded, not idempotent. Never automatically replay an uncertain PUT.</summary>
public sealed class MasterEditSubmission
{
    readonly ApexApi api;
    readonly string path,masterId,kind;
    readonly int session;
    readonly JsonObject originalData;
    string? submittedBody;
    public bool Saving{get;private set;}
    public bool ReviewRequired{get;private set;}
    public string ReviewMessage{get;private set;}="";
    public MasterEditSubmission(ApexApi api,string companyId,string masterId,string kind,JsonObject originalData)
    {
        if(string.IsNullOrWhiteSpace(companyId)||string.IsNullOrWhiteSpace(masterId)||string.IsNullOrWhiteSpace(kind))
            throw new ArgumentException("An existing company, master identity and kind are required.");
        this.api=api;this.masterId=masterId;this.kind=kind;this.originalData=originalData.DeepClone().AsObject();session=api.SessionGeneration;
        path=api.CompanyPath(companyId,"/masters/"+Uri.EscapeDataString(masterId));
    }
    public async Task<JsonObject> Save(JsonObject editedData,string name,Func<bool> workspaceCurrent)
    {
        if(Saving)throw new InvalidOperationException("Wait for the current master update to finish.");
        if(ReviewRequired)throw new InvalidOperationException(ReviewMessage);
        api.Capabilities.RequireMasterRevisionSupport();
        RequireScope(workspaceCurrent);
        // Construct and validate before entering the send boundary. Fresh validation errors are correctable.
        submittedBody=api.Capabilities.MasterData(WorkflowMasterValues.MasterUpdate(originalData,editedData,name)).ToJsonString();
        var body=JsonNode.Parse(submittedBody)!.AsObject();
        Saving=true;
        try{
            var response=await api.Send(path,HttpMethod.Put,body);
            RequireScope(workspaceCurrent);
            if(response is not JsonObject result || !ExactString(result["id"],masterId)||!ExactString(result["kind"],kind)
                || !ExactString(result["name"],body.Text("name")) || result["data"] is not JsonObject returnedData
                || !StrictRevision(returnedData["version"],out var returnedVersion) || !StrictRevision(body["version"],out var openedVersion) || returnedVersion<=openedVersion
                || ((body.ContainsKey("is_active")||returnedData.ContainsKey("is_active"))&&!StrictBoolean(returnedData["is_active"])))
                throw new InvalidDataException("The master update response could not confirm the original master identity and updated data.");
            submittedBody=null;
            return result;
        }catch(Exception error){
            var scopeCurrent=false;
            try{RequireScope(workspaceCurrent);scopeCurrent=true;}catch{ /* A stale response cannot unlock this form. */ }
            if(scopeCurrent&&error is ApiFailure {Status:>=400 and <=499} failure && failure.Status is not (408 or 409)){
                submittedBody=null; // Received definitive rejection; keep the original opened revision.
            }else{
                ReviewRequired=true;
                ReviewMessage=error is ApiFailure {Status:409}
                    ?"The server rejected this master update. Your entered values remain here. Copy any values you need before closing. Close this form, refresh the company and reopen the master to compare before submitting a new edit."
                    :"The master update outcome is unknown; it may already have saved. Your entered values remain here. Copy any values you need before closing. Do not submit it again. Close this form, refresh the company and reopen the master to compare before making another edit.";
            }
            throw;
        }finally{Saving=false;}
    }
    static bool StrictRevision(JsonNode? value,out long revision)
    {
        revision=0;
        return value is not null&&long.TryParse(value.ToJsonString(),NumberStyles.None,CultureInfo.InvariantCulture,out revision);
    }
    static bool StrictBoolean(JsonNode? value)=>value is JsonValue scalar&&scalar.TryGetValue<bool>(out _);
    static bool ExactString(JsonNode? value,string expected)=>value is JsonValue scalar&&scalar.TryGetValue<string>(out var actual)&&actual==expected;
    void RequireScope(Func<bool> current)
    {
        if(session!=api.SessionGeneration||!current())
            throw new OperationCanceledException("The original company, session or master view changed.");
    }
}
