namespace ApexBooks.NativePrinting;

public static class NativePrintBridge
{
    [System.Runtime.InteropServices.DllImport("user32.dll")]
    private static extern bool IsWindowEnabled(IntPtr handle);
    [System.Runtime.InteropServices.DllImport("user32.dll")]
    private static extern bool EnableWindow(IntPtr handle,bool enabled);
    private sealed class Owner(IntPtr handle) : System.Windows.Forms.IWin32Window { public IntPtr Handle=>handle; }
    public static void Print(IReadOnlyList<byte[]> pages,string title,IntPtr handle)
    {
        var ownerWasEnabled=IsWindowEnabled(handle);
        try
        {
        using var document=new System.Drawing.Printing.PrintDocument{DocumentName=title,PrintController=new System.Drawing.Printing.StandardPrintController()};
        document.DefaultPageSettings.Margins=new System.Drawing.Printing.Margins(0,0,0,0);
        // Indian document templates are A4; match wide GST/report PDFs too.
        foreach(System.Drawing.Printing.PaperSize paper in document.PrinterSettings.PaperSizes)
            if(paper.Kind==System.Drawing.Printing.PaperKind.A4){document.DefaultPageSettings.PaperSize=paper;break;}
        using(var firstInput=new MemoryStream(pages[0]))
        using(var firstImage=System.Drawing.Image.FromStream(firstInput))
            document.DefaultPageSettings.Landscape=firstImage.Width>firstImage.Height;
        document.PrinterSettings.MinimumPage=1;document.PrinterSettings.MaximumPage=pages.Count;document.PrinterSettings.FromPage=1;document.PrinterSettings.ToPage=pages.Count;
        using var dialog=new System.Windows.Forms.PrintDialog{Document=document,UseEXDialog=true,AllowSomePages=true,AllowSelection=false};
        if(dialog.ShowDialog(new Owner(handle))!=System.Windows.Forms.DialogResult.OK)return;
        var first=document.PrinterSettings.PrintRange==System.Drawing.Printing.PrintRange.SomePages?document.PrinterSettings.FromPage-1:0;
        var last=document.PrinterSettings.PrintRange==System.Drawing.Printing.PrintRange.SomePages?document.PrinterSettings.ToPage-1:pages.Count-1;
        if(first<0||last>=pages.Count||first>last)throw new ArgumentException("Choose a valid page range.");
        var index=first;document.BeginPrint+=(_,_)=>index=first;
        document.PrintPage+=(_,args)=>{using var input=new MemoryStream(pages[index]);using var image=System.Drawing.Image.FromStream(input);var bounds=args.PageBounds;var scale=Math.Min((float)bounds.Width/image.Width,(float)bounds.Height/image.Height);var width=image.Width*scale;var height=image.Height*scale;args.Graphics!.TranslateTransform(-args.PageSettings.HardMarginX,-args.PageSettings.HardMarginY);args.Graphics.DrawImage(image,(bounds.Width-width)/2,(bounds.Height-height)/2,width,height);args.HasMorePages=++index<=last;};
        document.Print();
        }
        finally
        {
            // WinForms/driver dialogs can leave a foreign WinUI owner disabled.
            // Restore only the state owned by this completed print operation.
            if(ownerWasEnabled)EnableWindow(handle,true);
        }
    }
}
