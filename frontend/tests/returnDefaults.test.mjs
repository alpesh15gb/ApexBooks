import test from 'node:test';
import assert from 'node:assert/strict';
import {remainingReturnDraftLines} from '../src/returnDefaults.js';
test('repeat return uses remaining quantity and omits exhausted lines without repricing',()=>{
 const rows=[{description:'First',quantity:'2',rate:'100',discount_amount:'7',return_capacity_scope:'additional_returns',remaining_return_quantity:'1.000'},{description:'Used',quantity:'2',return_capacity_scope:'additional_returns',remaining_return_quantity:'0'}];
 const result=remainingReturnDraftLines(rows);assert.equal(result.length,1);assert.equal(result[0].quantity,'1.000');assert.equal(result[0].discount_amount,'7');assert.equal(result[0].rate,'100');assert.equal(rows[0].quantity,'2');
});
test('unknown and older-server allowances require manual quantity review',()=>{
 for(const row of [{quantity:'2'},{quantity:'2',return_capacity_scope:'additional_returns',remaining_return_quantity:null,return_capacity_reason:'Ambiguous source'}]) assert.equal(remainingReturnDraftLines([row])[0].quantity,'');
});
