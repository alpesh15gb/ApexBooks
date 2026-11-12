using System.IO.Compression;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json.Nodes;
using Windows.Graphics.Imaging;
using Windows.Storage;
using Windows.Storage.Pickers;
using Windows.Storage.Streams;

namespace ApexBooks_Windows.Services;

public static class ApexFiles
{
    public static Func<Action>? CaptureSaveAccess { get; set; }
    public static async Task<StorageFile?> Pick(params string[] extensions)
    {
        var picker = new FileOpenPicker(); WinRT.Interop.InitializeWithWindow.Initialize(picker, App.WindowHandle);
        foreach (var extension in extensions) picker.FileTypeFilter.Add(extension);
        return await picker.PickSingleFileAsync();
    }

    public static async Task<bool> Save(byte[] bytes, string name, Action? originalAccess=null)
    {
        var verify=originalAccess??CaptureSaveAccess?.Invoke()??throw new InvalidOperationException("Save ownership is unavailable.");verify();
        var clean = string.Concat(name.Select(c => Path.GetInvalidFileNameChars().Contains(c) ? '_' : c));
        var picker = new FileSavePicker { SuggestedFileName = Path.GetFileNameWithoutExtension(clean) };
        picker.FileTypeChoices.Add("Apex Books " + Path.GetExtension(clean).Trim('.').ToUpperInvariant(), new List<string> { Path.GetExtension(clean) });
        WinRT.Interop.InitializeWithWindow.Initialize(picker, App.WindowHandle);
        var file = await picker.PickSaveFileAsync(); if (file is null) return false;
        verify();await FileIO.WriteBytesAsync(file, bytes);verify();return true;
    }

    public static async Task<bool> SaveStream(Stream source,string name,Action? originalAccess=null)
    {
        var verify=originalAccess??CaptureSaveAccess?.Invoke()??throw new InvalidOperationException("Save ownership is unavailable.");verify();
        var clean=string.Concat(name.Select(c=>Path.GetInvalidFileNameChars().Contains(c)?'_':c));var picker=new FileSavePicker{SuggestedFileName=Path.GetFileNameWithoutExtension(clean)};picker.FileTypeChoices.Add("Apex Books backup",new List<string>{Path.GetExtension(clean)});WinRT.Interop.InitializeWithWindow.Initialize(picker,App.WindowHandle);var file=await picker.PickSaveFileAsync();if(file is null)return false;
        verify();using var output=await file.OpenStreamForWriteAsync();verify();output.SetLength(0);source.Position=0;var buffer=new byte[32768];int count;
        while((count=await source.ReadAsync(buffer))>0){verify();await output.WriteAsync(buffer.AsMemory(0,count));}
        verify();await output.FlushAsync();verify();return true;
    }

    public static async Task<byte[]> Read(StorageFile file, long maximum = 50_000_000)
    {
        var properties = await file.GetBasicPropertiesAsync(); if (properties.Size > (ulong)maximum) throw new Exception("This file exceeds the supported size.");
        return await File.ReadAllBytesAsync(file.Path);
    }

