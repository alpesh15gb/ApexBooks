using System.Text.Json.Nodes;

namespace ApexBooks_Windows.Services;

/// <summary>Item locations and vehicle fitment: text shown on item rows, search text, and clean payload values.</summary>
public static class InventoryText
{
    public const int LocationLimit = 5;
    public static readonly (string Key, string Label)[] Grades = [("", "Not specified"), ("oem", "OEM / genuine"), ("aftermarket", "Aftermarket"), ("used", "Used"), ("refurbished", "Refurbished")];

    public static List<string> LocationIds(JsonNode? data) => data?["location_ids"] is JsonArray list
        ? list.Select(x => x?.ToString() ?? "").Where(x => x.Length > 0).ToList() : [];

    public static List<string> LocationNames(JsonNode? setup, IEnumerable<string> ids)
    {
        if (setup?["locations"] is not JsonArray rows) return [];
        var byId = rows.OfType<JsonObject>().ToDictionary(r => r.Text("id"), r => r.Text("name"), StringComparer.Ordinal);
        return ids.Where(byId.ContainsKey).Select(id => byId[id]).ToList();
    }

    public static string Years(int? from, int? to) => (from, to) switch
    {
        (not null, not null) => from == to ? $"{from}" : $"{from}–{to}",
        (not null, null) => $"{from} onwards",
        (null, not null) => $"up to {to}",
        _ => "",
    };

    static int? Year(JsonNode? node) => node is JsonValue value && value.TryGetValue<int>(out var number) ? number : null;

    public static string FitmentLabel(JsonNode? row) =>
        string.Join(' ', new[] { row.Text("make").Trim(), row.Text("model").Trim(), Years(Year(row?["year_from"]), Year(row?["year_to"])) }.Where(x => x.Length > 0));

    public static List<string> Fits(JsonNode? data) => data?["vehicle_fitment"] is JsonArray list
        ? list.Select(FitmentLabel).Where(x => x.Length > 0).ToList() : [];

    /// <summary>Short lines for an item row: where it is kept, its part info, and the vehicles it fits.</summary>
    public static List<string> Summary(JsonObject item, JsonNode? setup)
    {
        var data = item["data"];
        var lines = new List<string>();
        var places = LocationNames(setup, LocationIds(data));
        if (places.Count > 0) lines.Add("📍 " + string.Join(" · ", places));
        var part = new[] { data.Text("oem_number"), data.Text("part_brand") }.Where(x => x.Length > 0).ToList();
        if (part.Count > 0) lines.Add("Part " + string.Join(" · ", part));
        var fits = Fits(data);
        if (fits.Count > 0) lines.Add("Fits " + string.Join("; ", fits.Take(3)) + (fits.Count > 3 ? $" +{fits.Count - 3} more" : ""));
        return lines;
    }

    public static string SearchText(JsonObject item, JsonNode? setup)
    {
        var data = item["data"];
        var grade = Grades.FirstOrDefault(g => g.Key == data.Text("part_grade")).Label ?? "";
        return string.Join(' ', new[] { item.Text("name"), data.Text("barcode"), data.Text("hsn"), data.Text("oem_number"), data.Text("part_brand"), grade }
            .Concat(LocationNames(setup, LocationIds(data))).Concat(Fits(data)));
    }

    /// <summary>Rows without a make are dropped; years must be four digits or blank.</summary>
    public static JsonArray CleanFitment(IEnumerable<(string Make, string Model, string From, string To)> rows)
    {
        var result = new JsonArray();
        foreach (var (make, model, from, to) in rows)
        {
            if (make.Trim().Length == 0) continue;
            result.Add(new JsonObject { ["make"] = make.Trim(), ["model"] = model.Trim(), ["year_from"] = YearValue(from), ["year_to"] = YearValue(to) });
        }
        return result;
    }

    public static JsonNode? YearValue(string text)
    {
        var digits = new string(text.Where(char.IsAsciiDigit).Take(4).ToArray());
        return digits.Length == 4 && int.TryParse(digits, out var year) ? JsonValue.Create(year) : null;
    }

    public static bool Duplicate(IEnumerable<string> existing, string name) => existing.Any(x => string.Equals(Tidy(x), Tidy(name), StringComparison.OrdinalIgnoreCase));
    public static string Tidy(string text) => string.Join(' ', text.Split((char[]?)null, StringSplitOptions.RemoveEmptyEntries));
}
