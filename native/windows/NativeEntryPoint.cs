namespace ApexBooks_Windows;

internal static class NativeEntryPoint
{
    [STAThread]
    private static void Main(string[] args)
    {
        WinRT.ComWrappersSupport.InitializeComWrappers();
        if(args.Length==2&&args[0]=="--share-pdf")
        {
            // Keep Shell sharing independent of WinUI modal state.
            ApexBooks.NativePrinting.NativeShareHost.Run(args[1]);
            return;
        }
        Microsoft.UI.Xaml.Application.Start(_=>{
            var queue=Microsoft.UI.Dispatching.DispatcherQueue.GetForCurrentThread();
            SynchronizationContext.SetSynchronizationContext(new Microsoft.UI.Dispatching.DispatcherQueueSynchronizationContext(queue));
            new App();
        });
    }
}
