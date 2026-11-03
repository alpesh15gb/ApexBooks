using System.Net.Http;
using System.Text.Json.Nodes;

namespace ApexBooks_Windows.Services;

/// <summary>One inline creation command, isolated from the surrounding document.</summary>
public sealed class InlineMasterSubmission(ApexApi api,string companyId)
{
    readonly long session=api.SessionGeneration;
    readonly string key=Guid.NewGuid().ToString();
    readonly RetrySubmission retry=new();
    public bool Unresolved=>retry.Unresolved;
    public static bool CanEditInputs(bool saving,bool unresolved)=>!saving&&!unresolved;
    public static bool CanTrackStock(string itemType,bool inputsEditable)=>itemType=="goods"&&inputsEditable;
    public async Task<JsonObject> Save(JsonObject candidate,Func<bool> workspaceCurrent)
    {
        if(session!=api.SessionGeneration||!workspaceCurrent())throw new OperationCanceledException("The original company or session changed. Reopen its invoice before creating a master.");
        try{
            var prepared=candidate.Copy().Object();prepared["data"]=api.Capabilities.MasterData(candidate["data"].Object());
            var original=retry.Body(prepared);
            var result=(await api.Send(api.CompanyPath(companyId,"/records"),HttpMethod.Post,original,key)).Object();
            if(session!=api.SessionGeneration||!workspaceCurrent())throw new OperationCanceledException("The master may have been created in the original company. Return there and refresh before creating another.");
            if(string.IsNullOrWhiteSpace(result.Text("id"))||result.Text("kind")!=original.Text("kind")||result.Text("name")!=original.Text("name").Trim()||!ValidActivation(result["data"])||(result.ContainsKey("company_id")&&result.Text("company_id")!=companyId))throw new InvalidDataException("The create response could not be verified. Retry the original request.");
            retry.Succeeded();return result;
        }catch(Exception error){
            // Exact duplicate-name rejection is definitive and never selects the
            // existing record. Other409 responses remain conservative/locked.
            if(error is ApiFailure{Status:409} failure&&failure.Message=="A party or item with this name already exists")retry.Succeeded();
            else retry.Failed(error);
            throw;
        }
    }
    private static bool ValidActivation(JsonNode? data)=>data is JsonObject fields&&(!fields.ContainsKey("is_active")||fields["is_active"] is JsonValue active&&active.TryGetValue<bool>(out _));
    public static JsonObject CurrentRow(JsonArray catalog,JsonObject created)=>catalog.OfType<JsonObject>().FirstOrDefault(row=>row.Text("id")==created.Text("id"))??created;
    public static string PartySupplyState(JsonObject party,string companyState)=>party["data"].Text("gstin") is {Length:>=2} gstin?gstin[..2]:companyState;
    public static JsonObject ItemLine(JsonObject item,bool regular)
    {
        if(item.Text("id").Length==0||item.Text("kind")!="item"||!WorkflowMasterValues.IsActive(item))throw new InvalidOperationException("Created item is unavailable for this invoice.");
        var data=item["data"];var treatment=data.Text("tax_treatment");if(regular&&data.Number("gst_rate")==0&&treatment is "" or "taxable")treatment="nil_rated";
        return new(){["item_id"]=item.Text("id"),["description"]=item.Text("name"),["quantity"]="1",["rate"]=data.Text("sale_rate"),["gst_rate"]=regular?data.Text("gst_rate"):"0",["tax_treatment"]=treatment.Length>0?treatment:"taxable",["unit"]=data.Text("unit"),["hsn"]=data.Text("hsn"),["discount_percent"]="0",["price_includes_tax"]=false};
    }
    public static bool CanReusePlaceholder(int count,bool sameInstance,string current,string opened)=>count==1&&sameInstance&&current==opened;
    public static bool CanAppend(int count)=>count>=0&&count<100;
}
