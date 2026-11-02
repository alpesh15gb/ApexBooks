import test from 'node:test';
import assert from 'node:assert/strict';
import { reorderDraft } from '../src/reorderDraft.js';
test('reorder seeds retain exact catalogue tax treatment without conversion lineage', () => {
 for (const treatment of ['taxable','exempt','nil_rated','non_gst']) {
  const seed = reorderDraft([{item_id:'i1',name:'Synthetic',quantity:'3',purchase_rate:'80'}],[{id:'i1',kind:'item',data:{gst_rate:'18',tax_treatment:treatment,hsn:'1234'}}]);
  assert.equal(seed.data.lines[0].tax_treatment,treatment); assert.equal(seed.data.lines[0].gst_rate,'18'); assert.equal(seed.data.source_document_id,undefined);
 }
});
test('missing or newly inactive masters cannot produce incomplete reorder tax defaults', () => {
 assert.throws(() => reorderDraft([{item_id:'i1'}],[]),/catalogue/);
 assert.throws(() => reorderDraft([{item_id:'i1'}],[{id:'i1',kind:'item',data:{is_active:false}}]),/inactive/);
});
