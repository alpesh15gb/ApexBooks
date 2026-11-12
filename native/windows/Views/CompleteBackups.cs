using ApexBooks.BackupStreaming;
using System.Text.Json.Nodes;
using ApexBooks_Windows.Services;
using Microsoft.UI.Xaml.Controls;
using static ApexBooks_Windows.Views.NativeUi;

namespace ApexBooks_Windows;
public sealed partial class MainPage
{
    private async Task RecoverCompleteTransfers()
    {
        RequireFeature("chunked_backups");var cid=CompanyId;var epoch=generation;var response=await Api.Send("/api/backups/transfers");if(epoch!=generation)return;var panel=Stack();panel.Children.Add(Text("Resume an immutable transfer or cancel its staging. This never deletes source books or a restored company. For import, select the same original backup; its length and complete SHA256 must match.",12));JsonObject? selected=null;var cancel=false;
        foreach(var row in response["transfers"].Array().OfType<JsonObject>().Where(row=>row.Text("direction")!="export"||row.Text("source_company_id")==cid)){
            var transfer=row;var card=Stack();card.Children.Add(Text(transfer.Text("direction")+" · "+transfer.Text("target_company_name")+" · "+transfer.Text("state"),16,true));card.Children.Add(Text((transfer.Text("upload_id")+transfer.Text("export_id"))+" · expires "+transfer.Text("expires_at"),12));card.Children.Add(Button(transfer.Text("state")=="restored"?"Open restored company":"Resume this transfer",()=>{selected=transfer;CloseDialog();},true));if(transfer.Text("state")!="restored")card.Children.Add(Button("Cancel staging only",()=>{selected=transfer;cancel=true;CloseDialog();}));panel.Children.Add(Card(card));}
        if(panel.Children.Count==1)panel.Children.Add(Text("No active transfers to recover."));await Dialog("Recover complete backup transfers",panel,()=>Task.CompletedTask,"Done");if(epoch!=generation||selected is null)return;
        if(selected.Text("state")=="restored"){CompanyId=selected.Text("company_id");await LoadCompanies();return;}
        if(cancel){await new CompleteBackupTransfer(Api,selected).Cancel(selected.Text("direction")=="export"?cid:null);Success("Transfer staging cancelled. No company data was deleted.");}
        else if(selected.Text("direction")=="export")await CompleteBackupCompany(selected);else await RestoreCompleteCompany(selected);
    }
    private async Task CompleteBackupCompany(JsonObject? resume=null)
    {
        RequireFeature("chunked_backups");if(Company.Text("role")!="owner")throw new Exception("Only the company owner can create a complete backup.");var cid=CompanyId;var epoch=generation;var exportAccess=CaptureFileSaveAccess();var transfer=new CompleteBackupTransfer(Api,resume);var password=new PasswordBox{Header="Backup password · at least 12 characters"};var encrypt=new CheckBox{Content="Encrypt portable backup locally (recommended)",IsChecked=true};var progress=Text("Complete ZIP includes books and every retained receipt, including archived evidence.");var panel=Stack();panel.Children.Add(progress);panel.Children.Add(encrypt);panel.Children.Add(password);panel.Children.Add(Text("The passphrase never leaves this device. Server transfer carries authenticated company data over HTTPS. Keep your saved backup and passphrase safe; lost passphrases cannot be recovered.",12));
        await Dialog("Complete portable backup",panel,async()=>{await ScopedFileExport.Run(exportAccess,async()=>{
            if(encrypt.IsChecked==true&&password.Password.Length<12)throw new Exception("Use a backup password of at least 12 characters.");using var archive=await transfer.DownloadExport(cid,new Progress<string>(value=>{if(ScopedFileExport.Current(exportAccess))progress.Text=value;}));exportAccess();if(cid!=CompanyId||epoch!=generation)return false;
            progress.Text="Verified complete archive. Snapshot "+transfer.Metadata.Text("export_id")+" · expires "+transfer.Metadata.Text("expires_at");
            if(encrypt.IsChecked==true){using var encrypted=CompleteBackupTransfer.Stage();var passphrase=password.Password;await Task.Run(()=>StreamingEncryptedBackup.Encrypt(archive,encrypted,passphrase,transfer.Limit));exportAccess();if(!await ApexFiles.SaveStream(encrypted,$"apex-complete-{J.Today}.apexbackup",exportAccess))throw new Exception("No file was saved. Retry to save the same immutable snapshot.");}
            else if(!await ApexFiles.SaveStream(archive,$"apex-complete-{J.Today}.zip",exportAccess))throw new Exception("No file was saved. Retry to save the same immutable snapshot.");
            try{await transfer.Cancel(cid);}catch{/* A saved backup remains successful; server staging expires without changing books. */}
            return true;});
        },"Verify and save backup",unresolved:()=>transfer.Pending);
    }
    private async Task RestoreCompleteCompany(JsonObject? resume=null)
    {
        RequireFeature("chunked_backups");var epoch=generation;var file=await ApexFiles.Pick(".apexbackup",".zip",".gz",".json");if(file is null||epoch!=generation)return;var transfer=new CompleteBackupTransfer(Api,resume);var name=Input("Name for the NEW restored company");if(resume is not null){name.Text=resume.Text("target_company_name");name.IsEnabled=false;}var password=new PasswordBox{Header="Encrypted backup passphrase"};var encrypted=new CheckBox{Content="This file uses Apex encrypted-backup v1",IsChecked=Path.GetExtension(file.Name).Equals(".apexbackup",StringComparison.OrdinalIgnoreCase)};var panel=Stack();panel.Children.Add(Text(file.Name,18,true));panel.Children.Add(Text("Restore creates a separate company; it never overwrites your current books. Validate and review totals and retained evidence before confirming. No automatic fallback from a failed encrypted file to plaintext.",12));panel.Children.Add(name);panel.Children.Add(encrypted);panel.Children.Add(password);var progress=Text("Choose the correct file format. Passphrases are used only on this device.");var report=Stack();panel.Children.Add(progress);FileStream? prepared=null;var reviewedName="";var committed=false;
        try{
            panel.Children.Add(AsyncButton("Validate / resume and preview",async()=>{
                if(transfer.Pending&&transfer.Preview is not null)throw new Exception("The restore may already have committed. Use Restore reviewed backup to recover the same company.");
                if(prepared is null){if(string.IsNullOrWhiteSpace(name.Text))throw new Exception("Enter a new company name.");using var source=await file.OpenStreamForReadAsync();if(encrypted.IsChecked==true){var passphrase=password.Password;prepared=await Task.Run(()=>StreamingEncryptedBackup.DecryptAuthenticated(source,passphrase,CompleteBackupTransfer.PrivateDirectory,transfer.Limit));}else{prepared=CompleteBackupTransfer.Stage();try{if(source.Length>transfer.Limit)throw new Exception("Backup exceeds this server's size limit.");var buffer=new byte[32768];int read;while((read=await source.ReadAsync(buffer))>0){if(prepared.Length+read>transfer.Limit)throw new Exception("Backup exceeds this server's size limit.");await prepared.WriteAsync(buffer.AsMemory(0,read));}prepared.Position=0;}catch{prepared.Dispose();prepared=null;throw;}}reviewedName=name.Text.Trim();name.IsEnabled=false;password.IsEnabled=false;encrypted.IsEnabled=false;}
                if(epoch!=generation)throw new OperationCanceledException("Workspace changed. Recover the transfer in the original account.");var result=await transfer.UploadAndPreview(prepared,reviewedName,new Progress<string>(value=>progress.Text=value));if(epoch!=generation)return;progress.Text="Upload "+transfer.Metadata.Text("upload_id")+" · expires "+transfer.Metadata.Text("expires_at")+" · Complete SHA256 verified. Review below before creating the new company.";report.Children.Clear();RenderReport(report,result);
            },Error,true));panel.Children.Add(report);
            var saved=await Dialog("Restore complete backup into a new company",panel,async()=>{if(transfer.Preview is null)throw new Exception("Validate and preview before restoring.");var result=await transfer.Commit();committed=true;if(epoch==generation)CompanyId=result.Text("company_id");},"Restore reviewed backup",unresolved:()=>transfer.Pending);
            if(saved&&epoch==generation)await LoadCompanies();
        }finally{prepared?.Dispose();if(!committed&&!transfer.Pending&&transfer.Metadata is not null){try{await transfer.Cancel();}catch{/* Stage expiry is bounded; cancellation never deletes a company. */}}}
    }
}
