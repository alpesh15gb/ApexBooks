// Test-only in-memory substitute: tests exercise HTTP/session logic, not Windows credential storage.
namespace Windows.Security.Credentials;
public sealed class PasswordCredential(string resource,string userName,string password)
{
    public string Resource {get;}=resource;
    public string UserName {get;}=userName;
    public string Password {get;}=password;
    public void RetrievePassword() { }
}
public sealed class PasswordVault
{
    private readonly List<PasswordCredential> credentials=[];
    public IReadOnlyList<PasswordCredential> FindAllByResource(string resource)=>credentials.Where(c=>c.Resource==resource).ToArray();
    public void Add(PasswordCredential credential)=>credentials.Add(credential);
    public void Remove(PasswordCredential credential)=>credentials.Remove(credential);
}
