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
    public static string Today => BusinessCalendar.Today.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture);
    public static string FinancialStart => BusinessCalendar.FinancialStart(DateTimeOffset.UtcNow);
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
    private int capabilityGeneration;private Task? capabilityLoad;
    public ClientCapabilities Capabilities { get; private set; }=ClientCapabilities.Unavailable;
    public int SessionGeneration {get{lock(sessionGate)return capabilityGeneration;}}
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
        lock(sessionGate){Email=email;sessionToken=token;capabilityGeneration++;capabilityLoad=null;Capabilities=ClientCapabilities.Unavailable;}
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
    public void ForgetSession(){lock(sessionGate){loginSequence++;ClearStoredSession();sessionToken="";Email="";capabilityGeneration++;capabilityLoad=null;Capabilities=ClientCapabilities.Unavailable;}}
    private string SessionToken(){lock(sessionGate)return sessionToken;}

    public Task EnsureCapabilities()
    {
        lock(sessionGate){if(capabilityLoad is not null)return capabilityLoad;Capabilities=ClientCapabilities.Checking;return capabilityLoad=LoadCapabilities(capabilityGeneration); }
    }
    public Task RetryCapabilities()
    {
        lock(sessionGate){if(capabilityLoad is {IsCompleted:false})return capabilityLoad;if(!Capabilities.Retryable)return capabilityLoad??Task.CompletedTask;Capabilities=ClientCapabilities.Checking;return capabilityLoad=LoadCapabilities(capabilityGeneration);}
    }
    private async Task LoadCapabilities(int generation)
    {
        var found=ClientCapabilities.Unavailable;
        try{
            using var deadline=new CancellationTokenSource(TimeSpan.FromSeconds(8));using var request=new HttpRequestMessage(HttpMethod.Get,"api/capabilities");using var response=await http.SendAsync(request,deadline.Token).ConfigureAwait(false);
            if(response.IsSuccessStatusCode){try{found=ClientCapabilities.Parse(JsonNode.Parse(await response.Content.ReadAsStringAsync(deadline.Token).ConfigureAwait(false)));}catch(System.Text.Json.JsonException){found=ClientCapabilities.Unavailable;}}
            else if((int)response.StatusCode>=500||(int)response.StatusCode is 408 or 429)found=ClientCapabilities.TransientFailure;
        }catch(HttpRequestException){found=ClientCapabilities.TransientFailure;}catch(IOException){found=ClientCapabilities.TransientFailure;}catch(OperationCanceledException){found=ClientCapabilities.TransientFailure;}
        lock(sessionGate){if(generation==capabilityGeneration)Capabilities=found;}
    }

    public void ClearStoredSession()
    {
        try { foreach (var item in vault.FindAllByResource(resource)) vault.Remove(item); } catch { }
    }

    public async Task<JsonNode> Send(string path, HttpMethod? method = null, JsonNode? body = null, string? retryKey = null, CancellationToken cancellation = default)
    {
        if(body is JsonObject input){
            if(path.Contains("/masters/",StringComparison.Ordinal)&&method==HttpMethod.Put)body=Capabilities.MasterData(input);
            else if(path.EndsWith("/records",StringComparison.Ordinal)&&input.Text("kind") is "party" or "item"){var copy=input.Copy().Object();copy["data"]=Capabilities.MasterData(input["data"].Object());body=copy;}
            if(body is JsonObject fields&&fields.ContainsKey("book_label")&&!Capabilities.Supports("company_book_labels")){body=fields.Copy();body!.AsObject().Remove("book_label");}
        }
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

    public async Task<JsonNode> SendBytes(string path,HttpMethod method,byte[] body,string mediaType,string? retryKey=null,CancellationToken cancellation=default)
    {
        using var request=new HttpRequestMessage(method,path.TrimStart('/'));var token=SessionToken();if(token.Length>0)request.Headers.Authorization=new AuthenticationHeaderValue("Bearer",token);request.Content=new ByteArrayContent(body);request.Content.Headers.ContentType=new MediaTypeHeaderValue(mediaType);if(retryKey is not null)request.Headers.Add("Idempotency-Key",retryKey);
        try{using var response=await http.SendAsync(request,cancellation).ConfigureAwait(false);var text=await response.Content.ReadAsStringAsync(cancellation).ConfigureAwait(false);if(!response.IsSuccessStatusCode)throw Failure(response.StatusCode,text,token);return JsonNode.Parse(text)??new JsonObject();}
        catch(HttpRequestException){throw new ApiFailure(0,"Transfer response interrupted. Retry the original operation.");}catch(TaskCanceledException)when(!cancellation.IsCancellationRequested){throw new ApiFailure(0,"Transfer timed out. Retry the original operation.");}
    }
    public async Task<(byte[] Bytes,string Sha256,string ArchiveSha256)> DownloadBounded(string path,int maximum,CancellationToken cancellation=default)
    {
        var token=SessionToken();using var request=new HttpRequestMessage(HttpMethod.Get,path.TrimStart('/'));if(token.Length>0)request.Headers.Authorization=new AuthenticationHeaderValue("Bearer",token);
        using var response=await http.SendAsync(request,HttpCompletionOption.ResponseHeadersRead,cancellation).ConfigureAwait(false);if(!response.IsSuccessStatusCode)throw Failure(response.StatusCode,await response.Content.ReadAsStringAsync(cancellation).ConfigureAwait(false),token);
        if(response.Content.Headers.ContentLength>maximum)throw new InvalidDataException("Download exceeds its size limit.");using var output=new MemoryStream();using var input=await response.Content.ReadAsStreamAsync(cancellation).ConfigureAwait(false);var buffer=new byte[32768];int n;
        while((n=await input.ReadAsync(buffer,cancellation).ConfigureAwait(false))>0){if(output.Length+n>maximum)throw new InvalidDataException("Download exceeds its size limit.");await output.WriteAsync(buffer.AsMemory(0,n),cancellation).ConfigureAwait(false);}
        string Header(string name)=>response.Headers.TryGetValues(name,out var values)?values.FirstOrDefault()??"":"";
        return(output.ToArray(),Header("X-Chunk-SHA256") is {Length:>0} chunk?chunk:Header("X-Content-SHA256"),Header("X-Archive-SHA256"));
    }

    public string CompanyPath(string companyId, string suffix = "") => $"/api/companies/{Uri.EscapeDataString(companyId)}{suffix}";

    public async Task<(JsonArray Records,JsonArray Banks)> LoadCompanyCore(string companyId)
    {
        _=EnsureCapabilities(); // Optional metadata never gates financial company readiness.
        var records=Records(companyId);var banks=Send(CompanyPath(companyId,"/bank-accounts"));await Task.WhenAll(records,banks).ConfigureAwait(false);return(await records.ConfigureAwait(false),(await banks.ConfigureAwait(false)).Array());
    }

    public async Task<JsonArray> Records(string companyId)
    {
        // Offset pages can overlap when another client inserts during a scan.
        // Never publish deduplicated or partial financial data: restart once.
        for(var attempt=0;attempt<2;attempt++)
        {
            var rows=new JsonArray();var seen=new HashSet<string>(StringComparer.Ordinal);
            for(var offset=0;;offset+=500)
            {
                var page=(await Send(CompanyPath(companyId,$"/records?compact=true&limit=500&offset={offset}")).ConfigureAwait(false)).Array();
                var overlap=false;
                foreach(var item in page){if(!seen.Add(item.Text("id"))){overlap=true;break;}rows.Add(item.Copy());}
                if(overlap)break;
                if(page.Count<500)return rows;
            }
        }
        throw new InvalidOperationException("Company records changed while loading. No partial balances were loaded. Refresh the company and try again.");
    }

    public Task<JsonNode> Record(string companyId, string recordId) => Send(CompanyPath(companyId, "/records/" + Uri.EscapeDataString(recordId)));

    public async Task<JsonNode> SaveMaster(string companyId,string masterId,JsonObject openedData,JsonObject editedData,string name)
    {
        Capabilities.RequireMasterRevisionSupport();
        var body=WorkflowMasterValues.MasterUpdate(openedData,editedData,name);
        try{return await Send(CompanyPath(companyId,"/masters/"+Uri.EscapeDataString(masterId)),HttpMethod.Put,body).ConfigureAwait(false);}
        catch(ApiFailure error)when(error.Status==409){throw new ApiFailure(409,error.Message+" Your edits remain in this form. An earlier interrupted attempt may already have saved. Copy any needed changes, then close, refresh the company, and reopen the master to compare before saving again.");}
    }

    public Task<JsonNode> SaveRecord(string companyId, JsonObject body, string retryKey, JsonNode? previous = null)
    {
        var kind = body.Text("kind");
        if(previous is null&&body["data"].Text("source_document_id").Length>0)Capabilities.RequireDocumentConversionSupport();
        var suffix = previous is null ? "/records" : new[] { "estimate", "proforma", "sales_order", "purchase_order" }.Contains(kind) ? "/drafts/" + previous.Text("id") : "/documents/" + previous.Text("id");
        return Send(CompanyPath(companyId, suffix), previous is null ? HttpMethod.Post : HttpMethod.Put, body, retryKey);
    }

    public void Dispose() => http.Dispose();
}
