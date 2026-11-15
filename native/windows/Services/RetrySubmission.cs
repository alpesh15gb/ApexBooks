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
    /// <summary>
    /// definitiveConflict: true only for routes that replay committed idempotency keys before validating,
    /// so a 409 means nothing was written. Generic routes keep 409 unresolved.
    /// </summary>
    public void Failed(Exception error, bool definitiveConflict = false)
    {
        // A timeout or server error may follow a committed write.
        if (error is ApiFailure { Status: >= 400 and <= 499 } failure && failure.Status is not 408
            && (failure.Status is not 409 || definitiveConflict)) pending = null;
    }
}
