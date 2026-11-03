using System.Globalization;

namespace ApexBooks_Windows.Services;

/// <summary>Presentation state for complete history reads, never a claim of an atomic server snapshot.</summary>
public sealed class HistorySnapshotStatus
{
    int workspace,session,sequence=-1;
    public DateTimeOffset? LoadedAt{get;private set;}
    public bool Loading{get;private set;}
    public bool RefreshFailed{get;private set;}
    public bool Deferred{get;private set;}
    public void Reset(int workspace,int session)
    {
        this.workspace=workspace;this.session=session;sequence=-1;LoadedAt=null;Loading=false;RefreshFailed=false;Deferred=false;
    }
    public bool Begin(int workspace,int session,int sequence)
    {
        if(this.workspace!=workspace||this.session!=session||sequence<=this.sequence)return false;
        this.sequence=sequence;Loading=true;RefreshFailed=false;Deferred=false;return true;
    }
    bool Current(int workspace,int session,int sequence)=>this.workspace==workspace&&this.session==session&&this.sequence==sequence&&Loading;
    public bool Complete(int workspace,int session,int sequence,DateTimeOffset loadedAt)
    {
        if(!Current(workspace,session,sequence))return false;
        LoadedAt=loadedAt;Loading=false;RefreshFailed=false;Deferred=false;return true;
    }
    public bool Fail(int workspace,int session,int sequence)
    {
        if(!Current(workspace,session,sequence))return false;
        Loading=false;RefreshFailed=true;return true;
    }
    public bool Defer(int workspace,int session,int sequence)
    {
        if(!Current(workspace,session,sequence))return false;
        Loading=false;Deferred=true;return true;
    }
    public static bool ManualRefreshAllowed(bool openDialog,bool pendingPage,bool unsavedPage)=>!openDialog&&!pendingPage&&!unsavedPage;
    public string Message
    {
        get{
            var snapshot=LoadedAt is { } at?"History snapshot loaded "+at.ToOffset(TimeSpan.FromHours(5.5)).ToString("yyyy-MM-dd HH:mm:ss",CultureInfo.InvariantCulture)+" IST. ":"No complete company history has loaded. ";
            if(Loading)return snapshot+"Refreshing history… Other devices may have newer changes.";
            if(Deferred)return snapshot+"Refresh was deferred to preserve your open editor or unsaved work. Finish that work, then use Refresh. The previous snapshot has not been replaced.";
            if(RefreshFailed)return snapshot+(LoadedAt is null?"Refresh failed; history is unavailable. ":"Refresh failed; the previous history is still shown and may be stale. ")+"Use Refresh to try again.";
            return snapshot+"Other devices may have newer changes. Use Refresh to load them.";
        }
    }
}
