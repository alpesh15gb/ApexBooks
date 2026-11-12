namespace ApexBooks_Windows.Services;
public static class ScopedExternalAction
{
    public static async Task Run<T>(Func<Task<string>> load, Func<bool> current, Func<string,T> prepare, Func<T,Task> launch)
    {
        if(!current())return;
        string value;
        try{value=await load();}catch(OperationCanceledException){throw;}catch(Exception){value="";}
        if(!current())return;
        var payload=prepare(value);
        if(current())await launch(payload);
    }
}
