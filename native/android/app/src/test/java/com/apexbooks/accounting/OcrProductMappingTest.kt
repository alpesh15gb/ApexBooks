package com.apexbooks.accounting

import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class OcrProductMappingTest {
    private fun catalogue()=JSONObject().put("id","stock-item").put("name","Catalogue adapter")
        .put("data",JSONObject().put("purchase_rate","50").put("sale_rate","100").put("gst_rate","5")
            .put("hsn","8517").put("unit","NOS").put("tax_treatment","taxable"))

    @Test fun linkingScannedBillPreservesSupplierFinancialValues(){
        val line=LineState(JSONObject().put("description","Supplier description").put("quantity","2")
            .put("rate","500").put("gst_rate","18").put("discount_percent","10")
            .put("price_includes_tax",true).put("tax_treatment","taxable"),regular=true,importedFromOcr=true)
        line.linkProduct(catalogue(),purchase=true,regular=true)
        assertEquals("stock-item",line.get("item_id"));assertEquals("NOS",line.get("unit"));assertEquals("8517",line.get("hsn"))
        assertEquals("2",line.get("quantity"));assertEquals("500",line.get("rate"));assertEquals("18",line.get("gst_rate"))
        assertEquals("10",line.get("discount_percent"));assertEquals("true",line.get("price_includes_tax"))
        assertFalse(line.json().has("importedFromOcr"))
    }

    @Test fun newManualLineUsesCatalogueDefaults(){
        val line=LineState(regular=true)
        line.linkProduct(catalogue(),purchase=true,regular=true)
        assertEquals("50",line.get("rate"));assertEquals("5",line.get("gst_rate"));assertEquals("1",line.get("quantity"))
    }
}
