package com.apexbooks.accounting

import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class InventoryTextTest {
    private val setup = JSONObject().put("locations", JSONArray()
        .put(JSONObject().put("id", "l1").put("name", "Rack 1").put("active", true))
        .put(JSONObject().put("id", "l2").put("name", "Shelf B").put("active", false)))

    private fun fit(make: String, model: String, from: Any?, to: Any?) =
        JSONObject().put("make", make).put("model", model).put("year_from", from ?: JSONObject.NULL).put("year_to", to ?: JSONObject.NULL)

    private fun item() = JSONObject().put("name", "Brake pad").put("data", JSONObject()
        .put("barcode", "8901").put("location_ids", JSONArray().put("l2").put("gone").put("l1"))
        .put("oem_number", "55810").put("part_brand", "Bosch").put("part_grade", "aftermarket")
        .put("vehicle_fitment", JSONArray().put(fit("Maruti Suzuki", "Swift", 2011, 2017)).put(fit("Hyundai", "", null, null))))

    @Test fun locationsResolveToKnownNamesOnly() {
        assertEquals(listOf("Shelf B", "Rack 1"), InventoryText.locationNames(setup, listOf("l2", "gone", "l1")))
        assertTrue(InventoryText.locationNames(null, listOf("l1")).isEmpty())
    }

    @Test fun yearRangesReadNaturally() {
        assertEquals("2011–2017", InventoryText.years(2011, 2017))
        assertEquals("2015", InventoryText.years(2015, 2015))
        assertEquals("2018 onwards", InventoryText.years(2018, null))
        assertEquals("up to 2012", InventoryText.years(null, 2012))
        assertEquals("Tata Nexon", InventoryText.fitmentLabel(fit(" Tata ", "Nexon", null, null)))
    }

    @Test fun summaryShowsPlacePartAndFitment() {
        val lines = InventoryText.summary(item(), setup)
        assertEquals("📍 Shelf B · Rack 1", lines[0])
        assertEquals("Part 55810 · Bosch", lines[1])
        assertEquals("Fits Maruti Suzuki Swift 2011–2017; Hyundai", lines[2])
        assertTrue(InventoryText.summary(JSONObject().put("data", JSONObject()), setup).isEmpty())
    }

    @Test fun searchFindsByLocationPartBrandGradeAndVehicle() {
        val text = InventoryText.searchText(item(), setup).lowercase()
        for (word in listOf("rack 1", "55810", "bosch", "aftermarket", "swift", "2011", "brake pad", "8901")) assertTrue(word, text.contains(word))
    }

    @Test fun fitmentRowsAreCleanedBeforeSending() {
        val raw = JSONArray().put(fit("", "", null, null)).put(fit(" Tata ", " Nexon ", 2018, null)).toString()
        val clean = InventoryText.cleanFitment(raw)
        assertEquals(1, clean.length())
        assertEquals("Tata", clean.getJSONObject(0).getString("make"))
        assertEquals("Nexon", clean.getJSONObject(0).getString("model"))
        assertEquals(2018, clean.getJSONObject(0).getInt("year_from"))
        assertTrue(clean.getJSONObject(0).isNull("year_to"))
        assertTrue(InventoryText.fitmentRows("not json").isEmpty())
        assertEquals(2024, InventoryText.yearOrNull("20x24"))
        assertEquals(JSONObject.NULL, InventoryText.yearOrNull(""))
    }

    @Test fun locationIdsParseFromTheEditorField() {
        assertEquals(listOf("a", "b"), InventoryText.ids(" a, ,b "))
        assertTrue(InventoryText.ids("").isEmpty())
    }
}
