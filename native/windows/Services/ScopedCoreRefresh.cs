namespace ApexBooks_Windows.Services;
public static class ScopedCoreRefresh
{
    public static async Task Run<A,B>(Task<A> first,Task<B> second,Func<bool> current,Action invalidate,Action<A,B> publish,Func<Task> navigate)
    {
        try { await Task.WhenAll(first,second); }
        catch {
            if(!current())return;
            if(new Task[]{first,second}.Where(t=>t.Exception!=null).SelectMany(t=>t.Exception!.Flatten().InnerExceptions).Any(e=>e is ApiFailure {Status:403 or 404}))invalidate();
            throw;
        }
        if(!current())return;
        publish(await first,await second);
        // Navigation errors are not evidence that the successfully loaded core is unauthorized.
        try { await navigate(); } catch { if(current())throw; }
    }
}
