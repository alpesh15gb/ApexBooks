namespace ApexBooks_Windows.Services;

// Read-only fetch gate: do not publish a response into a changed/closed draft.
public sealed class SourceSelectionRequest
{
    private long version;
    public bool Busy { get; private set; }
    public void Invalidate() { version++; }
    public async Task<bool> Load<T>(Func<Task<T>> fetch, Func<string> draft, Func<bool> current, Action<T> apply)
    {
        if(Busy||!current())return false;
        Busy=true;var request=++version;
        try
        {
            var before=draft();
            var value=await fetch();
            if(request!=version||!current()||draft()!=before)return false;
            apply(value);return true;
        }
        catch when(request!=version||!current()) { return false; }
        finally { Busy=false; }
    }
}
