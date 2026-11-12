namespace ApexBooks_Windows.Services;

public static class ScopedFileExport
{
    public static bool Current(Action verify)
    {
        try { verify(); return true; }
        catch (InvalidOperationException) { return false; }
    }
    // null means the originating workspace is stale; false means picker cancelled.
    public static async Task<bool?> Run(Action verify, Func<Task<bool>> operation)
    {
        if (!Current(verify)) return null;
        try { var result=await operation();return Current(verify)?result:null; }
        catch (Exception) when (!Current(verify)) { return null; }
    }
    public static Task<bool?> Download(Action verify, Func<Task<byte[]>> load,
        Func<byte[],Task<byte[]>>? transform, Func<byte[],Action,Task<bool>> save)
        =>Run(verify,async()=>{
            var bytes=await load();verify();
            if(transform is not null){bytes=await transform(bytes);verify();}
            return await save(bytes,verify);
        });
}
