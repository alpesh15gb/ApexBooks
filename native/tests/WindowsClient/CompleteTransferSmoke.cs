using System.Text;
using System.Text.Json.Nodes;
using ApexBooks_Windows.Services;

static class CompleteTransferSmoke
{
 public static async Task Run(string origin)
 {
  if(!Uri.TryCreate(origin,UriKind.Absolute,out var uri)||uri.Scheme!="http"||!new[]{"127.0.0.1","localhost","[::1]"}.Contains(uri.Host)||uri.AbsolutePath!="/")throw new InvalidOperationException("Smoke accepts explicit loopback HTTP origin only.");
  using var handler=new HttpClientHandler{AllowAutoRedirect=false};using var api=new ApexApi(origin,handler);var email="native-backup-"+Guid.NewGuid().ToString("N")+"@example.invalid";const string password="Synthetic-backup-only-password-42";
  await api.Send("/api/auth/register",HttpMethod.Post,new JsonObject{["email"]=email,["password"]=password});await api.Login(email,password,false);await api.EnsureCapabilities();if(!api.Capabilities.Supports("document_attachments")||!api.Capabilities.Supports("chunked_backups"))throw new Exception("Local API does not advertise complete transfer capabilities.");
  var company=await api.Send("/api/companies",HttpMethod.Post,new JsonObject{["name"]="Windows synthetic complete backup",["tax_mode"]="unregistered"});var cid=company.Text("id");var root=api.CompanyPath(cid);
  var record=await api.Send(root+"/records",HttpMethod.Post,JsonNode.Parse("{\"kind\":\"purchase_bill\",\"name\":\"Synthetic supplier\",\"date\":\"2026-04-02\",\"data\":{\"lines\":[{\"description\":\"Synthetic supplies\",\"quantity\":1,\"rate\":100,\"gst_rate\":0}]}}"),Guid.NewGuid().ToString());
  var prefix=Encoding.ASCII.GetBytes("%PDF-1.4\n% Synthetic native transfer evidence\n");var suffix=Encoding.ASCII.GetBytes("\n%%EOF\n");var bytes=prefix.Concat(System.Security.Cryptography.RandomNumberGenerator.GetBytes(600000)).Concat(suffix).ToArray();var uploadPath=root+"/records/"+record.Text("id")+"/attachments?filename=synthetic.pdf";var key=Guid.NewGuid().ToString();
  var receipt=(await api.SendBytes(uploadPath,HttpMethod.Post,bytes,"application/pdf",key))["attachment"]!.AsObject();var replay=(await api.SendBytes(uploadPath,HttpMethod.Post,bytes,"application/pdf",key))["attachment"]!;if(receipt.Text("id")!=replay.Text("id"))throw new Exception("Receipt retry duplicated evidence.");
  await api.Send(root+"/attachments/"+receipt.Text("id"),HttpMethod.Put,new JsonObject{["version"]=receipt["version"].Copy(),["is_archived"]=true},Guid.NewGuid().ToString());
  var export=new CompleteBackupTransfer(api);using var archive=await export.DownloadExport(cid);if(archive.Length<=CompleteBackupTransfer.ChunkSize)throw new Exception("Fixture did not exercise multiple chunks.");
  var import=new CompleteBackupTransfer(api);var preview=await import.UploadAndPreview(archive,"Windows restored synthetic backup");if(preview.Number("attachment_count")!=1)throw new Exception("Preview omitted retained evidence.");var restored=await import.Commit();var repeated=await import.Commit();if(restored.Text("company_id")!=repeated.Text("company_id"))throw new Exception("Commit replay duplicated company.");
  var restoredId=restored.Text("company_id");var records=await api.Records(restoredId);var bill=records.Single(x=>x.Text("kind")=="purchase_bill");var listed=await api.Send(api.CompanyPath(restoredId,"/records/"+bill.Text("id")+"/attachments"));var evidence=listed["attachments"]!.AsArray().Single()!;if(!evidence.Flag("is_archived"))throw new Exception("Archive lineage was lost.");
  var downloaded=await api.DownloadBounded(api.CompanyPath(restoredId,"/attachments/"+evidence.Text("id")+"/download"),2*1024*1024);CompleteBackupTransfer.VerifyHash(downloaded.Bytes,CompleteBackupTransfer.Hash(bytes));CompleteBackupTransfer.VerifyHash(downloaded.Bytes,downloaded.Sha256);await export.Cancel(cid);
  foreach(var variant in new[]{(Kind:"estimate",Rate:"100",Gst:"0",Inclusive:false,DocumentDiscount:"0",Expected:90m),(Kind:"purchase_order",Rate:"118",Gst:"18",Inclusive:true,DocumentDiscount:"10",Expected:97.2m)}){
   var sourceLine=new JsonObject{["description"]="Fixed discount reopen fixture",["quantity"]="1",["rate"]=variant.Rate,["gst_rate"]=variant.Gst,["price_includes_tax"]=variant.Inclusive,["discount_amount"]="10"};
   var body=new JsonObject{["kind"]=variant.Kind,["name"]="Synthetic fixed discount party",["date"]="2026-04-02",["data"]=new JsonObject{["lines"]=new JsonArray(sourceLine),["document_discount_percent"]=variant.DocumentDiscount}};
   var draft=await api.Send(root+"/records",HttpMethod.Post,body,Guid.NewGuid().ToString());if(draft.Number("amount")!=variant.Expected)throw new Exception("Original fixed discount fixture total wrong.");var fresh=await api.Record(cid,draft.Text("id"));var savedLine=fresh["data"]!["lines"]![0]!.AsObject();
   var model=new LineDiscountState(savedLine);var submittedLine=new JsonObject();foreach(var field in new[]{"description","quantity","rate","gst_rate","price_includes_tax","tax_treatment"})if(savedLine.ContainsKey(field))submittedLine[field]=savedLine[field].Copy();model.WriteTo(submittedLine);
   var editedData=fresh["data"].Copy().Object();editedData["lines"]=new JsonArray(submittedLine);editedData["notes"]="Reopened through native discount state";var edited=new JsonObject{["kind"]=variant.Kind,["name"]=fresh.Text("name"),["number"]=fresh.Text("number"),["date"]=fresh.Text("date"),["data"]=editedData};
   var calculated=await api.Send(root+"/documents/preview",HttpMethod.Post,edited);if(calculated.Number("amount")!=variant.Expected)throw new Exception("Native reopened discount changed preview total.");var updated=await api.Send(root+"/drafts/"+fresh.Text("id"),HttpMethod.Put,edited,Guid.NewGuid().ToString());if(updated.Number("amount")!=variant.Expected||updated["data"]!["lines"]![0]!.Text("discount_amount")!="10")throw new Exception("Native draft save lost fixed discount.");
   Console.WriteLine($"PASS live native fixed discount {variant.Kind}: reopen, preview and save retain total {variant.Expected} with inclusive={variant.Inclusive}, document_discount={variant.DocumentDiscount}");
  }
  await api.Logout();
  Console.WriteLine("PASS live Windows service: receipt retry/archive, multi-chunk verified ZIP export, preview, exact commit replay, new-company archived evidence SHA256");
 }
}
