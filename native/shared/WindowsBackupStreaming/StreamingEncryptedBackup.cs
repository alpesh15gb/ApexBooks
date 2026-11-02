using System.Security.Cryptography;
using System.Text;
using Org.BouncyCastle.Crypto.Engines;
using Org.BouncyCastle.Crypto.Modes;
using Org.BouncyCastle.Crypto.Parameters;

namespace ApexBooks.BackupStreaming;

/// <summary>Existing encrypted-backup v1 envelope; never exposes unauthenticated plaintext.
/// Synchronous bounded work: callers must run off the UI thread. Input/output ownership stays with caller.</summary>
public static class StreamingEncryptedBackup
{
    const int Block=48*1024;
    public const long DefaultLimit=320L*1024*1024;
    static FileStream Stage(string directory)
    {
        var options=new FileStreamOptions{Mode=FileMode.CreateNew,Access=FileAccess.ReadWrite,Share=FileShare.None,Options=FileOptions.DeleteOnClose|FileOptions.SequentialScan,BufferSize=Block};
        if(!OperatingSystem.IsWindows())options.UnixCreateMode=UnixFileMode.UserRead|UnixFileMode.UserWrite;
        return new FileStream(Path.Combine(directory,"apex-backup-"+Guid.NewGuid().ToString("N")+".stage"),options);
    }
    static byte[] Key(string password,byte[] salt){var encoded=Encoding.UTF8.GetBytes(password);try{return Rfc2898DeriveBytes.Pbkdf2(encoded,salt,250000,HashAlgorithmName.SHA256,32);}finally{CryptographicOperations.ZeroMemory(encoded);}}
    static GcmBlockCipher Cipher(bool encrypt,byte[] key,byte[] iv){var cipher=new GcmBlockCipher(new AesEngine());cipher.Init(encrypt,new AeadParameters(new KeyParameter(key),128,iv));return cipher;}
    static void ValidateLimit(long limit){if(limit<0||limit>DefaultLimit)throw new ArgumentOutOfRangeException(nameof(limit),"Choose a byte limit from zero through 320MiB.");}
    static void CheckLimit(long size,long limit){if(limit<0||size>limit)throw new InvalidDataException("Backup exceeds configured size limit.");}

    public static void Encrypt(Stream plaintext,Stream envelope,string password,long maxBytes=DefaultLimit,CancellationToken cancellation=default)
    {
        ValidateLimit(maxBytes);if(password.Length<12)throw new ArgumentException("Use a backup password of at least 12 characters.",nameof(password));
        cancellation.ThrowIfCancellationRequested();var salt=RandomNumberGenerator.GetBytes(16);var iv=RandomNumberGenerator.GetBytes(12);var key=Key(password,salt);
        var input=new byte[Block];var output=new byte[Block+32];
        try{
            var cipher=Cipher(true,key,iv);using var writer=new StreamWriter(envelope,new UTF8Encoding(false),Block,true);
            writer.Write("{\"format\":\"apex-encrypted-backup\",\"version\":1,\"salt\":\"");writer.Write(Convert.ToBase64String(salt));writer.Write("\",\"iv\":\"");writer.Write(Convert.ToBase64String(iv));writer.Write("\",\"ciphertext\":\"");
            // AES block chunks need not be base64 triplet aligned; preserve carry between calls.
            var encoder=new Base64Writer(writer);long total=0;int count;
            while((count=plaintext.Read(input))!=0){cancellation.ThrowIfCancellationRequested();CheckLimit(total+=count,maxBytes);encoder.Write(output,cipher.ProcessBytes(input,0,count,output,0));}
            cancellation.ThrowIfCancellationRequested();encoder.Write(output,cipher.DoFinal(output,0));encoder.Finish();writer.Write("\"}");writer.Flush();
        }finally{CryptographicOperations.ZeroMemory(key);CryptographicOperations.ZeroMemory(input);CryptographicOperations.ZeroMemory(output);}
    }

