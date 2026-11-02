using System.Security.Cryptography;
using System.Text;
using System.Text.Json.Nodes;
using ApexBooks.BackupStreaming;

const string Password="cross-platform-test-only";
var directory=Path.Combine(Path.GetTempPath(),"apex-stream-tests-"+Guid.NewGuid().ToString("N"));Directory.CreateDirectory(directory);
void Check(bool condition,string name){if(!condition)throw new Exception(name);Console.WriteLine("PASS "+name);}
byte[] Legacy(byte[] plain)=>LegacyBackup.EncryptBackup(plain,Password);
byte[] Read(Stream stream){using var result=new MemoryStream();stream.CopyTo(result);return result.ToArray();}
void Reject(byte[] envelope,string name,string password=Password,CancellationToken cancel=default,long max=StreamingEncryptedBackup.DefaultLimit){try{using var plain=StreamingEncryptedBackup.DecryptAuthenticated(new MemoryStream(envelope),password,directory,max,cancel);throw new Exception("Accepted "+name);}catch(Exception e)when(e is InvalidDataException or OperationCanceledException or Org.BouncyCastle.Crypto.InvalidCipherTextException){Check(Directory.GetFiles(directory).Length==0,name+" rejected and staging removed");}}
try{
 var fixtures=Path.Combine(AppContext.BaseDirectory,"Fixtures");
 foreach(var (name,payload,password) in new[]{
  ("android-compatible-v1.json","android-compatible-v1.bin",Password),
  ("android-streaming-v1.json","android-compatible-v1.bin",Password),
  ("android-unicode-v1.json","android-compatible-v1.bin","cross-platform-₹-test-🔒"),
  ("csharp-legacy-v1.json","csharp-legacy-v1.bin",Password),
  ("csharp-escaped-reordered-v1.json","csharp-legacy-v1.bin",Password),
  ("csharp-legacy-unicode-password-v1.json","csharp-legacy-v1.bin","cross-platform-₹-test-🔒")}){
  using var expected=File.OpenRead(Path.Combine(fixtures,payload));using var input=File.OpenRead(Path.Combine(fixtures,name));using var actual=StreamingEncryptedBackup.DecryptAuthenticated(input,password,directory);
  Check(SHA256.HashData(actual).SequenceEqual(SHA256.HashData(expected)),"checked-in crosswriter fixture "+name);
 }
 var plain=RandomNumberGenerator.GetBytes(100003);var old=Legacy(plain);
 if(args.Length>=2&&args[0]=="--fixtures"){Directory.CreateDirectory(args[1]);File.WriteAllBytes(Path.Combine(args[1],"csharp-legacy-v1.json"),old);File.WriteAllBytes(Path.Combine(args[1],"csharp-legacy-v1.bin"),plain);File.WriteAllBytes(Path.Combine(args[1],"csharp-legacy-unicode-password-v1.json"),LegacyBackup.EncryptBackup(plain,"cross-platform-₹-test-🔒"));}
 using(var decrypted=StreamingEncryptedBackup.DecryptAuthenticated(new MemoryStream(old),Password,directory)){Check(Read(decrypted).SequenceEqual(plain),"legacy .NET writer to streaming reader");Check(Directory.GetFiles(directory).Length==1,"only authenticated plaintext staging remains");}Check(Directory.GetFiles(directory).Length==0,"dispose removes authenticated plaintext staging");
 using var encrypted=new MemoryStream();StreamingEncryptedBackup.Encrypt(new MemoryStream(plain),encrypted,Password);var envelope=JsonNode.Parse(encrypted.ToArray())!;var cipher=Convert.FromBase64String(envelope["ciphertext"]!.GetValue<string>());var salt=Convert.FromBase64String(envelope["salt"]!.GetValue<string>());var iv=Convert.FromBase64String(envelope["iv"]!.GetValue<string>());var key=Rfc2898DeriveBytes.Pbkdf2(Encoding.UTF8.GetBytes(Password),salt,250000,HashAlgorithmName.SHA256,32);var result=new byte[cipher.Length-16];using(var aes=new AesGcm(key,16))aes.Decrypt(iv,cipher.AsSpan(0,result.Length),cipher.AsSpan(result.Length),result);CryptographicOperations.ZeroMemory(key);Check(result.SequenceEqual(plain),"streaming writer to legacy .NET reader");
 var reordered="{\"ciphertext\":\""+envelope["ciphertext"]!.GetValue<string>().Replace("+","\\u002b").Replace("/","\\/").Replace("=","\\u003d")+"\",\"iv\":"+envelope["iv"]!.ToJsonString()+",\"version\":1,\"salt\":"+envelope["salt"]!.ToJsonString()+",\"format\":\"apex-encrypted-backup\"}";
 if(args.Length>=2&&args[0]=="--fixtures")File.WriteAllText(Path.Combine(args[1],"csharp-escaped-reordered-v1.json"),reordered);
 using(var decrypted=StreamingEncryptedBackup.DecryptAuthenticated(new MemoryStream(Encoding.UTF8.GetBytes(reordered)),Password,directory))Check(Read(decrypted).SequenceEqual(plain),"ciphertext first with escaped base64 Unicode and slash");
 var escapedPlain=RandomNumberGenerator.GetBytes(32*1024);var escapedEnvelope=JsonNode.Parse(Legacy(escapedPlain))!;
 var escapedCipher=string.Concat(escapedEnvelope["ciphertext"]!.GetValue<string>().Select(c=>"\\u"+((int)c).ToString("x4")));
 var fullyEscaped="{\"ciphertext\":\""+escapedCipher+"\",\"iv\":"+escapedEnvelope["iv"]!.ToJsonString()+",\"version\":1,\"salt\":"+escapedEnvelope["salt"]!.ToJsonString()+",\"format\":\"apex-encrypted-backup\"}";
 using(var decoded=StreamingEncryptedBackup.DecryptAuthenticated(new MemoryStream(Encoding.UTF8.GetBytes(fullyEscaped)),Password,directory,escapedPlain.Length))Check(Read(decoded).SequenceEqual(escapedPlain),"every ciphertext symbol Unicode-escaped at exact32KiB plaintext limit");
 Reject(Encoding.UTF8.GetBytes(fullyEscaped),"escaped envelope still enforces decoded plaintext limit",max:escapedPlain.Length-1);
 Reject(old,"wrong password","wrong password");var damaged=JsonNode.Parse(old)!;var bytes=Convert.FromBase64String(damaged["ciphertext"]!.GetValue<string>());bytes[200]^=1;damaged["ciphertext"]=Convert.ToBase64String(bytes);Reject(Encoding.UTF8.GetBytes(damaged.ToJsonString()),"ciphertext tamper");bytes[200]^=1;bytes[^1]^=1;damaged["ciphertext"]=Convert.ToBase64String(bytes);Reject(Encoding.UTF8.GetBytes(damaged.ToJsonString()),"tag tamper");
 Reject(old[..^2],"truncated JSON");damaged=JsonNode.Parse(old)!;damaged["ciphertext"]=Convert.ToBase64String(bytes[..^17]);Reject(Encoding.UTF8.GetBytes(damaged.ToJsonString()),"truncated ciphertext");Reject(old,"size bound",max:100);Reject(old,"cancellation",cancel:new CancellationToken(true));
 foreach(var bad in new[]{"{\"format\":\"apex-encrypted-backup\",\"format\":\"x\"}",Encoding.UTF8.GetString(old).Replace("\"version\":1","\"version\":2"),Encoding.UTF8.GetString(old)+"x"})Reject(Encoding.UTF8.GetBytes(bad),"invalid envelope structure");
 foreach(var mutation in new[]{"salt","iv","base64","escape","duplicate"}){
  var bad=JsonNode.Parse(old)!;string badJson;
  if(mutation is "salt" or "iv"){bad[mutation]="AA==";badJson=bad.ToJsonString();}
  else if(mutation=="base64"){bad["ciphertext"]="AAAA!AAA";badJson=bad.ToJsonString();}
  else if(mutation=="escape")badJson=Encoding.UTF8.GetString(old).Replace("apex-encrypted-backup","apex\\qencrypted-backup");
  else badJson=Encoding.UTF8.GetString(old).Replace("{","{\"version\":1,",StringComparison.Ordinal);
  Reject(Encoding.UTF8.GetBytes(badJson),mutation+" validation");
 }
 using(var empty=new MemoryStream()){StreamingEncryptedBackup.Encrypt(Stream.Null,empty,Password);empty.Position=0;using var decrypted=StreamingEncryptedBackup.DecryptAuthenticated(empty,Password,directory);Check(decrypted.Length==0,"empty plaintext with valid authentication tag");}
 if(args.Contains("--large")||args.Contains("--max")){
  var file=Path.Combine(directory,"large.encrypted");var size=(args.Contains("--max")?320L:128L)*1024*1024;var clock=System.Diagnostics.Stopwatch.StartNew();
  using(var output=File.Create(file))StreamingEncryptedBackup.Encrypt(new PatternStream(size),output,Password,size);
  using(var input=File.OpenRead(file))using(var decoded=StreamingEncryptedBackup.DecryptAuthenticated(input,Password,directory,size)){using var expected=new PatternStream(size);Check(decoded.Length==size&&SHA256.HashData(decoded).SequenceEqual(SHA256.HashData(expected)),$"{size/1024/1024}MiB bounded encrypted roundtrip");}
  using(var cancel=new CancellationTokenSource()){
   var watch=Task.Run(async()=>{while(!cancel.IsCancellationRequested){if(Directory.GetFiles(directory,"*.stage").Length==2){cancel.Cancel();break;}await Task.Delay(1);}});
   try{using var input=File.OpenRead(file);using var decoded=StreamingEncryptedBackup.DecryptAuthenticated(input,Password,directory,size,cancel.Token);throw new Exception("Expected mid-decryption cancellation");}catch(OperationCanceledException){Check(Directory.GetFiles(directory,"*.stage").Length==0,"mid-decryption cancellation removes plaintext and ciphertext staging");}finally{cancel.Cancel();watch.GetAwaiter().GetResult();}
  }
  File.Delete(file);Console.WriteLine($"MEMORY managed_peak_bound={GC.GetGCMemoryInfo().TotalAvailableMemoryBytes} process_peak_working_set={System.Diagnostics.Process.GetCurrentProcess().PeakWorkingSet64} elapsed_ms={clock.ElapsedMilliseconds}");
 }
 if(args.Length>=3&&args[0]=="--cross-read"){using var input=File.OpenRead(args[1]);using var decoded=StreamingEncryptedBackup.DecryptAuthenticated(input,args.Length>=4?args[3]:Password,directory);Check(SHA256.HashData(decoded).SequenceEqual(Convert.FromHexString(args[2])),"Android existing writer cross-platform decryption");}
 if(args.Length>=2&&args[0]=="--cross-write"){using var output=File.Create(args[1]);StreamingEncryptedBackup.Encrypt(new MemoryStream(Encoding.UTF8.GetBytes("Apex Books synthetic cross-platform backup v1\n")),output,Password);Console.WriteLine("CROSS_SHA256 "+Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes("Apex Books synthetic cross-platform backup v1\n"))));}
 Check(Directory.GetFiles(directory).Length==0,"all private staging removed");
}finally{Directory.Delete(directory,true);}

