package com.apexbooks.accounting

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.apexbooks.accounting.data.a
import com.apexbooks.accounting.data.o
import com.apexbooks.accounting.data.objects
import com.apexbooks.accounting.data.s
import org.json.JSONArray
import org.json.JSONObject

/** Pure helpers for item locations and vehicle fitment, kept free of Compose so they can be unit tested. */
object InventoryText {
    const val LOCATION_LIMIT = 5
    val grades = listOf("" to "Not specified", "oem" to "OEM / genuine", "aftermarket" to "Aftermarket", "used" to "Used", "refurbished" to "Refurbished")

    fun ids(raw: String): List<String> = raw.split(',').map { it.trim() }.filter { it.isNotEmpty() }

    fun locationNames(setup: JSONObject?, ids: List<String>): List<String> {
        val byId = setup?.a("locations")?.objects()?.associate { it.s("id") to it.s("name") } ?: return emptyList()
        return ids.mapNotNull { byId[it] }
    }

    fun years(from: Int?, to: Int?): String = when {
        from != null && to != null -> if (from == to) "$from" else "$from–$to"
        from != null -> "$from onwards"
        to != null -> "up to $to"
        else -> ""
    }

    fun fitmentLabel(row: JSONObject): String {
        val from = if (row.isNull("year_from")) null else row.optInt("year_from")
        val to = if (row.isNull("year_to")) null else row.optInt("year_to")
        return listOf(row.s("make").trim(), row.s("model").trim(), years(from, to)).filter { it.isNotBlank() }.joinToString(" ")
    }

    fun locationIds(data: JSONObject): List<String> = data.a("location_ids").let { array -> (0 until array.length()).map { array.optString(it) } }

    /** Short lines shown under an item: where it is, its part info, and what it fits. */
    fun summary(item: JSONObject, setup: JSONObject?): List<String> {
        val data = item.o("data")
        val lines = mutableListOf<String>()
        val places = locationNames(setup, locationIds(data))
        if (places.isNotEmpty()) lines += "📍 " + places.joinToString(" · ")
        val part = listOf(data.s("oem_number"), data.s("part_brand")).filter { it.isNotBlank() }
        if (part.isNotEmpty()) lines += "Part " + part.joinToString(" · ")
        val fits = data.a("vehicle_fitment").objects().map(::fitmentLabel).filter { it.isNotBlank() }
        if (fits.isNotEmpty()) lines += "Fits " + fits.take(3).joinToString("; ") + if (fits.size > 3) " +${fits.size - 3} more" else ""
        return lines
    }

    fun searchText(item: JSONObject, setup: JSONObject?): String {
        val data = item.o("data")
        val grade = grades.firstOrNull { it.first == data.s("part_grade") }?.second.orEmpty()
        return (listOf(item.s("name"), data.s("barcode"), data.s("hsn"), data.s("oem_number"), data.s("part_brand"), grade) +
            locationNames(setup, locationIds(data)) + data.a("vehicle_fitment").objects().map(::fitmentLabel)).joinToString(" ")
    }

    fun fitmentRows(raw: String): MutableList<JSONObject> = try { JSONArray(raw.ifBlank { "[]" }).objects().toMutableList() } catch (e: Exception) { mutableListOf() }

    fun yearOrNull(text: String): Any = text.filter { it.isDigit() }.take(4).toIntOrNull() ?: JSONObject.NULL

    /** Rows with neither make nor model are dropped; the rest are sent as the API expects. */
    fun cleanFitment(raw: String): JSONArray = JSONArray(fitmentRows(raw).filter { it.s("make").isNotBlank() }.map {
        JSONObject().put("make", it.s("make").trim()).put("model", it.s("model").trim())
            .put("year_from", if (it.isNull("year_from")) JSONObject.NULL else it.opt("year_from")).put("year_to", if (it.isNull("year_to")) JSONObject.NULL else it.opt("year_to"))
    })

    fun makeOptions(setup: JSONObject?): List<JSONObject> = setup?.a("vehicle_options")?.objects().orEmpty()
}