    /// <summary>Returns authenticated plaintext in an exclusive delete-on-close staging file.
    /// Caller must dispose it. On any parse/authentication/cancellation failure all staging is deleted.
    /// Directory must be an app-private directory, never a shared export/upload destination.</summary>
    public static FileStream DecryptAuthenticated(Stream envelope,string password,string privateDirectory,long maxBytes=DefaultLimit,CancellationToken cancellation=default)
    {
        ValidateLimit(maxBytes);cancellation.ThrowIfCancellationRequested();using var encrypted=Stage(privateDirectory);var parser=new EnvelopeReader(envelope,cancellation,maxBytes);var (salt,iv)=parser.Parse(encrypted);encrypted.Position=0;
        var key=Key(password,salt);var input=new byte[Block];var output=new byte[Block+32];FileStream? plain=null;
        try{
            plain=Stage(privateDirectory);var cipher=Cipher(false,key,iv);long total=0;int count;
            while((count=encrypted.Read(input))!=0){cancellation.ThrowIfCancellationRequested();var size=cipher.ProcessBytes(input,0,count,output,0);CheckLimit(total+=size,maxBytes);plain.Write(output,0,size);}
            cancellation.ThrowIfCancellationRequested();var final=cipher.DoFinal(output,0);CheckLimit(total+final,maxBytes);plain.Write(output,0,final);plain.Flush();cancellation.ThrowIfCancellationRequested();plain.Position=0;var authenticated=plain;plain=null;return authenticated;
        }finally{plain?.Dispose();CryptographicOperations.ZeroMemory(key);CryptographicOperations.ZeroMemory(input);CryptographicOperations.ZeroMemory(output);}
    }
    sealed class Base64Writer(TextWriter writer)
    {
        readonly byte[] buffer=new byte[Block+36];int used;
        public void Write(byte[] bytes,int length){var offset=0;while(offset<length){var take=Math.Min(buffer.Length-used,length-offset);Array.Copy(bytes,offset,buffer,used,take);used+=take;offset+=take;var ready=used-used%3;if(ready>0){writer.Write(Convert.ToBase64String(buffer,0,ready));Array.Copy(buffer,ready,buffer,0,used-ready);used-=ready;}}}
        public void Finish(){if(used>0)writer.Write(Convert.ToBase64String(buffer,0,used));CryptographicOperations.ZeroMemory(buffer);}
    }
    // Deliberately narrow bounded tokenizer for the frozen five-field envelope, not a general JSON parser.
    // Decodes JSON string escapes before strict base64 processing; property order is irrelevant.
    sealed class EnvelopeReader(Stream input,CancellationToken cancellation,long limit)
    {
        readonly StreamReader reader=new(input,new UTF8Encoding(false,true),false,Block,true);long characters;
        // A base64 symbol may use six JSON characters (\\uXXXX): roughly 8x decoded bytes, plus bounded metadata/padding.
        int Read(){cancellation.ThrowIfCancellationRequested();var c=reader.Read();if(c>=0&&++characters>checked((limit+16)*8+4096))throw new InvalidDataException("Envelope too large.");return c;}
        int Next(){int c;do{c=Read();}while(c is ' ' or '\r' or '\n' or '\t');return c;}
        static InvalidDataException Invalid()=>new("Invalid encrypted backup v1 envelope.");
        void String(Action<char> accept){while(true){var c=Read();if(c=='"')return;if(c<32)throw Invalid();if(c=='\\'){c=Read();c=c switch{'"'=>'"','\\'=>'\\','/'=>'/','b'=>'\b','f'=>'\f','n'=>'\n','r'=>'\r','t'=>'\t','u'=>Unicode(),_=>throw Invalid()};}accept((char)c);}}
        int Unicode(){var value=0;for(var i=0;i<4;i++){var c=Read();var digit=c is >= '0' and <= '9'?c-'0':c is >= 'a' and <= 'f'?c-'a'+10:c is >= 'A' and <= 'F'?c-'A'+10:-1;if(digit<0)throw Invalid();value=value*16+digit;}return value;}
        string Small(){var value=new StringBuilder();String(c=>{if(value.Length>=128)throw Invalid();value.Append(c);});return value.ToString();}
        public (byte[],byte[]) Parse(Stream ciphertext)
        {
            using(reader){if(Next()!='{')throw Invalid();var seen=new HashSet<string>();string? salt=null,iv=null;long bytes=0;
            while(true){if(Next()!='"')throw Invalid();var name=Small();if(!seen.Add(name)||Next()!=':')throw Invalid();var type=Next();
                if(name=="version"){if(type!='1')throw Invalid();}
                else{if(type!='"')throw Invalid();switch(name){case "format":if(Small()!="apex-encrypted-backup")throw Invalid();break;case "salt":salt=Small();break;case "iv":iv=Small();break;
                    case "ciphertext":var quartet=new char[4];var decoded=new byte[3];var buffer=new byte[Block];var used=0;var n=0;var ended=false;
                        String(c=>{if(ended||!(char.IsAsciiLetterOrDigit(c)||c is '+' or '/' or '='))throw Invalid();quartet[n++]=c;if(n==4){if(!Convert.TryFromBase64Chars(quartet,decoded,out var count))throw Invalid();ended=quartet[2]=='='||quartet[3]=='=';CheckLimit(bytes+=count,checked(limit+16));for(var i=0;i<count;i++)buffer[used++]=decoded[i];if(used==Block){ciphertext.Write(buffer);used=0;}n=0;}});if(n!=0||bytes<16)throw Invalid();ciphertext.Write(buffer,0,used);break;
                    default:throw Invalid();}}
                var delimiter=Next();if(delimiter=='}')break;if(delimiter!=',')throw Invalid();
            }
            if(seen.Count!=5||Next()!=-1||salt is null||iv is null)throw Invalid();byte[] saltBytes,ivBytes;try{saltBytes=Convert.FromBase64String(salt);ivBytes=Convert.FromBase64String(iv);}catch(FormatException){throw Invalid();}if(saltBytes.Length!=16||ivBytes.Length!=12)throw Invalid();return(saltBytes,ivBytes);}
        }
    }
}
