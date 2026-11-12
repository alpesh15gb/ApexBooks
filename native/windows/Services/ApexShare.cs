using System.Diagnostics;

namespace ApexBooks_Windows.Services;

public static class ApexShare
{
    public static async Task Show(byte[] bytes,string filename,Action? verify=null)
    {
        verify?.Invoke();
        var clean=string.Concat(filename.Select(c=>Path.GetInvalidFileNameChars().Contains(c)?'_':c));
        if(string.IsNullOrWhiteSpace(clean))clean="Apex-Books-document.pdf";
        var folder=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"ApexBooks","Shared",Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(folder);
        var path=Path.Combine(folder,clean);
        await File.WriteAllBytesAsync(path,bytes);
        try{verify?.Invoke();}catch{try{File.Delete(path);Directory.Delete(folder);}catch{}throw;}
        var start=new ProcessStartInfo(Environment.ProcessPath??throw new Exception("The native share host is unavailable.")){
            UseShellExecute=false,WindowStyle=ProcessWindowStyle.Normal
        };
        start.ArgumentList.Add("--share-pdf");start.ArgumentList.Add(path);
        verify?.Invoke();using var process=Process.Start(start)??throw new Exception("Windows could not open sharing. Save the PDF and try again.");
    }
}
