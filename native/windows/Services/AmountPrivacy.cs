namespace ApexBooks_Windows.Services;

/// <summary>
/// Dashboard amounts can be hidden on this PC. Hiding needs no password; showing them again needs the
/// account password, which the server checks. The choice is a marker file under the user's profile.
/// </summary>
public static class AmountPrivacy
{
    public const string Mask = "₹ ••••••";
    /// <summary>Tests point this at a scratch folder; production uses the user's local application data.</summary>
    public static string? DirectoryOverride { get; set; }
    private static string Marker => Path.Combine(
        DirectoryOverride ?? Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "ApexBooks", "Preferences"),
        "dashboard-amounts-hidden");

    public static bool Hidden
    {
        get { try { return File.Exists(Marker); } catch { return false; } }
    }

    public static void Set(bool hidden)
    {
        try
        {
            if (hidden)
            {
                Directory.CreateDirectory(Path.GetDirectoryName(Marker)!);
                File.WriteAllText(Marker, "1");
            }
            else if (File.Exists(Marker)) File.Delete(Marker);
        }
        catch { /* A locked profile keeps the previous choice; amounts are never hidden by accident. */ }
    }

    public static string Text(bool hidden, string formatted) => hidden ? Mask : formatted;

    /// <summary>A server without the password check cannot reveal by password, so it must not strand the user behind masked figures.</summary>
    public static bool RevealUnsupported(Exception error) => error is ApiFailure { Status: 404 or 405 };
}
