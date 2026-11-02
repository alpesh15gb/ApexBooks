import test from 'node:test';
import assert from 'node:assert/strict';
import {lineDiscountMode,serializeLineDiscount,changeLineDiscount} from '../src/lineDiscount.js';
test('fixed input including zero is distinct from calculated discount and preserves other commercial fields',()=>{
 for(const amount of ['10','0']){
  const line={quantity:'1',rate:'100',discount_amount:amount,discount_percent:'0',discount:'10',price_includes_tax:true,gst_rate:'18'};
  assert.equal(lineDiscountMode(line),'amount');const out=serializeLineDiscount(line);assert.equal(out.discount_amount,amount);assert.equal(Object.hasOwn(out,'discount_percent'),false);assert.equal(out.price_includes_tax,true);assert.equal(line.discount_percent,'0');
 }
 assert.equal(lineDiscountMode({discount:'10',discount_percent:'10'}),'percent');
});
test('deliberate mode switch clears inactive input and never silently converts or prorates',()=>{
 const fixed={quantity:'2',rate:'100',discount_amount:'10',discount_percent:'0'};
 const percent=changeLineDiscount(fixed,'discount_mode','percent');assert.equal(percent.discount_percent,'0');assert.equal(Object.hasOwn(percent,'discount_amount'),false);
 const changed=changeLineDiscount(percent,'discount_percent','5');assert.equal(changed.discount_percent,'5');assert.equal(Object.hasOwn(changed,'discount_amount'),false);
 const back=changeLineDiscount(changed,'discount_mode','amount');assert.equal(back.discount_amount,'0');assert.equal(Object.hasOwn(back,'discount_percent'),false);
 assert.equal(serializeLineDiscount({...fixed,quantity:'1'}).discount_amount,'10');
});
