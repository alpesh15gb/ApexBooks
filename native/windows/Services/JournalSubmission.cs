using System.Net.Http;
using System.Text.Json.Nodes;

namespace ApexBooks_Windows.Services;

/// <summary>In-memory journal command recovery. No process-restart persistence.</summary>
public sealed class JournalSubmission
{
    readonly ApexApi api;readonly string path,key=Guid.NewGuid().ToString();readonly int session;readonly string? reversalOf;
    readonly RetrySubmission retry=new();
    public bool Saving{get;private set;}
    public bool ReviewRequired{get;private set;}
    bool earlierUnknown;
    public const string ReviewGuidance="Close this form, review the journal register, then reopen before starting a new command. Keep a copy of these entered values. An earlier interrupted attempt may already have saved; do not create a replacement until reconciled.";
    static bool KnownRejection(Exception error)=>error is ApiFailure {Status:409} && error.Message is
        "Journal retry key was used for a different request" or
        "Journal reference already exists" or
        "Journal is already reversed or is itself a reversal" or
        "Reference already exists or journal was already reversed" or
        "Date is in a locked accounting period" or
        "Reverse source documents through their document workflow";
    public bool Unresolved=>retry.Unresolved;
    public bool InputsEditable=>!Saving&&!Unresolved;
    public JournalSubmission(ApexApi api,string companyId,string? originalJournalId=null)
    {
        if(string.IsNullOrWhiteSpace(companyId)||originalJournalId is not null&&string.IsNullOrWhiteSpace(originalJournalId))throw new ArgumentException("A company and valid original journal are required.");
        this.api=api;session=api.SessionGeneration;reversalOf=originalJournalId;
        path=api.CompanyPath(companyId,originalJournalId is null?"/journals":$"/journals/{Uri.EscapeDataString(originalJournalId)}/reverse");
    }
    public async Task<JsonObject> Save(JsonObject candidate,Func<bool> originalScopeCurrent)
    {
        if(ReviewRequired)throw new InvalidOperationException(ReviewGuidance);
        if(Saving)throw new InvalidOperationException("Wait for the current journal submission to finish.");
        api.Capabilities.RequireJournalIdempotency();RequireScope(originalScopeCurrent);var previouslyUnknown=earlierUnknown||retry.Unresolved;Saving=true;
        try{
            var original=retry.Body(candidate);
            var result=(await api.Send(path,HttpMethod.Post,original,key)).Object();RequireScope(originalScopeCurrent);
            if(string.IsNullOrWhiteSpace(result.Text("id"))||result.Text("reference")!=original.Text("reference").Trim()||(reversalOf is null&&result.Text("date")!=original.Text("date"))||(reversalOf is not null&&result.Text("reversal_of")!=reversalOf))throw new InvalidDataException("The journal response could not be verified. Retry this original submission before creating another.");
            retry.Succeeded();return result;
        }catch(Exception error){
            if(KnownRejection(error)){
                retry.Succeeded();
                ReviewRequired=previouslyUnknown||error.Message=="Journal retry key was used for a different request";
            }else{
                retry.Failed(error);
                earlierUnknown|=retry.Unresolved;
            }
            throw;
        }
        finally{Saving=false;}
    }
    void RequireScope(Func<bool> current)
    {
        if(session!=api.SessionGeneration||!current())throw new OperationCanceledException("The original company, session or journal view changed. Return there and check the journal before submitting another.");
    }
}
