using ApexBooks_Windows.Services;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using System.Net.Http;
using System.Text.Json.Nodes;
using static ApexBooks_Windows.Views.NativeUi;

namespace ApexBooks_Windows;

/// <summary>Item form section: where the item is kept and, with the Automobile module, what it fits.</summary>
internal sealed class ItemPlacementEditor
{
    private readonly JsonObject setup;
    private readonly List<(string Id, CheckBox Box)> locations = [];
    private readonly TextBox? oem, brand;
    private readonly ComboBox? grade;
    private readonly StackPanel fitRows = Stack(8);
    private readonly List<(ComboBox Make, ComboBox Model, TextBox From, TextBox To)> fits = [];
    public StackPanel View { get; } = Stack(10);

    public ItemPlacementEditor(JsonObject setup, JsonObject data)
    {
        this.setup = setup;
        var chosen = InventoryText.LocationIds(data);
        View.Children.Add(Text("Where it is kept", 15, true));
        var options = setup["locations"].Array().OfType<JsonObject>().Where(r => r["active"]?.GetValue<bool>() != false || chosen.Contains(r.Text("id"))).ToList();
        if (options.Count == 0) View.Children.Add(Text("No locations yet. The owner can add them in Settings → Stock & modules.", 12));
        else
        {
            var grid = new VariableSizedWrapGrid { Orientation = Orientation.Horizontal, ItemWidth = 150 };
            foreach (var row in options)
            {
                var id = row.Text("id");
                var box = new CheckBox { Content = row.Text("name") + (row["active"]?.GetValue<bool>() == false ? " (archived)" : ""), IsChecked = chosen.Contains(id), MinWidth = 0 };
                box.Checked += (_, _) => Limit(box);
                locations.Add((id, box)); grid.Children.Add(box);
            }
            View.Children.Add(new ScrollViewer { MaxHeight = 170, Content = grid });
            View.Children.Add(Text($"An item can be filed under up to {Limit()} locations.", 12));
        }
        if (setup["automobile_enabled"]?.GetValue<bool>() != true) return;
        View.Children.Add(Text("Vehicle details", 15, true));
        oem = Input("Part number (OEM)", data.Text("oem_number")); oem.MaxLength = 40;
        brand = Input("Brand", data.Text("part_brand")); brand.MaxLength = 40;
        grade = Select("Part grade", InventoryText.Grades, data.Text("part_grade"));
        View.Children.Add(Columns(oem, brand)); View.Children.Add(grade);
        View.Children.Add(Text("Fits these vehicles", 14, true));
        View.Children.Add(fitRows);
        foreach (var row in data["vehicle_fitment"].Array().OfType<JsonObject>()) AddFit(row.Text("make"), row.Text("model"), row["year_from"]?.ToString() ?? "", row["year_to"]?.ToString() ?? "");
        View.Children.Add(Button("Add vehicle", () => AddFit("", "", "", "")));
    }

    private int Limit() => setup["location_limit_per_item"] is JsonValue v && v.TryGetValue<int>(out var n) ? n : InventoryText.LocationLimit;

    private void Limit(CheckBox changed)
    {
        if (locations.Count(l => l.Box.IsChecked == true) > Limit()) changed.IsChecked = false;
    }

    private IEnumerable<(string Key, string Label)> Makes(string current)
    {
        var list = setup["vehicle_options"].Array().OfType<JsonObject>().Select(r => (r.Text("make"), r.Text("make"))).ToList();
        if (current.Length > 0 && list.All(x => x.Item1 != current)) list.Add((current, current));
        return new[] { ("", "Choose make") }.Concat(list);
    }

    private IEnumerable<(string Key, string Label)> Models(string make, string current)
    {
        var entry = setup["vehicle_options"].Array().OfType<JsonObject>().FirstOrDefault(r => string.Equals(r.Text("make"), make, StringComparison.OrdinalIgnoreCase));
        var list = entry?["models"].Array().OfType<JsonObject>().Select(r => (r.Text("name"), r.Text("name"))).ToList() ?? [];
        if (current.Length > 0 && list.All(x => x.Item1 != current)) list.Add((current, current));
        return new[] { ("", "All models") }.Concat(list);
    }

    private void AddFit(string make, string model, string from, string to)
    {
        var makeBox = Select("Make", Makes(make), make);
        var modelBox = Select("Model", Models(make, model), model);
        var fromBox = Input("From year", from); fromBox.MaxLength = 4; var toBox = Input("To year", to); toBox.MaxLength = 4;
        makeBox.SelectionChanged += (_, _) =>
        {
            modelBox.Items.Clear();
            foreach (var (key, label) in Models(Value(makeBox), "")) modelBox.Items.Add(new ComboBoxItem { Content = label, Tag = key });
            modelBox.SelectedIndex = 0;
        };
        var entry = (makeBox, modelBox, fromBox, toBox);
        var holder = Stack(6);
        var remove = Button("Remove vehicle", () => { fits.Remove(entry); fitRows.Children.Remove(holder); });
        holder.Children.Add(Columns(makeBox, modelBox)); holder.Children.Add(Columns(fromBox, toBox)); holder.Children.Add(remove);
        fits.Add(entry); fitRows.Children.Add(holder);
    }