/** Item form section: where the item is kept and, with the Automobile module on, what it fits. */
@OptIn(ExperimentalLayoutApi::class)
@Composable
fun ItemPlacementFields(editor: EntryEditor) {
    val vm = editor.vm
    val setup = vm.inventorySetup
    if (!vm.supports("inventory_setup") || setup == null) return
    val chosen = InventoryText.ids(editor.get("location_ids"))
    val limit = setup.optInt("location_limit_per_item", InventoryText.LOCATION_LIMIT)
    val options = setup.a("locations").objects().filter { it.optBoolean("active", true) || it.s("id") in chosen }
    Section("Where it is kept") {
        if (options.isEmpty()) Text("No locations yet. The owner can add them in Settings → Stock & modules.", style = MaterialTheme.typography.bodySmall)
        else FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            options.forEach { row ->
                val id = row.s("id"); val on = id in chosen
                FilterChip(selected = on, enabled = editor.canEdit && (on || chosen.size < limit), onClick = { editor.set("location_ids", (if (on) chosen - id else chosen + id).joinToString(",")) },
                    label = { Text(row.s("name") + if (row.optBoolean("active", true)) "" else " (archived)") })
            }
        }
        if (chosen.size >= limit) Text("An item can be filed under up to $limit locations.", style = MaterialTheme.typography.bodySmall)
    }
    if (!setup.optBoolean("automobile_enabled")) return
    val catalogue = InventoryText.makeOptions(setup)
    val rows = InventoryText.fitmentRows(editor.get("vehicle_fitment"))
    fun save(next: List<JSONObject>) = editor.set("vehicle_fitment", JSONArray(next).toString())
    Section("Vehicle details") {
        Field("Part number (OEM)", editor.get("oem_number"), { editor.set("oem_number", it) }, maximum = 40)
        Field("Brand", editor.get("part_brand"), { editor.set("part_brand", it) }, maximum = 40)
        Choice("Part grade", editor.get("part_grade"), InventoryText.grades, { editor.set("part_grade", it) })
        Text("Fits these vehicles", style = MaterialTheme.typography.titleSmall)
        if (rows.isEmpty()) Text("Add each make and model this part fits. Choose \"All models\" if it fits every model of that make.", style = MaterialTheme.typography.bodySmall)
        rows.forEachIndexed { index, row ->
            val make = row.s("make")
            val makeChoices = (listOf("" to "Choose make") + catalogue.map { it.s("make") to it.s("make") }).let { list -> if (make.isNotBlank() && list.none { it.first == make }) list + (make to make) else list }
            val models = catalogue.firstOrNull { it.s("make").equals(make, true) }?.a("models")?.objects()?.map { it.s("name") }.orEmpty()
            val modelChoices = (listOf("" to "All models") + models.map { it to it }).let { list -> if (row.s("model").isNotBlank() && list.none { it.first == row.s("model") }) list + (row.s("model") to row.s("model")) else list }
            Section("Vehicle ${index + 1}") {
                Choice("Make", make, makeChoices, { value -> save(rows.mapIndexed { at, r -> if (at == index) JSONObject(r.toString()).put("make", value).put("model", "") else r }) })
                Choice("Model", row.s("model"), modelChoices, { value -> save(rows.mapIndexed { at, r -> if (at == index) JSONObject(r.toString()).put("model", value) else r }) })
                Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    Field("From year", if (row.isNull("year_from")) "" else row.optInt("year_from").toString(), { value -> save(rows.mapIndexed { at, r -> if (at == index) JSONObject(r.toString()).put("year_from", InventoryText.yearOrNull(value)) else r }) }, Modifier.weight(1f), number = true, maximum = 4)
                    Field("To year", if (row.isNull("year_to")) "" else row.optInt("year_to").toString(), { value -> save(rows.mapIndexed { at, r -> if (at == index) JSONObject(r.toString()).put("year_to", InventoryText.yearOrNull(value)) else r }) }, Modifier.weight(1f), number = true, maximum = 4)
                }
                TextButton(enabled = editor.canEdit, onClick = { save(rows.filterIndexed { at, _ -> at != index }) }) { Text("Remove vehicle") }
            }
        }
        OutlinedButton(enabled = editor.canEdit && rows.size < 60, onClick = { save(rows + JSONObject().put("make", "").put("model", "").put("year_from", JSONObject.NULL).put("year_to", JSONObject.NULL)) }) { Text("Add vehicle") }
    }
}

private class LocationDraft(val id: String?, name: String, active: Boolean) {
    var name by mutableStateOf(name)
    var active by mutableStateOf(active)
}

