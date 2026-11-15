using System.Text.Json.Nodes;
using ApexBooks_Windows.Services;

static class InventoryTextRegression
{
    static void Check(bool ok, string message) { if (!ok) throw new Exception(message); }

    public static void Run()
    {
        var setup = new JsonObject { ["locations"] = new JsonArray {
            new JsonObject { ["id"] = "l1", ["name"] = "Rack 1", ["active"] = true },
            new JsonObject { ["id"] = "l2", ["name"] = "Shelf B", ["active"] = false } } };
        var item = new JsonObject { ["name"] = "Brake pad", ["data"] = new JsonObject {
            ["barcode"] = "8901", ["location_ids"] = new JsonArray { "l2", "gone", "l1" }, ["oem_number"] = "55810", ["part_brand"] = "Bosch", ["part_grade"] = "aftermarket",
            ["vehicle_fitment"] = new JsonArray {
                new JsonObject { ["make"] = "Maruti Suzuki", ["model"] = "Swift", ["year_from"] = 2011, ["year_to"] = 2017 },
                new JsonObject { ["make"] = "Hyundai", ["model"] = "", ["year_from"] = null, ["year_to"] = null } } } };

        Check(string.Join("|", InventoryText.LocationNames(setup, ["l2", "gone", "l1"])) == "Shelf B|Rack 1", "Unknown locations must be skipped");
        Check(InventoryText.LocationNames(null, ["l1"]).Count == 0, "No setup means no names");
        var lines = InventoryText.Summary(item, setup);
        Check(lines[0] == "📍 Shelf B · Rack 1" && lines[1] == "Part 55810 · Bosch" && lines[2] == "Fits Maruti Suzuki Swift 2011–2017; Hyundai", "Item summary lines: " + string.Join("/", lines));
        Check(InventoryText.Summary(new JsonObject { ["data"] = new JsonObject() }, setup).Count == 0, "Plain items have no extra lines");
        var text = InventoryText.SearchText(item, setup).ToLowerInvariant();
        foreach (var word in new[] { "rack 1", "55810", "bosch", "aftermarket", "swift", "2011", "brake pad", "8901" }) Check(text.Contains(word), "Search misses " + word);
        Check(InventoryText.Years(2015, 2015) == "2015" && InventoryText.Years(2018, null) == "2018 onwards" && InventoryText.Years(null, 2012) == "up to 2012", "Year ranges");

        var clean = InventoryText.CleanFitment([("", "", "", ""), (" Tata ", " Nexon ", "2018", ""), ("Audi", "", "20", "x2024")]);
        Check(clean.Count == 2, "Rows without a make are dropped");
        Check(clean[0]!["make"]!.ToString() == "Tata" && clean[0]!["model"]!.ToString() == "Nexon" && (int)clean[0]!["year_from"]! == 2018 && clean[0]!["year_to"] is null, "Fitment row cleaned");
        Check(clean[1]!["year_from"] is null && (int)clean[1]!["year_to"]! == 2024, "Partial years are not guessed");
        Check(InventoryText.Duplicate(["Rack 1"], "  rack   1 ") && !InventoryText.Duplicate(["Rack 1"], "Rack 2"), "Duplicate names ignore case and spacing");

        var capabilities = ClientCapabilities.Parse(new JsonObject { ["capabilities_version"] = 1, ["supported_features"] = new JsonArray { "inventory_setup" } });
        Check(capabilities.Supports("inventory_setup"), "inventory_setup must be a known capability");
        var original = new JsonObject { ["location_ids"] = new JsonArray { "l1" } };
        var legacy = ClientCapabilities.Parse(new JsonObject { ["capabilities_version"] = 1, ["supported_features"] = new JsonArray() });
        Check(!legacy.MasterData(original).ContainsKey("location_ids"), "Older servers must not be sent location fields");
        Console.WriteLine("PASS item locations, fitment text, search and capability gating");
    }
}