    public static async Task<string> Image(StorageFile file, uint maximumDimension = 600, uint maximumBytes = 64000)
    {
        var raw = await Read(file, 15_000_000);
        if (raw.Length <= maximumBytes && (raw.Take(4).SequenceEqual(new byte[] { 137, 80, 78, 71 }) || raw.Take(2).SequenceEqual(new byte[] { 255, 216 })))
        {
            using var probe = await file.OpenAsync(FileAccessMode.Read); var decoder = await BitmapDecoder.CreateAsync(probe);
            if (decoder.PixelWidth <= maximumDimension && decoder.PixelHeight <= maximumDimension) return "data:image/" + (raw[0] == 137 ? "png" : "jpeg") + ";base64," + Convert.ToBase64String(raw);
        }
        using var stream = await file.OpenAsync(FileAccessMode.Read); var source = await BitmapDecoder.CreateAsync(stream);
        var factor = Math.Min(1d, maximumDimension / (double)Math.Max(source.PixelWidth, source.PixelHeight));
        var width = Math.Max(1u, (uint)(source.PixelWidth * factor)); var height = Math.Max(1u, (uint)(source.PixelHeight * factor));
        var transform = new BitmapTransform { ScaledWidth = width, ScaledHeight = height, InterpolationMode = BitmapInterpolationMode.Fant };
        using var bitmap = await source.GetSoftwareBitmapAsync(BitmapPixelFormat.Bgra8, BitmapAlphaMode.Premultiplied, transform, ExifOrientationMode.RespectExifOrientation, ColorManagementMode.ColorManageToSRgb);
        using(var png = new InMemoryRandomAccessStream()) {
            var encoder=await BitmapEncoder.CreateAsync(BitmapEncoder.PngEncoderId,png);encoder.SetSoftwareBitmap(bitmap);await encoder.FlushAsync();
            if(png.Size<=maximumBytes){png.Seek(0);using var reader=new DataReader(png.GetInputStreamAt(0));await reader.LoadAsync((uint)png.Size);var bytes=new byte[png.Size];reader.ReadBytes(bytes);return "data:image/png;base64,"+Convert.ToBase64String(bytes);}
        }
        // JPEG cannot retain alpha: composite on the same white background as paper.
        var pixelsBuffer=Windows.Security.Cryptography.CryptographicBuffer.CreateFromByteArray(new byte[bitmap.PixelWidth*bitmap.PixelHeight*4]);
        bitmap.CopyToBuffer(pixelsBuffer);Windows.Security.Cryptography.CryptographicBuffer.CopyToByteArray(pixelsBuffer,out var pixels);
        for(var i=0;i<pixels.Length;i+=4){var white=255-pixels[i+3];for(var c=0;c<3;c++)pixels[i+c]=(byte)Math.Min(255,pixels[i+c]+white);pixels[i+3]=255;}
        foreach (var quality in new[] { .9f, .75f, .6f, .4f })
        {
            using var output = new InMemoryRandomAccessStream();
            var properties = new BitmapPropertySet { ["ImageQuality"] = new BitmapTypedValue(quality, Windows.Foundation.PropertyType.Single) };
            var encoder = await BitmapEncoder.CreateAsync(BitmapEncoder.JpegEncoderId, output, properties); encoder.SetPixelData(BitmapPixelFormat.Bgra8,BitmapAlphaMode.Ignore,(uint)bitmap.PixelWidth,(uint)bitmap.PixelHeight,96,96,pixels); await encoder.FlushAsync();
            if (output.Size > maximumBytes) continue;
            output.Seek(0); using var reader = new DataReader(output.GetInputStreamAt(0)); await reader.LoadAsync((uint)output.Size); var data = new byte[output.Size]; reader.ReadBytes(data); return "data:image/jpeg;base64," + Convert.ToBase64String(data);
        }
        throw new Exception("Choose a smaller crop or a less detailed image.");
    }

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

    public static byte[] PrepareRestore(byte[] bytes, string password)
    {
        if (bytes.Length > 50_000_000) throw new Exception("The backup exceeds 50 MB.");
        if (bytes.Length > 0 && bytes[0] == '{')
        {
            var root = JsonNode.Parse(bytes);
            if (root.Text("format") == "apex-encrypted-backup")
            {
                if (root.Number("version") != 1) throw new Exception("This backup encryption version is not supported.");
                var salt = Convert.FromBase64String(root.Text("salt")); var iv = Convert.FromBase64String(root.Text("iv")); var encrypted = Convert.FromBase64String(root.Text("ciphertext"));
                var key = Rfc2898DeriveBytes.Pbkdf2(Encoding.UTF8.GetBytes(password), salt, 250000, HashAlgorithmName.SHA256, 32);
                try { var plain = new byte[encrypted.Length - 16]; using var aes = new AesGcm(key, 16); aes.Decrypt(iv, encrypted.AsSpan(0, encrypted.Length - 16), encrypted.AsSpan(encrypted.Length - 16), plain); bytes = plain; }
                catch (CryptographicException) { throw new Exception("The backup password is incorrect or the encrypted file is damaged."); }
                finally { CryptographicOperations.ZeroMemory(key); }
            }
        }
        if (!(bytes.Length > 2 && bytes[0] == 31 && bytes[1] == 139)) { using var output = new MemoryStream(); using (var compressor = new GZipStream(output, CompressionLevel.SmallestSize, true)) compressor.Write(bytes); bytes = output.ToArray(); }
        if (bytes.Length > 3_000_000) throw new Exception("The compressed backup exceeds this server's 3 MB import limit.");
        return bytes;
    }
}
