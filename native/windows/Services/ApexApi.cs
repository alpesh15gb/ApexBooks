using System.Globalization;
using System.Net;
using System.Net.Http.Headers;
using System.Text;
using System.Text.Json.Nodes;
using Windows.Security.Credentials;

namespace ApexBooks_Windows.Services;

public sealed class ApiFailure(int status, string message) : Exception(message)
{
    public int Status { get; } = status;
}

public static class J
{
    public static string Text(this JsonNode? node, string key = "") => (key.Length == 0 ? node : node?[key])?.ToString() ?? "";
    public static JsonObject Object(this JsonNode? node) => node as JsonObject ?? new();
    public static JsonArray Array(this JsonNode? node) => node as JsonArray ?? new();
    public static decimal Number(this JsonNode? node, string key = "") => decimal.TryParse(node.Text(key), NumberStyles.Any, CultureInfo.InvariantCulture, out var value) ? value : 0m;
    public static bool Flag(this JsonNode? node, string key) => bool.TryParse(node.Text(key), out var value) && value;
    public static string Money(decimal value) => value.ToString("C2", CultureInfo.GetCultureInfo("en-IN"));
    public static string Today => DateTime.Today.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture);
    public static string FinancialStart => $"{(DateTime.Today.Month >= 4 ? DateTime.Today.Year : DateTime.Today.Year - 1)}-04-01";
    public static JsonNode? Copy(this JsonNode? value) => value?.DeepClone();
}

/// <summary>All business requests use the shared server. No database or OCR provider credentials are stored here.</summary>
public sealed class ApexApi : IDisposable
{
    public const string ProductionOrigin = "https://api.apexbooks.in";
    private readonly HttpClient http;
    private readonly PasswordVault vault = new();
    private readonly string resource;
    private readonly object sessionGate=new();
    private string sessionToken="";
    private int loginSequence;
    public string Origin { get; }
    public string Email { get; private set; } = "";
    public bool SignedIn {get{lock(sessionGate)return sessionToken.Length>0;}}
    public event Action? SessionExpired;

