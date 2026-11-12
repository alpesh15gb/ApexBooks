import test from 'node:test';
import assert from 'node:assert/strict';
import {parseMasterCsv} from '../src/masterCsv.js';
for (const ending of ['\n','\r\n','\r']) test(`CSV accepts line ending ${JSON.stringify(ending)}`,()=>{
 assert.deepEqual(parseMasterCsv(`name,phone${ending}Buyer,00123${ending}`,'party'),[{name:'Buyer',phone:'00123'}]);
});
for (const row of ['Buyer','Buyer,00123,','Buyer,00123,extra']) test(`CSV rejects inconsistent width ${row}`,()=>assert.throws(()=>parseMasterCsv(`name,phone\n${row}`,'party'),/row 2.*expected 2 columns/));
for (const value of ['=SUM(1,2)','+1+2','-1+2','@SUM(1,2)','="a",\r\n"b"']) test(`CSV preserves literal ${JSON.stringify(value)}`,()=>{
 const quoted='"'+value.replaceAll('"','""')+'"';
 assert.deepEqual(parseMasterCsv(`name,phone\n${quoted},00123`,'party'),[{name:value,phone:'00123'}]);
});
test('CSV error identifies physical row after embedded newline',()=>assert.throws(()=>parseMasterCsv('name,address\nBuyer,"line1\nline2"\nOther','party'),/row 4.*expected 2 columns/));
