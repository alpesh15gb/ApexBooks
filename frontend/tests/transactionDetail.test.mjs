import test,{after} from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,rm} from 'node:fs/promises';
import {resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
import {build} from 'esbuild';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
const temporary=await mkdtemp(resolve('node_modules/.transaction-detail-test-'));
await build({entryPoints:['src/TransactionDetail.jsx'],outfile:resolve(temporary,'component.mjs'),bundle:true,platform:'node',format:'esm',loader:{'.css':'empty'},external:['react','react-dom','lucide-react']});
const Detail=(await import(pathToFileURL(resolve(temporary,'component.mjs')))).default;
after(()=>rm(temporary,{recursive:true,force:true}));
test('read-only detail explains fixed and percentage discounts without changing totals',()=>{
 const markup=renderToStaticMarkup(React.createElement(Detail,{record:{id:'r',kind:'sales_invoice',amount:'81.00',posted:true,outstanding:'81.00',data:{lines:[{description:'Synthetic fixed',quantity:'1',rate:'100',discount_amount:'10.00',discount_percent:'0',document_discount:'9.00',taxable:'81.00',tax:'0'},{description:'Synthetic percentage',quantity:'1',rate:'20',discount_percent:'5',taxable:'19',tax:'0'}]}},records:[],company:{name:'Synthetic books',role:'viewer'},features:[],labels:{sales_invoice:'Invoice'}}));
 assert.match(markup,/Line discount: ₹10\.00/);assert.match(markup,/Document discount allocation: ₹9\.00/);assert.match(markup,/Line discount: 5%/);assert.match(markup,/₹81\.00/);assert.doesNotMatch(markup,/Edit details/);
});

test('cancelled documents show reversal and suppress payment and edit actions even with stale posting data',()=>{
 const markup=renderToStaticMarkup(React.createElement(Detail,{record:{id:'r',kind:'sales_invoice',amount:'100',posted:true,cancelled:true,outstanding:'100',data:{}},records:[],company:{name:'Synthetic books',role:'owner'},features:[],labels:{sales_invoice:'Invoice'}}));
 assert.match(markup,/Reversed/);assert.doesNotMatch(markup,/Still outstanding|Collect payment|Sales return|Edit details/);
});

test('unknown outstanding balances are not presented as zero or settled',()=>{
 const markup=renderToStaticMarkup(React.createElement(Detail,{record:{id:'r',kind:'sales_invoice',amount:'100',posted:true,data:{}},records:[],company:{name:'Synthetic books',role:'viewer'},features:[],labels:{sales_invoice:'Invoice'}}));
 assert.match(markup,/Refresh details to see the current balance/);assert.doesNotMatch(markup,/₹0\.00|>Settled</);
});
