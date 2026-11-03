using System.Globalization;
using System.Net.Http;
using System.Text.Json.Nodes;

namespace ApexBooks_Windows.Services;

/// <summary>A displayed exact match is removed only with its original identity and revision.</summary>
public sealed class ExactBankUnmatch
{
    readonly ApexApi api;readonly string companyId,lineId,body;readonly int session;
    public ExactBankUnmatch(ApexApi api,string companyId,JsonObject displayedLine)
    {
        this.api=api;this.companyId=companyId;session=api.SessionGeneration;lineId=displayedLine.Text("id");
        if(string.IsNullOrWhiteSpace(companyId)||string.IsNullOrWhiteSpace(lineId))throw new InvalidOperationException("Reload the statement before unmatching this line.");
        body=CaptureBody(displayedLine).ToJsonString();
    }
    public static JsonObject CaptureBody(JsonObject displayedLine)
    {
        var recordId=displayedLine.Text("matched_record_id");var revision=displayedLine["match_revision"];
        if(string.IsNullOrWhiteSpace(recordId)||revision is null||!long.TryParse(revision.ToJsonString(),NumberStyles.None,CultureInfo.InvariantCulture,out var value))throw new InvalidOperationException("This displayed match has no valid revision. Reload the statement before unmatching; update the API if revisions remain unavailable.");
        return new(){["expected_record_id"]=recordId,["expected_match_revision"]=value};
    }
    public async Task Remove(Func<bool> originalScopeCurrent)
    {
        api.Capabilities.RequireBankMatchRevisionSupport();
        RequireScope(originalScopeCurrent);
        await api.Send(api.CompanyPath(companyId,$"/bank-statement/{Uri.EscapeDataString(lineId)}/match"),HttpMethod.Delete,JsonNode.Parse(body));
        RequireScope(originalScopeCurrent);
    }
    void RequireScope(Func<bool> current)
    {
        if(session!=api.SessionGeneration||!current())throw new OperationCanceledException("The original company, session or statement view changed. Return there and reload to check the match before taking another action.");
    }
}
