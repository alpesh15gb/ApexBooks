using System.Security.Cryptography;
using System.Text.Json.Nodes;

namespace ApexBooks_Windows.Services;

/// <summary>Session-local resumable immutable transfer. Never encrypts over HTTP or creates a second
/// import after an unknown commit; the original stage/digest remains the recovery identity.</summary>
public sealed class CompleteBackupTransfer(ApexApi api,JsonObject? resume=null)
{
    public const int ChunkSize=524288;
    public string CreationKey {get;}=Guid.NewGuid().ToString();
    public JsonObject? Metadata {get;private set;}=resume?.Copy().Object();
    public JsonObject? Preview {get;private set;}
    public bool Pending {get;private set;}
    readonly RetrySubmission create=new();readonly int session=api.SessionGeneration;
    void Guard(){if(!api.SignedIn||session!=api.SessionGeneration)throw new OperationCanceledException("The account session changed. Recover this transfer after signing into the original account.");}
    public static string PrivateDirectory {get{var path=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"ApexBooks","PrivateTransfers");Directory.CreateDirectory(path);return path;}}
    public static FileStream Stage(){var options=new FileStreamOptions{Mode=FileMode.CreateNew,Access=FileAccess.ReadWrite,Share=FileShare.None,BufferSize=32768,Options=FileOptions.DeleteOnClose};if(!OperatingSystem.IsWindows())options.UnixCreateMode=UnixFileMode.UserRead|UnixFileMode.UserWrite;return new FileStream(Path.Combine(PrivateDirectory,Guid.NewGuid().ToString("N")+".stage"),options);}
    public static string Hash(byte[] bytes)=>Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant();
    public static void VerifyHash(byte[] bytes,string expected){if(expected.Length!=64||!string.Equals(Hash(bytes),expected,StringComparison.OrdinalIgnoreCase))throw new InvalidDataException("Transfer checksum mismatch. Nothing was imported or opened.");}
    public long Limit=>api.Capabilities.Limit("backup_archive_max_bytes",128L*1024*1024,320L*1024*1024);
    string UploadPath=>"/api/backups/uploads/"+Uri.EscapeDataString(Metadata.Text("upload_id"));
    public async Task<JsonObject> StartExport(string companyId)
    {
        Guard();if(Metadata is not null)return Metadata;
        Pending=true;try{Metadata=(await api.Send(api.CompanyPath(companyId,"/backup-exports"),HttpMethod.Post,create.Body(new()),CreationKey)).Object();if(Metadata.Text("export_id").Length==0)throw new InvalidDataException("Export response was incomplete. Retry the same snapshot request.");create.Succeeded();Pending=false;return Metadata;}
        catch(Exception error){Metadata=null;create.Failed(error);Pending=create.Unresolved;throw;}
    }
    public async Task<FileStream> DownloadExport(string companyId,IProgress<string>? progress=null)
    {
        Guard();var metadata=await StartExport(companyId);Guard();var path=api.CompanyPath(companyId,"/backup-exports/"+Uri.EscapeDataString(metadata.Text("export_id")));Metadata=metadata=(await api.Send(path)).Object();Validate(metadata);
        var output=Stage();try{using var hash=IncrementalHash.CreateHash(HashAlgorithmName.SHA256);var count=(int)metadata.Number("chunk_count");var chunks=metadata["chunks"].Array();if(chunks.Count!=count)throw new InvalidDataException("Export chunk manifest is incomplete.");
            for(var index=0;index<count;index++){Guard();var spec=chunks.SingleOrDefault(x=>x.Number("index")==index)??throw new InvalidDataException("Export chunk index missing.");var part=await api.DownloadBounded(api.CompanyPath(companyId,$"/backup-exports/{Uri.EscapeDataString(metadata.Text("export_id"))}/chunks/{index}"),ChunkSize);VerifyHash(part.Bytes,spec.Text("sha256"));VerifyHash(part.Bytes,part.Sha256);if(part.Bytes.Length!=(int)spec.Number("size_bytes")||part.ArchiveSha256!=metadata.Text("sha256"))throw new InvalidDataException("Export chunk metadata mismatch.");await output.WriteAsync(part.Bytes);hash.AppendData(part.Bytes);progress?.Report($"Verified chunk {index+1} of {count}");}
            if(output.Length!=(long)metadata.Number("byte_count")||!string.Equals(Convert.ToHexString(hash.GetHashAndReset()),metadata.Text("sha256"),StringComparison.OrdinalIgnoreCase))throw new InvalidDataException("Whole-backup checksum mismatch.");output.Position=0;return output;
        }catch{output.Dispose();throw;}
    }
    void Validate(JsonObject metadata){var bytes=metadata.Number("byte_count");if(bytes<=0||bytes>Limit||metadata.Number("chunk_size")!=ChunkSize||metadata.Number("chunk_count")!=Math.Ceiling(bytes/ChunkSize))throw new InvalidDataException("Unsupported or oversized transfer metadata.");if(metadata.Text("state") is "expired" or "cancelled")throw new InvalidOperationException("This transfer expired or was cancelled. Start a new explicitly reviewed transfer.");}
    public async Task<JsonObject> UploadAndPreview(Stream plaintext,string companyName,IProgress<string>? progress=null)
    {
        Guard();if(!plaintext.CanSeek||plaintext.Length<=0||plaintext.Length>Limit)throw new InvalidDataException("Backup exceeds this server's archive limit.");
        if(Metadata is null){plaintext.Position=0;var sha=Convert.ToHexString(await SHA256.HashDataAsync(plaintext)).ToLowerInvariant();Guard();var body=create.Body(new(){["company_name"]=companyName,["byte_count"]=plaintext.Length,["sha256"]=sha});if(body.Number("byte_count")!=plaintext.Length||body.Text("sha256")!=sha||body.Text("company_name")!=companyName)throw new InvalidOperationException("Recover the original upload with its original file and company name.");Pending=true;
            try{Metadata=(await api.Send("/api/backups/uploads",HttpMethod.Post,body,CreationKey)).Object();if(Metadata.Text("upload_id").Length==0)throw new InvalidDataException("Upload response incomplete. Retry the same request.");create.Succeeded();Pending=false;}catch(Exception error){Metadata=null;create.Failed(error);Pending=create.Unresolved;throw;}}
        Guard();Metadata=(await api.Send(UploadPath)).Object();Guard();Validate(Metadata);plaintext.Position=0;var actualHash=Convert.ToHexString(await SHA256.HashDataAsync(plaintext));if(plaintext.Length!=(long)Metadata.Number("byte_count")||!actualHash.Equals(Metadata.Text("sha256"),StringComparison.OrdinalIgnoreCase)||companyName!=Metadata.Text("target_company_name"))throw new InvalidOperationException("Resume requires the exact original backup and immutable target company name.");if(Metadata.Text("state")=="restored")throw new InvalidOperationException("This transfer was already restored. Recover the original commit instead of uploading again.");
        var received=Metadata["received_indices"].Array().Select(x=>x!.GetValue<int>()).ToHashSet();var buffer=new byte[ChunkSize];var count=(int)Metadata.Number("chunk_count");
        for(var index=0;index<count;index++){Guard();if(received.Contains(index))continue;plaintext.Position=(long)index*ChunkSize;var length=(int)Math.Min(ChunkSize,plaintext.Length-plaintext.Position);await plaintext.ReadExactlyAsync(buffer.AsMemory(0,length));var part=buffer.AsSpan(0,length).ToArray();Guard();var result=await api.SendBytes($"/api/backups/uploads/{Uri.EscapeDataString(Metadata.Text("upload_id"))}/chunks/{index}",HttpMethod.Put,part,"application/octet-stream");if(result.Number("index")!=index||result.Number("size_bytes")!=length||!result.Flag("received"))throw new InvalidDataException("Chunk acknowledgement mismatch.");VerifyHash(part,result.Text("sha256"));progress?.Report($"Uploaded chunk {index+1} of {count}; retry resumes received chunks.");}
        Guard();Preview=(await api.Send($"/api/backups/uploads/{Uri.EscapeDataString(Metadata.Text("upload_id"))}/preview",HttpMethod.Post)).Object();if(Preview.Text("digest")!=Metadata.Text("sha256"))throw new InvalidDataException("Preview digest does not match the complete upload.");return Preview;
    }
    public async Task<JsonObject> Commit()
    {
        Guard();if(Preview is null)throw new InvalidOperationException("Validate and review the backup first.");Pending=true;
        try{var result=(await api.Send($"/api/backups/uploads/{Uri.EscapeDataString(Metadata.Text("upload_id"))}/commit",HttpMethod.Post,new JsonObject{["digest"]=Preview.Text("digest")})).Object();if(result.Text("company_id").Length==0)throw new InvalidDataException("Commit response incomplete. Retry this same transfer to recover the restored company.");Pending=false;return result;}catch(ApiFailure error)when(error.Status is >=400 and <=499 and not (408 or 409)){Pending=false;throw;}
    }
    public async Task Cancel(string? companyId=null){Guard();if(Pending)throw new InvalidOperationException("Recover the original operation before cancelling.");if(Metadata is null)return;var path=companyId is null?UploadPath:api.CompanyPath(companyId,"/backup-exports/"+Uri.EscapeDataString(Metadata.Text("export_id")));await api.Send(path,HttpMethod.Delete);}
}
