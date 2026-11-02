using System.Text.Json.Nodes;

namespace ApexBooks_Windows.Services;

/// <summary>Preserves the original command while a financial write has an unknown outcome.</summary>
public sealed class RetrySubmission
{
    private string? pending;
    public bool Unresolved => pending is not null;
    public JsonObject Body(JsonObject candidate)
    {
        pending ??= candidate.ToJsonString();
        return JsonNode.Parse(pending)!.AsObject();
    }
    public void Succeeded() => pending = null;
    public void Failed(Exception error)
    {
        if (error is ApiFailure { Status: >= 400 and <= 499 } failure && failure.Status is not (408 or 409)) pending = null;
    }
}
