using System.Net.Http;
using System.Text.Json.Nodes;
using ApexBooks_Windows.Services;
using Microsoft.UI.Xaml.Controls;
using static ApexBooks_Windows.Views.NativeUi;

namespace ApexBooks_Windows;
public sealed partial class MainPage
{
    private async Task RetainedReceipts(JsonObject record)
    {
        RequireFeature("document_attachments");var cid=CompanyId;var epoch=generation;var exportAccess=CaptureFileSaveAccess();var root=Api.CompanyPath(cid);var path=Api.CompanyPath(cid,$"/records/{Uri.EscapeDataString(record.Text("id"))}/attachments");var panel=Stack();var rows=Stack();var status=Text("Loading retained evidence…");panel.Children.Add(Text("Retained receipts · "+record.Text("number"),22,true));panel.Children.Add(Text("PDF, JPEG or PNG evidence only. No automatic viewing, OCR or changes to books. Archived files remain in complete backups and storage quota.",12));panel.Children.Add(status);
        byte[]? pendingBytes=null;JsonObject? pendingArchive=null;string pendingPath="",media="",key="";var retry=new RetrySubmission();
        bool Current()=>cid==CompanyId&&epoch==generation&&Api.SignedIn;
        async Task Recover(){if(!Current())return;try{if(pendingBytes is not null)await Api.SendBytes(pendingPath,HttpMethod.Post,pendingBytes,media,key);else if(pendingArchive is not null)await Api.Send(pendingPath,HttpMethod.Put,retry.Body(pendingArchive),key);else return;retry.Succeeded();pendingBytes=null;pendingArchive=null;await Load();}catch(Exception error){retry.Failed(error);if(!retry.Unresolved){pendingBytes=null;pendingArchive=null;}throw;}}
        async Task Load(){await ScopedFileExport.Run(exportAccess,async()=>{if(!Current())return false;var data=await Api.Send(path);if(!Current()||!ScopedFileExport.Current(exportAccess))return false;var storage=data["storage"].Object();status.Text=$"Storage {storage.Text("used_bytes")} / {storage.Text("quota_bytes")} bytes · max {storage.Text("max_file_bytes")} bytes per file · archived evidence counts.";rows.Children.Clear();foreach(var entry in data["attachments"].Array()){
            var item=entry!.Object();var card=Stack();card.Children.Add(Text(item.Text("filename")+(item.Flag("is_archived")?" · Archived":""),16,true));card.Children.Add(Text(item.Text("media_type")+" · "+item.Text("size_bytes")+" bytes · SHA256 "+item.Text("sha256"),11));
            card.Children.Add(AsyncButton("Download verified copy",async()=>{await ScopedFileExport.Run(exportAccess,async()=>{if(retry.Unresolved)throw new Exception("Recover the pending receipt change first.");var maximum=(int)Api.Capabilities.Limit("attachment_max_file_bytes",2*1024*1024,16*1024*1024);var result=await Api.DownloadBounded(Api.CompanyPath(cid,$"/attachments/{Uri.EscapeDataString(item.Text("id"))}/download"),maximum);exportAccess();CompleteBackupTransfer.VerifyHash(result.Bytes,item.Text("sha256"));CompleteBackupTransfer.VerifyHash(result.Bytes,result.Sha256);if(result.Bytes.Length!=(long)item.Number("size_bytes"))throw new Exception("Receipt size mismatch.");if(!Current())return false;return await ApexFiles.Save(result.Bytes,item.Text("filename"),exportAccess);});},Error));
            if(CanWrite)card.Children.Add(AsyncButton(item.Flag("is_archived")?"Reactivate retained receipt":"Archive retained receipt",async()=>{if(retry.Unresolved)throw new Exception("Use Retry original receipt change first.");pendingArchive=new(){["version"]=item["version"].Copy(),["is_archived"]=!item.Flag("is_archived")};pendingPath=root+"/attachments/"+Uri.EscapeDataString(item.Text("id"));key=Guid.NewGuid().ToString();retry.Body(pendingArchive);await Recover();},Error));rows.Children.Add(Card(card));}
            if(rows.Children.Count==0)rows.Children.Add(Text("No retained receipts. Upload original evidence to keep it with this transaction."));return true;});}
        if(CanWrite)panel.Children.Add(AsyncButton("Choose receipt and upload",async()=>{if(retry.Unresolved)throw new Exception("Retry the original receipt change before choosing another file.");var file=await ApexFiles.Pick(".pdf",".jpg",".jpeg",".png");if(file is null||!Current())return;var extension=Path.GetExtension(file.Name).ToLowerInvariant();media=extension==".pdf"?"application/pdf":extension==".png"?"image/png":"image/jpeg";pendingBytes=await ApexFiles.Read(file,Api.Capabilities.Limit("attachment_max_file_bytes",2*1024*1024,16*1024*1024));if(!Current()){pendingBytes=null;return;}pendingPath=path+"?filename="+Uri.EscapeDataString(file.Name);key=Guid.NewGuid().ToString();retry.Body(new(){["filename"]=file.Name,["sha256"]=CompleteBackupTransfer.Hash(pendingBytes)});await Recover();},Error,true));
        panel.Children.Add(AsyncButton("Retry original receipt change",Recover,Error));panel.Children.Add(rows);await Load();if(!Current()||!ScopedFileExport.Current(exportAccess))return;
        void InvalidateRead(){rows.Children.Clear();status.Text="Company access removed or unavailable. Reopen retained receipts after access is restored. Pending changes remain in this dialog.";}
        ReadAccessInvalidated+=InvalidateRead;
        try{await Dialog("Retained receipt evidence",panel,()=>{if(retry.Unresolved)throw new Exception("The receipt change may already have succeeded. Retry the original change before closing.");return Task.CompletedTask;},"Done",unresolved:()=>retry.Unresolved);}finally{ReadAccessInvalidated-=InvalidateRead;}
    }
}