    /// <summary>Writes the chosen locations and (Automobile on) vehicle details into the item data.</summary>
    public void Apply(JsonObject data)
    {
        var ids = new JsonArray();
        foreach (var (id, box) in locations) if (box.IsChecked == true) ids.Add(id);
        // Archived locations the item already has are kept even if they are not offered as choices.
        foreach (var kept in InventoryText.LocationIds(data)) if (locations.All(l => l.Id != kept)) ids.Add(kept);
        data["location_ids"] = ids;
        if (oem is null || brand is null || grade is null) return;
        data["oem_number"] = oem.Text.Trim(); data["part_brand"] = brand.Text.Trim(); data["part_grade"] = Value(grade);
        data["vehicle_fitment"] = InventoryText.CleanFitment(fits.Select(f => (Value(f.Make), Value(f.Model), f.From.Text, f.To.Text)));
    }
}

public sealed partial class MainPage
{
    internal JsonObject? InventorySetup;

    private async Task LoadInventorySetup(string cid)
    {
        InventorySetup = null;
        if (!Supports("inventory_setup")) return;
        try
        {
            var loaded = (await Api.Send(Api.CompanyPath(cid, "/inventory-setup"))).Object();
            if (cid == CompanyId) InventorySetup = loaded;
        }
        catch { /* Locations are optional; items stay usable without them. */ }
    }

    private ItemPlacementEditor? ItemPlacement(JsonObject data) =>
        Supports("inventory_setup") && InventorySetup is { } setup ? new ItemPlacementEditor(setup, data) : null;

