import test from 'node:test';
import assert from 'node:assert/strict';
import { capabilityFeatures, supportedMasterData, companyDisplayName, companyUpdatePayload } from '../src/capabilities.js';
test('missing or malformed feature metadata defaults to unsupported',()=>{
 assert.deepEqual(capabilityFeatures(null),[]);assert.deepEqual(capabilityFeatures({supported_features:['master_lifecycle']}),[]);
 assert.deepEqual(capabilityFeatures({capabilities_version:1,supported_features:['master_lifecycle',false]}),['master_lifecycle']);
});
test('unsupported optional metadata is omitted rather than silently sent to an older API',()=>{
 const input={address:'Billing',is_active:false,shipping_address:'Shipping',credit_limit:'0',payment_terms_days:0,low_stock_threshold:'2'};
 assert.deepEqual(supportedMasterData(input,[]),{address:'Billing'});
 assert.deepEqual(supportedMasterData(input,['party_credit_limits']),{address:'Billing',credit_limit:'0'});
 assert.equal(input.is_active,false);
});
test('book labels distinguish separate legal books without altering legal names or guessing periods',()=>{
 const companies=[{id:'one-12345678',name:'Same Legal'},{id:'two-87654321',name:'Same Legal'}];
 assert.equal(companyDisplayName(companies[0],companies),'Same Legal · Book 12345678');
 const labelled={...companies[0],book_label:'  Owner choice  '};
 assert.equal(companyDisplayName(labelled,[labelled,companies[1]]),'Same Legal · Owner choice');assert.equal(labelled.name,'Same Legal');
 const collision=[{id:'one-12345678',name:'Same Legal'},{id:'two-12345678',name:'Same Legal'}];assert.equal(companyDisplayName(collision[0],collision),'Same Legal · Book one-12345678');
});
test('company label writes require advertised support and retain legal fields',()=>{
 const form={name:'Same Legal',gstin:'',book_label:'  Separate books  '};
 assert.deepEqual(companyUpdatePayload(form,[]),{name:'Same Legal',gstin:''});
 assert.deepEqual(companyUpdatePayload(form,['company_book_labels']),{name:'Same Legal',gstin:'',book_label:'Separate books'});
});