/** Settings → Stock & modules: item locations, the Automobile switch and the owner's own makes and models. */
@OptIn(ExperimentalLayoutApi::class)
@Composable
fun InventorySetupTool(vm: AppModel) {
    val cid = vm.companyId
    var loaded by remember { mutableStateOf(false) }
    var version by remember { mutableStateOf(0) }
    var automobile by remember { mutableStateOf(false) }
    val locations = remember { mutableStateListOf<LocationDraft>() }
    val added = remember { mutableStateListOf<JSONObject>() }
    var hiddenMakes by remember { mutableStateOf(emptyList<String>()) }
    var hiddenModels by remember { mutableStateOf(JSONArray()) }
    var vehicleOptions by remember { mutableStateOf(emptyList<JSONObject>()) }
    var vehicleTypes by remember { mutableStateOf(JSONObject()) }
    var initial by remember { mutableStateOf("") }
    var newLocation by remember { mutableStateOf("") }
    var prefix by remember { mutableStateOf("Rack") }
    var from by remember { mutableStateOf("1") }
    var to by remember { mutableStateOf("5") }
    var newMake by remember { mutableStateOf("") }
    var newMakeType by remember { mutableStateOf("car") }
    var modelMake by remember { mutableStateOf("") }
    var newModel by remember { mutableStateOf("") }
    var problem by remember { mutableStateOf("") }

    fun apply(setup: JSONObject) {
        version = setup.optInt("version"); automobile = setup.optBoolean("automobile_enabled")
        locations.clear(); setup.a("locations").objects().forEach { locations.add(LocationDraft(it.s("id"), it.s("name"), it.optBoolean("active", true))) }
        added.clear(); setup.a("vehicle_added").objects().forEach { added.add(JSONObject(it.toString())) }
        hiddenMakes = setup.a("vehicle_hidden_makes").let { array -> (0 until array.length()).map { array.optString(it) } }
        hiddenModels = setup.a("vehicle_hidden_models"); vehicleOptions = setup.a("vehicle_options").objects(); vehicleTypes = setup.o("vehicle_types")
    }
    fun payload(): JSONObject = JSONObject().put("version", version).put("automobile_enabled", automobile)
        .put("locations", JSONArray(locations.map { row -> JSONObject().apply { if (row.id != null) put("id", row.id) }.put("name", row.name.trim()).put("active", row.active) }))
        .put("vehicle_added", JSONArray(added.toList())).put("vehicle_hidden_makes", JSONArray(hiddenMakes)).put("vehicle_hidden_models", hiddenModels)
    fun signature() = payload().toString()
    LaunchedEffect(cid) {
        try { val setup = vm.api.request(vm.api.company(cid, "/inventory-setup")) as JSONObject; apply(setup); initial = signature(); loaded = true } catch (e: Exception) { vm.failure(e) }
    }
    fun addNames(names: List<String>) {
        val clean = names.map { it.trim().replace(Regex("\\s+"), " ") }.filter { it.isNotEmpty() }
        if (clean.any { it.length > 40 }) { problem = "A location name can be at most 40 characters."; return }
        var skipped = 0
        clean.forEach { name -> if (locations.any { it.name.trim().equals(name, true) }) skipped++ else locations.add(LocationDraft(null, name, true)) }
        problem = if (skipped > 0) "$skipped already listed and skipped." else ""
    }
    val owner = vm.isOwner
    ActionDialog("Stock & modules", vm, enabled = loaded && owner, hasChanges = { loaded && signature() != initial }, confirm = "Save changes", onDismiss = { vm.tool = "" }, onSave = {
        val saved = vm.api.request(vm.api.company(cid, "/inventory-setup"), "PUT", payload()) as JSONObject
        vm.publishInventorySetup(saved); vm.tool = ""; vm.notice = "Stock and module settings saved."
    }) {
        if (!loaded) { CircularProgressIndicator(); return@ActionDialog }
        if (!owner) Text("Only the owner can change item locations and business modules.", style = MaterialTheme.typography.bodySmall)
        Section("Item locations") {
            Text("Name the places you keep stock, such as Rack 1 or Shelf B. Items can be filed under up to ${InventoryText.LOCATION_LIMIT} locations and found by location.", style = MaterialTheme.typography.bodySmall)
            Field("New location", newLocation, { newLocation = it }, maximum = 40)
            OutlinedButton(enabled = owner && newLocation.isNotBlank(), onClick = { addNames(listOf(newLocation)); newLocation = "" }) { Text("Add location") }
            Field("Series name", prefix, { prefix = it }, maximum = 30)
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                Field("From", from, { from = it }, Modifier.weight(1f), number = true, maximum = 4)
                Field("To", to, { to = it }, Modifier.weight(1f), number = true, maximum = 4)
            }
            OutlinedButton(enabled = owner, onClick = {
                val a = from.toIntOrNull(); val b = to.toIntOrNull()
                when {
                    prefix.isBlank() -> problem = "Enter a name for the series."
                    a == null || b == null || a > b -> problem = "Enter a valid number range."
                    b - a >= 200 -> problem = "A series can add up to 200 locations at a time."
                    else -> addNames((a..b).map { "${prefix.trim()} $it" })
                }
            }) { Text("Add numbered series") }
            Message(problem, true)
            locations.forEachIndexed { index, row ->
                Section {
                    Field("Location ${index + 1}", row.name, { row.name = it }, maximum = 40)
                    Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        OutlinedButton(enabled = owner, onClick = { row.active = !row.active }) { Text(if (row.active) "Archive" else "Restore") }
                        if (row.id == null) TextButton(enabled = owner, onClick = { locations.remove(row) }) { Text("Remove") }
                    }
                    if (!row.active) Text("Archived: stays on items that use it, but cannot be chosen for new items.", style = MaterialTheme.typography.bodySmall)
                }
            }
            if (locations.any { it.id != null }) Text("Saved locations that items use can be archived but not removed.", style = MaterialTheme.typography.bodySmall)
        }
        Section("Automobile module") {
            Text("Turn this on for a parts counter, workshop, dealer, or tyre and battery shop. Items then get a part number, brand, grade and the vehicles they fit. Turning it off hides these details but keeps what you entered.", style = MaterialTheme.typography.bodySmall)
            Toggle("Automobile shop — add vehicle details to items", automobile, { automobile = it }, enabled = owner)
        }
        if (automobile) Section("Your makes and models") {
            Text("${vehicleOptions.size} makes are available, with common models for cars, two-wheelers, trucks and three-wheelers. Add anything missing; the full make and model editor is on the web app.", style = MaterialTheme.typography.bodySmall)
            val types = vehicleTypes.keys().asSequence().map { it to vehicleTypes.optString(it) }.toList().ifEmpty { listOf("car" to "Cars and SUVs") }
            Field("Add a make", newMake, { newMake = it }, maximum = 40)
            Choice("Type", newMakeType, types, { newMakeType = it })
            OutlinedButton(enabled = owner && newMake.isNotBlank(), onClick = {
                val name = newMake.trim().replace(Regex("\\s+"), " ")
                if (vehicleOptions.any { it.s("make").equals(name, true) } || added.any { it.s("make").equals(name, true) }) problem = "$name is already listed."
                else { added.add(JSONObject().put("make", name).put("type", newMakeType).put("models", JSONArray())); vehicleOptions = vehicleOptions + JSONObject().put("make", name).put("type", newMakeType).put("custom", true).put("models", JSONArray()); newMake = ""; problem = "" }
            }) { Text("Add make") }
            Choice("Add a model to", modelMake, listOf("" to "Choose make") + vehicleOptions.map { it.s("make") to it.s("make") }, { modelMake = it })
            Field("Model name", newModel, { newModel = it }, maximum = 60)
            OutlinedButton(enabled = owner && modelMake.isNotBlank() && newModel.isNotBlank(), onClick = {
                val name = newModel.trim().replace(Regex("\\s+"), " ")
                val existing = vehicleOptions.firstOrNull { it.s("make") == modelMake }
                if (existing?.a("models")?.objects()?.any { it.s("name").equals(name, true) } == true) problem = "$name is already listed under $modelMake."
                else {
                    val entry = added.firstOrNull { it.s("make").equals(modelMake, true) } ?: JSONObject().put("make", modelMake).put("type", existing?.s("type") ?: "car").put("models", JSONArray()).also { added.add(it) }
                    entry.a("models").put(name)
                    vehicleOptions = vehicleOptions.map { option -> if (option.s("make") == modelMake) JSONObject(option.toString()).also { it.a("models").put(JSONObject().put("name", name).put("custom", true)) } else option }
                    newModel = ""; problem = ""
                }
            }) { Text("Add model") }
        }
    }
}
