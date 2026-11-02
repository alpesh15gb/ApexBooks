using System.Runtime.InteropServices;
using Windows.ApplicationModel.DataTransfer;
using Windows.Storage;
using WinRT;

namespace ApexBooks.NativePrinting;

public static class NativeShareHost
{
    [ComImport,Guid("3A3DCD6C-3EAB-43DC-BCDE-45671CE800C8"),InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    private interface IShareWindow
    {
        IntPtr GetForWindow([In]IntPtr window,[In]ref Guid iid);
        void ShowShareUIForWindow(IntPtr window);
    }
    public static void Run(string requestedPath)
    {
        var root=Path.GetFullPath(Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"ApexBooks","Shared"))+Path.DirectorySeparatorChar;
        var path=Path.GetFullPath(requestedPath);
        if(!path.StartsWith(root,StringComparison.OrdinalIgnoreCase)||!File.Exists(path)||!path.EndsWith(".pdf",StringComparison.OrdinalIgnoreCase))return;
        void Trace(string message){
#if DEBUG
            try{File.AppendAllText(Path.Combine(root,"qa-share-events.log"),DateTime.UtcNow.ToString("O")+" "+message+Environment.NewLine);}catch{}
#endif
        }
        System.Windows.Forms.Application.EnableVisualStyles();
        using var window=new Form{Text="Share Apex Books document",Width=470,Height=220,StartPosition=FormStartPosition.CenterScreen,ShowInTaskbar=true,MaximizeBox=false,MinimizeBox=false,FormBorderStyle=FormBorderStyle.FixedDialog};
        var title=new Label{Text=Path.GetFileName(path),AutoEllipsis=true,Dock=DockStyle.Top,Height=42,Padding=new Padding(12),Font=new System.Drawing.Font("Segoe UI",10,System.Drawing.FontStyle.Bold)};
        var status=new Label{Text="Choose an app in Windows Share.",Dock=DockStyle.Fill,Padding=new Padding(12),Font=new System.Drawing.Font("Segoe UI",10)};
        var cancel=new Button{Text="Close",Dock=DockStyle.Bottom,Height=34};cancel.Click+=(_,_)=>window.Close();
        var share=new Button{Text="Choose an app",Dock=DockStyle.Bottom,Height=34,Enabled=false};
        window.CancelButton=cancel;window.AcceptButton=share;
        window.Controls.Add(status);window.Controls.Add(title);window.Controls.Add(share);window.Controls.Add(cancel);
        DataTransferManager? manager=null;
        using var timeout=new System.Windows.Forms.Timer{Interval=300000};timeout.Tick+=(_,_)=>window.Close();
        window.Shown+=async(_,_)=>{
            try{
                var file=await StorageFile.GetFileFromPathAsync(path);
                Trace("PDF ready");
                var interop=DataTransferManager.As<IShareWindow>();var iid=new Guid("A5CAEE9B-8708-49D1-8D36-67D25A8DA00C");var pointer=interop.GetForWindow(window.Handle,ref iid);
                try{manager=MarshalInterface<DataTransferManager>.FromAbi(pointer);}finally{Marshal.Release(pointer);}
                manager.DataRequested+=(_,args)=>{
                    Trace("DataRequested");
                    try{
                        args.Request.Data.Properties.Title=Path.GetFileNameWithoutExtension(path);
                        args.Request.Data.SetStorageItems(new IStorageItem[]{file});
                        args.Request.Data.RequestedOperation=DataPackageOperation.Copy;
                        args.Request.Data.OperationCompleted+=(_,_)=>{if(!window.IsDisposed)window.BeginInvoke(()=>window.Close());};
                        Trace("Storage attachment prepared");
                    }catch(Exception ex){Trace("Attachment failure "+ex.GetType().Name);args.Request.FailWithDisplayText("Windows could not prepare this PDF. Save it from Apex Books and try again.");}
                };
                share.Click+=(_,_)=>{Trace("Share requested");interop.ShowShareUIForWindow(window.Handle);};share.Enabled=true;
                timeout.Start();Trace("Initial share requested");interop.ShowShareUIForWindow(window.Handle);
            }catch(Exception ex){Trace("Share failure "+ex.GetType().Name);status.Text="Windows sharing is unavailable. Save this PDF from Apex Books, then attach it in your chosen app.";}
        };
        System.Windows.Forms.Application.Run(window);
        GC.KeepAlive(manager);
    }
}