sealed class PatternStream(long size):Stream
{
 long position;public override bool CanRead=>true;public override bool CanSeek=>false;public override bool CanWrite=>false;public override long Length=>size;public override long Position{get=>position;set=>throw new NotSupportedException();}
 public override int Read(byte[] buffer,int offset,int count){var n=(int)Math.Min(count,size-position);for(var i=0;i<n;i++)buffer[offset+i]=(byte)((position+i)*31+17);position+=n;return n;}public override void Flush(){}public override long Seek(long offset,SeekOrigin origin)=>throw new NotSupportedException();public override void SetLength(long value)=>throw new NotSupportedException();public override void Write(byte[] buffer,int offset,int count)=>throw new NotSupportedException();
}

// Verbatim legacy ApexFiles.EncryptBackup, isolated from WinUI dependencies for interoperability.
static class LegacyBackup
{
    public static byte[] EncryptBackup(byte[] gzip, string password)
    {
        if (password.Length < 12) throw new Exception("Use a backup password of at least 12 characters.");
        var salt = RandomNumberGenerator.GetBytes(16); var iv = RandomNumberGenerator.GetBytes(12);
        var key = Rfc2898DeriveBytes.Pbkdf2(Encoding.UTF8.GetBytes(password), salt, 250000, HashAlgorithmName.SHA256, 32);
        try
        {
            var cipher = new byte[gzip.Length]; var tag = new byte[16]; using var aes = new AesGcm(key, 16); aes.Encrypt(iv, gzip, cipher, tag);
            return Encoding.UTF8.GetBytes(new JsonObject { ["format"] = "apex-encrypted-backup", ["version"] = 1, ["salt"] = Convert.ToBase64String(salt), ["iv"] = Convert.ToBase64String(iv), ["ciphertext"] = Convert.ToBase64String(cipher.Concat(tag).ToArray()) }.ToJsonString());
        }
        finally { CryptographicOperations.ZeroMemory(key); }
    }

}
