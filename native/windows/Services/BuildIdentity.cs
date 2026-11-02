using System.Reflection;
using System.Text.RegularExpressions;

namespace ApexBooks_Windows.Services;

public static class BuildIdentity
{
    public const string Version="1.5.0";
    public static string Revision=>Normalize(typeof(BuildIdentity).Assembly.GetCustomAttributes<AssemblyMetadataAttribute>().FirstOrDefault(item=>item.Key=="ApexBuildSha")?.Value);
    public static string Normalize(string? revision)=>revision is not null&&Regex.IsMatch(revision,"\\A(?:[0-9a-fA-F]{40}|[0-9a-fA-F]{64})\\z",RegexOptions.CultureInvariant)?revision.ToLowerInvariant():"unknown";
}