    private async Task InventorySettings()
    {
        var cid = CompanyId;
        var setup = (await Api.Send(Api.CompanyPath(cid, "/inventory-setup"))).Object();
        var version = setup["version"]?.GetValue<int>() ?? 0;
        var locations = new List<(string? Id, TextBox Name, CheckBox Active)>();
        var added = setup["vehicle_added"].Array().OfType<JsonObject>().Select(r => (JsonObject)r.DeepClone()).ToList();
        var hiddenMakes = setup["vehicle_hidden_makes"].Array().Select(x => x?.ToString() ?? "").ToList();
        var hiddenModels = (JsonArray)setup["vehicle_hidden_models"].Array().DeepClone();
        var makes = setup["vehicle_options"].Array().OfType<JsonObject>().Select(r => (JsonObject)r.DeepClone()).ToList();
        var types = setup["vehicle_types"] as JsonObject ?? new JsonObject();
        var panel = Stack(); panel.MinWidth = 600;
        var message = Text("", 12);
        var list = Stack(8);

        void AddRow(string? id, string name, bool active)
        {
            var box = Input("Location", name); box.MaxLength = 40;
            var check = new CheckBox { Content = "In use (untick to archive)", IsChecked = active };
            locations.Add((id, box, check));
            var row = Stack(4); row.Children.Add(Columns(box, check));
            if (id is null) row.Children.Add(Button("Remove", () => { locations.RemoveAll(l => ReferenceEquals(l.Name, box)); list.Children.Remove(row); }));
            list.Children.Add(row);
        }
        void AddNames(IEnumerable<string> names)
        {
            var skipped = 0;
            foreach (var raw in names.Select(InventoryText.Tidy).Where(x => x.Length > 0))
            {
                if (raw.Length > 40) { message.Text = "A location name can be at most 40 characters."; return; }
                if (InventoryText.Duplicate(locations.Select(l => l.Name.Text), raw)) { skipped++; continue; }
                AddRow(null, raw, true);
            }
            message.Text = skipped > 0 ? $"{skipped} already listed and skipped." : "";
        }
        foreach (var row in setup["locations"].Array().OfType<JsonObject>()) AddRow(row.Text("id"), row.Text("name"), row["active"]?.GetValue<bool>() != false);

        panel.Children.Add(Text("Item locations", 18, true));
        panel.Children.Add(Text($"Name the places you keep stock, such as Rack 1 or Shelf B. Items can be filed under up to {InventoryText.LocationLimit} locations and found by location.", 12));
        var newName = Input("New location"); newName.MaxLength = 40;
        panel.Children.Add(newName); panel.Children.Add(Button("Add location", () => { AddNames([newName.Text]); newName.Text = ""; }));
        var prefix = Input("Series name", "Rack"); var from = Input("From", "1"); var to = Input("To", "5");
        panel.Children.Add(prefix); panel.Children.Add(Columns(from, to)); panel.Children.Add(Button("Add numbered series", () =>
        {
            if (prefix.Text.Trim().Length == 0) { message.Text = "Enter a name for the series."; return; }
            if (!int.TryParse(from.Text, out var a) || !int.TryParse(to.Text, out var b) || a > b) { message.Text = "Enter a valid number range."; return; }
            if (b - a >= 200) { message.Text = "A series can add up to 200 locations at a time."; return; }
            AddNames(Enumerable.Range(a, b - a + 1).Select(n => $"{prefix.Text.Trim()} {n}"));
        }));
        panel.Children.Add(message); panel.Children.Add(list);
        panel.Children.Add(Text("Saved locations that items use can be archived but not removed.", 12));

        var automobile = new CheckBox { Content = "Automobile shop — add vehicle details to items", IsChecked = setup["automobile_enabled"]?.GetValue<bool>() == true };
        panel.Children.Add(Text("Automobile module", 18, true));
        panel.Children.Add(Text("Turn this on for a parts counter, workshop, dealer, or tyre and battery shop. Items then get a part number, brand, grade and the vehicles they fit. Turning it off hides these details but keeps what you entered.", 12));
        panel.Children.Add(automobile);
        var vehicles = Stack(8);
        panel.Children.Add(vehicles);
        void DrawVehicles()
        {
            vehicles.Children.Clear();
            vehicles.Visibility = automobile.IsChecked == true ? Visibility.Visible : Visibility.Collapsed;
            vehicles.Children.Add(Text("Your makes and models", 16, true));
            vehicles.Children.Add(Text($"{makes.Count} makes are available, with common models for cars, two-wheelers, trucks and three-wheelers. Add anything missing; hiding and removing entries is done on the web app.", 12));
            var makeName = Input("Add a make"); makeName.MaxLength = 40;
            var type = Select("Type", types.Select(t => (t.Key, t.Value?.ToString() ?? t.Key)), "car");
            var model = Input("Model name"); model.MaxLength = 60;
            var target = Select("Add a model to", new[] { ("", "Choose make") }.Concat(makes.Select(m => (m.Text("make"), m.Text("make")))), "");
            vehicles.Children.Add(Columns(makeName, type)); vehicles.Children.Add(Button("Add make", () =>
            {
                var name = InventoryText.Tidy(makeName.Text);
                if (name.Length == 0) return;
                if (InventoryText.Duplicate(makes.Select(m => m.Text("make")), name)) { message.Text = $"{name} is already listed."; return; }
                added.Add(new JsonObject { ["make"] = name, ["type"] = Value(type), ["models"] = new JsonArray() });
                makes.Add(new JsonObject { ["make"] = name, ["type"] = Value(type), ["custom"] = true, ["models"] = new JsonArray() });
                message.Text = ""; DrawVehicles();
            }));
            vehicles.Children.Add(Columns(target, model)); vehicles.Children.Add(Button("Add model", () =>
            {
                var make = Value(target); var name = InventoryText.Tidy(model.Text);
                if (make.Length == 0 || name.Length == 0) return;
                var existing = makes.First(m => m.Text("make") == make);
                if (InventoryText.Duplicate(existing["models"].Array().Select(m => m.Text("name")), name)) { message.Text = $"{name} is already listed under {make}."; return; }
                var entry = added.FirstOrDefault(a => string.Equals(a.Text("make"), make, StringComparison.OrdinalIgnoreCase));
                if (entry is null) { entry = new JsonObject { ["make"] = make, ["type"] = existing.Text("type"), ["models"] = new JsonArray() }; added.Add(entry); }
                entry["models"]!.AsArray().Add(name);
                existing["models"]!.AsArray().Add(new JsonObject { ["name"] = name, ["custom"] = true });
                message.Text = ""; DrawVehicles();
            }));
        }
        automobile.Checked += (_, _) => DrawVehicles(); automobile.Unchecked += (_, _) => DrawVehicles();
        DrawVehicles();

        JsonObject Payload()
        {
            var rows = new JsonArray();
            foreach (var (id, name, active) in locations)
            {
                var row = new JsonObject { ["name"] = name.Text.Trim(), ["active"] = active.IsChecked == true };
                if (id is not null) row["id"] = id;
                rows.Add(row);
            }
            return new JsonObject
            {
                ["version"] = version, ["automobile_enabled"] = automobile.IsChecked == true, ["locations"] = rows,
                ["vehicle_added"] = new JsonArray(added.Select(a => (JsonNode)a.DeepClone()).ToArray()),
                ["vehicle_hidden_makes"] = new JsonArray(hiddenMakes.Select(m => (JsonNode)JsonValue.Create(m)!).ToArray()),
                ["vehicle_hidden_models"] = hiddenModels.DeepClone(),
            };
        }
        var baseline = Payload().ToJsonString();
        var saved = await Dialog("Stock & modules", panel, async () =>
        {
            var result = (await Api.Send(Api.CompanyPath(cid, "/inventory-setup"), HttpMethod.Put, Payload())).Object();
            if (cid == CompanyId) InventorySetup = result;
        }, "Save changes", hasChanges: () => Payload().ToJsonString() != baseline);
        if (saved && cid == CompanyId) await Refresh();
    }
}
