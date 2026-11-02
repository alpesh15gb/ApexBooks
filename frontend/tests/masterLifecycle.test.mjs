import test from 'node:test';
import assert from 'node:assert/strict';
import { availableMasters, isActiveMaster, partyShippingAddress, shippingForPartySelection } from '../src/masterLifecycle.js';
test('legacy active masters remain selectable; archived identities are retained only for historical editing', () => {
 const rows=[{id:'active',kind:'party'},{id:'archived',kind:'party',data:{is_active:false}},{id:'item',kind:'item',data:{is_active:false}}];
 assert.equal(isActiveMaster(rows[0]),true);
 assert.deepEqual(availableMasters(rows,'party').map(row=>row.id),['active']);
 assert.deepEqual(availableMasters(rows,'party',['archived']).map(row=>row.id),['active','archived']);
 assert.deepEqual(availableMasters(rows,'item',['archived']),[]);
});
test('party shipping uses separate saved address and falls back to billing when blank', () => {
 assert.equal(partyShippingAddress({data:{address:'Billing',shipping_address:'Warehouse'}}),'Warehouse');
 assert.equal(partyShippingAddress({data:{address:'Billing',shipping_address:''}}),'Billing');
});

test('switching party updates derived addresses but preserves deliberate delivery overrides', () => {
 assert.equal(shippingForPartySelection('Warehouse A','Warehouse A','Warehouse B'),'Warehouse B');
 assert.equal(shippingForPartySelection('Manual job site','Warehouse A','Warehouse B'),'Manual job site');
 assert.equal(shippingForPartySelection('Manual job site','Warehouse A',''),'Manual job site');
 assert.equal(shippingForPartySelection('','','Warehouse B'),'Warehouse B');
 assert.equal(shippingForPartySelection('Saved historical address','','Warehouse B'),'Saved historical address');
});
