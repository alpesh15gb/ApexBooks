using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;

namespace ApexBooks_Windows.Services;

/// <summary>Opaque restart reference only; input bodies are never written to this file.</summary>
public sealed class ImportReceiptRecovery
{
    public sealed record Marker(string Key,string Kind,string Hash);
    public sealed record Attempt(string? Key,string Body,bool Retry);
    private static readonly object StorageGate=new();
    private readonly string path;
    public Marker? Saved {get;private set;}
    public bool Pending=>Saved is not null;
    public bool Busy {get;private set;}
    public ImportReceiptRecovery(string path){this.path=path;Saved=Read();}
    public static string Hash(string value)=>Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(value))).ToLowerInvariant();
    public static string Location(string folder,string origin,string account,string company,bool bank=false)
    {
        if(string.IsNullOrWhiteSpace(account)||string.IsNullOrWhiteSpace(company))throw new InvalidOperationException("Sign in and select a company before importing.");
        return Path.Combine(folder,bank?"BankImportRecovery":"ImportRecovery",Hash(origin+"\n"+account.Trim().ToLowerInvariant()+"\n"+company)+".ref");
    }
    private Marker? Read()
    {
        if(!File.Exists(path))return null;
        if(new FileInfo(path).Length>512)throw new InvalidOperationException("Import recovery reference is damaged; verify the original result before continuing.");
        var parts=File.ReadAllText(path,Encoding.UTF8).Split('\n');
        if(parts.Length!=3||!Regex.IsMatch(parts[0],"^[a-f0-9-]{36}$")||parts[1] is not ("party" or "item" or "bank")||!Regex.IsMatch(parts[2],"^[a-f0-9]{64}$"))throw new InvalidOperationException("Import recovery reference is damaged; verify the original result before continuing.");
        return new(parts[0],parts[1],parts[2]);
    }
    private static FileStream OpenPrivate(string file,FileMode mode)
    {
        var options=new FileStreamOptions{Mode=mode,Access=FileAccess.ReadWrite,Share=FileShare.None};
        if(!OperatingSystem.IsWindows())options.UnixCreateMode=UnixFileMode.UserRead|UnixFileMode.UserWrite;
        return new FileStream(file,options);
    }
    private T Locked<T>(Func<T> action)
    {
        lock(StorageGate){Directory.CreateDirectory(Path.GetDirectoryName(path)!);using var gate=OpenPrivate(path+".lock",FileMode.OpenOrCreate);return action();}
    }
    public Attempt Begin(string body,string kind,bool supported)=>supported?Locked(()=>BeginCore(body,kind,true)):BeginCore(body,kind,false);
    private Attempt BeginCore(string body,string kind,bool supported)
    {
        if(Busy)throw new InvalidOperationException("An import request is already in progress.");
        var disk=Read();
        if(disk is not null&&Saved is not null&&disk.Key!=Saved.Key)throw new InvalidOperationException("Another import reference exists. Verify the original operations before continuing.");
        var existing=disk??Saved;Saved=existing;
        if(!supported){if(existing is not null)throw new InvalidOperationException("Reconnect to a server supporting import receipts before recovering this import.");Busy=true;return new(null,body,false);}
        if(kind is not ("party" or "item" or "bank"))throw new InvalidOperationException("Choose a supported import type.");
        var digest=Hash(body);
        if(existing is not null&&(existing.Kind!=kind||existing.Hash!=digest))throw new InvalidOperationException("Select the original CSV, bank, mapping and import type without changes to retry the original operation.");
        var marker=existing??new Marker(Guid.NewGuid().ToString(),kind,digest);
        if(disk is null){
            var temporary=path+"."+Guid.NewGuid().ToString("N")+".tmp";
            try{using(var output=OpenPrivate(temporary,FileMode.CreateNew)){output.Write(Encoding.UTF8.GetBytes(marker.Key+"\n"+marker.Kind+"\n"+marker.Hash));output.Flush(true);}File.Move(temporary,path,false);}
            finally{if(File.Exists(temporary))File.Delete(temporary);}
            if(Read()!=marker)throw new IOException("Could not retain import recovery reference; no import was sent.");
        }
        Saved=marker;Busy=true;return new(marker.Key,body,existing is not null);
    }
    public void Confirmed(string key)=>Locked(()=>{
        var stored=Read();if(stored is null||stored.Key!=key||Saved?.Key!=key)throw new InvalidOperationException("Unexpected or missing import receipt; verify the original result.");
        File.Delete(path);Saved=null;return true;
    });
    public void Failed(Attempt attempt,int status){if(attempt.Key is not null&&!attempt.Retry&&status is >=400 and <=499&&status is not (408 or 409))Confirmed(attempt.Key);}
    public void End()=>Busy=false;
}
