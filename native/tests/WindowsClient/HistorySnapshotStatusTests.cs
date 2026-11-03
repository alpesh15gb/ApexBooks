using ApexBooks_Windows.Services;

static class HistorySnapshotStatusTests
{
    public static void Run(Action<bool,string> check)
    {
        var status=new HistorySnapshotStatus();status.Reset(1,10);
        check(status.LoadedAt is null&&!status.RefreshFailed&&!status.Loading&&status.Message.Contains("No complete"),"initial history has no fabricated successful timestamp");
        check(status.Begin(1,10,3)&&status.Loading,"current history request begins loading");
        var first=new DateTimeOffset(2026,11,3,12,0,0,TimeSpan.Zero);
        check(status.Complete(1,10,3,first)&&status.LoadedAt==first&&!status.Loading&&status.Message.Contains("2026-11-03 17:30:00 IST"),"successful complete history records explicit IST timestamp");
        check(status.Message.Contains("Other devices may have newer changes")&&status.Message.Contains("Use Refresh"),"successful snapshot never claims real-time cross-device freshness");
        status.Begin(1,10,4);
        check(status.LoadedAt==first&&status.Message.Contains("Refreshing"),"in-flight refresh retains last successful timestamp");
        check(status.Fail(1,10,4)&&status.LoadedAt==first&&status.RefreshFailed&&status.Message.Contains("previous history"),"failed refresh keeps confirmed timestamp and visible stale-history warning");
        check(!status.Complete(1,10,3,first.AddHours(1))&&status.RefreshFailed,"older success cannot clear newest failure");
        status.Begin(1,10,5);status.Begin(1,10,6);
        check(!status.Fail(1,10,5)&&status.Loading&&!status.RefreshFailed,"older failure cannot label newer request stale");
        check(status.Complete(1,10,6,first.AddMinutes(2))&&!status.RefreshFailed&&status.LoadedAt==first.AddMinutes(2),"new successful refresh clears stale state only after completion");
        check(!status.Begin(1,10,6)&&!status.Begin(1,10,4),"duplicate or older begin cannot replace request order");
        status.Begin(1,10,7);
        check(status.Defer(1,10,7)&&status.LoadedAt==first.AddMinutes(2)&&status.Message.Contains("deferred")&&!status.Loading,"manual refresh discarded for editor safety retains prior snapshot and explicit deferred label");
        status.Begin(1,10,8);
        check(!status.Deferred&&status.Complete(1,10,8,first.AddMinutes(3)),"next explicit refresh can complete after deferred result");
        status.Reset(2,10);
        check(status.LoadedAt is null&&!status.Loading&&!status.RefreshFailed,"company replacement clears all history evidence");
        check(!status.Begin(1,10,7)&&!status.Complete(1,10,6,first)&&!status.Fail(1,10,6),"old workspace cannot publish freshness or failure");
        status.Begin(2,10,7);status.Reset(2,11);
        check(!status.Complete(2,10,7,first)&&!status.Fail(2,10,7)&&status.LoadedAt is null,"old session cannot publish late freshness evidence");
        status.Begin(2,11,8);status.Fail(2,11,8);
        check(status.LoadedAt is null&&status.Message.Contains("history is unavailable")&&!status.Message.Contains("previous history"),"failed initial load distinguishes unavailable history from a stale confirmed snapshot");
        foreach(var dialog in new[]{false,true})foreach(var pending in new[]{false,true})foreach(var unsaved in new[]{false,true})
            check(HistorySnapshotStatus.ManualRefreshAllowed(dialog,pending,unsaved)==!(dialog||pending||unsaved),"manual refresh preserves open editor, pending command and unsaved page");
    }
}