    public ApexApi(string origin = ProductionOrigin,HttpMessageHandler? transport=null)
    {
        http=new HttpClient(transport??new HttpClientHandler{AllowAutoRedirect=false}){Timeout=TimeSpan.FromSeconds(90)};
        var uri = new Uri(origin.TrimEnd('/') + "/");
        if (uri.Scheme != "https" && !uri.IsLoopback) throw new ArgumentException("Use HTTPS for the server address.");
        Origin = uri.ToString().TrimEnd('/'); http.BaseAddress = uri;
        http.DefaultRequestHeaders.UserAgent.ParseAdd("ApexBooks-Windows/1.0");
        resource = "ApexBooks.Windows." + Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(Encoding.UTF8.GetBytes(Origin)))[..20];
    }

    public bool RestoreSession()
    {
        try
        {
            var credential = vault.FindAllByResource(resource).FirstOrDefault();
            if (credential is null) return false;
            credential.RetrievePassword(); SetSession(credential.UserName, credential.Password); return true;
        }
        catch { return false; }
    }

    private void SetSession(string email, string token)
    {
        lock(sessionGate){Email=email;sessionToken=token;}
    }

    public async Task Login(string email, string password, bool remember)
    {
        int attempt;lock(sessionGate)attempt=++loginSequence;
        var result = await Send("/api/auth/login", HttpMethod.Post, new JsonObject { ["email"] = email, ["password"] = password });
        var token = result.Text("token"); if (string.IsNullOrWhiteSpace(token)) throw new ApiFailure(502, "The server did not return a sign-in session.");
        lock(sessionGate){if(attempt!=loginSequence)throw new OperationCanceledException("Sign-in was cancelled.");ClearStoredSession();SetSession(email,token);if(remember)vault.Add(new PasswordCredential(resource,email,token));}
    }

    public async Task Logout()
    {
        var token=SessionToken();try { await Send("/api/auth/logout", HttpMethod.Post); }
        finally { lock(sessionGate){if(sessionToken==token)ForgetSession();} }
    }
    public void ForgetSession(){lock(sessionGate){loginSequence++;ClearStoredSession();sessionToken="";Email="";}}
    private string SessionToken(){lock(sessionGate)return sessionToken;}

    public void ClearStoredSession()
    {
        try { foreach (var item in vault.FindAllByResource(resource)) vault.Remove(item); } catch { }
    }

    public async Task<JsonNode> Send(string path, HttpMethod? method = null, JsonNode? body = null, string? retryKey = null, CancellationToken cancellation = default)
    {
        using var request = new HttpRequestMessage(method ?? HttpMethod.Get, path.TrimStart('/'));
        var sentToken=SessionToken();if(sentToken.Length>0)request.Headers.Authorization=new AuthenticationHeaderValue("Bearer",sentToken);
        if (body is not null) request.Content = new StringContent(body.ToJsonString(), Encoding.UTF8, "application/json");
        if (retryKey is not null) request.Headers.Add("Idempotency-Key", retryKey);
        try
        {
            using var response = await http.SendAsync(request, cancellation).ConfigureAwait(false);
            var content = await response.Content.ReadAsStringAsync(cancellation).ConfigureAwait(false);
            if (!response.IsSuccessStatusCode) throw Failure(response.StatusCode,content,sentToken,path is "/api/auth/login" or "/api/auth/change-password" or "/api/auth/recovery-codes");
            if (string.IsNullOrWhiteSpace(content)) return new JsonObject();
            return JsonNode.Parse(content) ?? new JsonObject();
        }
        catch (HttpRequestException) { throw new ApiFailure(0, "Cannot reach Apex Books. Check your connection. Retry the same save to recover a transaction whose response was interrupted."); }
        catch (TaskCanceledException) when (!cancellation.IsCancellationRequested) { throw new ApiFailure(0, "The server took too long to respond. Retry this same save before creating another transaction."); }
    }

    private ApiFailure Failure(HttpStatusCode status,string content,string sentToken,bool credentialChallenge=false)
    {
        var message = "The request could not be completed.";
        try
        {
            var detail = JsonNode.Parse(content)?["detail"];
            message = detail is JsonArray list ? string.Join("\n", list.Select(row => row.Text("msg"))) : detail?.ToString() ?? message;
        }
        catch { }
        var expired=false;lock(sessionGate){if(status==HttpStatusCode.Unauthorized&&sentToken.Length>0&&sessionToken==sentToken&&!credentialChallenge){ForgetSession();expired=true;}}
        if(expired){SessionExpired?.Invoke();message="Your session has ended. Sign in again.";}
        return new ApiFailure((int)status, message);
    }

    public async Task<byte[]> Download(string path)
    {
        var sentToken=SessionToken();using var request=new HttpRequestMessage(HttpMethod.Get,path.TrimStart('/'));if(sentToken.Length>0)request.Headers.Authorization=new AuthenticationHeaderValue("Bearer",sentToken);
        using var response = await http.SendAsync(request);
        if (!response.IsSuccessStatusCode) throw Failure(response.StatusCode,await response.Content.ReadAsStringAsync(),sentToken);
        return await response.Content.ReadAsByteArrayAsync();
    }

    public string CompanyPath(string companyId, string suffix = "") => $"/api/companies/{Uri.EscapeDataString(companyId)}{suffix}";

    public async Task<JsonArray> Records(string companyId)
    {
        var rows = new JsonArray();
        for (var offset = 0; ; offset += 500)
        {
            var page = (await Send(CompanyPath(companyId, $"/records?compact=true&limit=500&offset={offset}")).ConfigureAwait(false)).Array();
            foreach (var item in page) rows.Add(item.Copy());
            if (page.Count < 500) return rows;
        }
    }

    public Task<JsonNode> Record(string companyId, string recordId) => Send(CompanyPath(companyId, "/records/" + Uri.EscapeDataString(recordId)));

    public Task<JsonNode> SaveRecord(string companyId, JsonObject body, string retryKey, JsonNode? previous = null)
    {
        var kind = body.Text("kind");
        var suffix = previous is null ? "/records" : new[] { "estimate", "proforma", "sales_order", "purchase_order" }.Contains(kind) ? "/drafts/" + previous.Text("id") : "/documents/" + previous.Text("id");
        return Send(CompanyPath(companyId, suffix), previous is null ? HttpMethod.Post : HttpMethod.Put, body, retryKey);
    }

    public void Dispose() => http.Dispose();
}
