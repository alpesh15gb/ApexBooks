// Pure ownership policy shared with portable regressions. Native lookup is injected.
public static class WindowOwnership
{
    public static bool ReachesApp(nint candidate,nint app,Func<nint,nint> owner,int maxDepth=64)
    {
        if(candidate==0||app==0||candidate==app||maxDepth<=0||maxDepth>64)return false;
        var seen=new HashSet<nint>{candidate};var current=candidate;
        for(var depth=0;depth<maxDepth;depth++){
            current=owner(current);
            if(current==app)return true;
            if(current==0||!seen.Add(current))return false;
        }
        return false;
    }
}
