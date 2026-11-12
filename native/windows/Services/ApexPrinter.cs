using Windows.Data.Pdf;
using Windows.Storage.Streams;

namespace ApexBooks_Windows.Services;

/// <summary>Native Windows print dialog, including elevated desktop sessions.</summary>
public static class ApexPrinter
{
    public static async Task<int> PageCount(byte[] bytes){using var stream=new InMemoryRandomAccessStream();using(var writer=new DataWriter(stream)){writer.WriteBytes(bytes);await writer.StoreAsync();writer.DetachStream();}stream.Seek(0);return (int)(await PdfDocument.LoadFromStreamAsync(stream)).PageCount;}
    public static async Task<List<byte[]>> Raster(byte[] bytes,uint width=1800,int? selectedPage=null)
    {
        using var stream=new InMemoryRandomAccessStream();using(var writer=new DataWriter(stream)){writer.WriteBytes(bytes);await writer.StoreAsync();writer.DetachStream();}stream.Seek(0);var pdf=await PdfDocument.LoadFromStreamAsync(stream);var pages=new List<byte[]>();
        for(uint i=(uint)(selectedPage??0);i<pdf.PageCount&&(!selectedPage.HasValue||i==selectedPage.Value);i++){using var page=pdf.GetPage(i);using var output=new InMemoryRandomAccessStream();await page.RenderToStreamAsync(output,new PdfPageRenderOptions{DestinationWidth=width});using var reader=new DataReader(output.GetInputStreamAt(0));await reader.LoadAsync((uint)output.Size);var png=new byte[checked((int)output.Size)];reader.ReadBytes(png);pages.Add(png);}return pages;
    }
    public static async Task Print(byte[] bytes,string title,Action? verify=null)
    {
        verify?.Invoke();var pages=await Raster(bytes);verify?.Invoke();if(pages.Count==0)throw new Exception("This document has no pages to print.");
        ApexBooks.NativePrinting.NativePrintBridge.Print(pages,title,App.WindowHandle);
    }
}
