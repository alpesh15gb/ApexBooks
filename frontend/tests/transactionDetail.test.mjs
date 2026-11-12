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

function renderNote(role, remaining='0', cancelled=false) {
 return renderToStaticMarkup(React.createElement(Detail,{record:{id:'note',kind:'debit_note',number:'DN-1',name:'Supplier',amount:'160',posted:true,cancelled,credit_remaining:remaining,data:{},document_trail:[{id:'refund',kind:'supplier_refund',number:'RF-1',name:'Supplier',date:'2026-04-02',amount:'60',allocated_amount:null,relations:['Credit settlement'],cancelled:false},{id:'application',kind:'credit_application',number:'CA-1',name:'Supplier',date:'2026-04-02',amount:'100',allocated_amount:null,relations:['Credit settlement'],cancelled:false}]},records:[],company:{name:'Synthetic',role},labels:{},onManageCredits:()=>{}}));
}
test('fully consumed supplier note retains refund and application history without loaded register rows',()=>{
 const markup=renderNote('owner');assert.match(markup,/RF-1/);assert.match(markup,/CA-1/);assert.match(markup,/₹60\.00/);assert.match(markup,/₹100\.00/);assert.doesNotMatch(markup,/Open supplier credits/);
});
test('available credit has a nonposting workspace link only for writable active notes',()=>{
 assert.match(renderNote('owner','100'),/Open supplier credits and refunds/);
 assert.match(renderNote('editor','100'),/opening the workspace does not post anything/);
 assert.doesNotMatch(renderNote('viewer','100'),/Open supplier credits/);
 assert.doesNotMatch(renderNote('owner','100',true),/Open supplier credits/);
});
test('reopened source shows cancelled conversion history and can still convert again',()=>{
 const markup=renderToStaticMarkup(React.createElement(Detail,{record:{id:'quote',kind:'estimate',number:'EST-1',data:{},document_trail:[{id:'old',kind:'sales_invoice',number:'INV-CANCELLED',name:'Buyer',date:'2026-04-02',amount:'100',allocated_amount:null,relations:['Converted document'],cancelled:true}]},records:[],company:{role:'owner'},labels:{}}));
 assert.match(markup,/INV-CANCELLED/);assert.match(markup,/Cancelled/);assert.match(markup,/Convert to invoice/);
});

test('cancelled split allocations show historical amounts rather than active allocation labels',()=>{
 const markup=renderToStaticMarkup(React.createElement(Detail,{record:{id:'payment',kind:'payment_in',number:'RC-1',amount:'100',cancelled:true,data:{cancelled:{reason:'Duplicate'}},document_trail:[{id:'invoice',kind:'sales_invoice',number:'INV-1',name:'Buyer',date:'2026-04-01',amount:'100',allocated_amount:null,historical_allocated_amount:'50',relations:['Cancelled allocation (history only)'],cancelled:false}]},records:[],company:{role:'viewer'},labels:{}}));
 assert.match(markup,/history only/);assert.match(markup,/₹50\.00/);assert.match(markup,/Cancelled allocation/);assert.doesNotMatch(markup,/>Allocated amount</);
});

test('totals bridge uses stored components including negative round off and does not recompute rates',()=>{
 const markup=renderToStaticMarkup(React.createElement(Detail,{record:{kind:'sales_invoice',amount:'118',data:{taxable:'100.20',cgst:'9.02',sgst:'9.02',igst:'0',round_off:'-0.24',lines:[{description:'Stored',quantity:'1',rate:'999',taxable:'100.20',tax:'18.04'}]}},records:[],company:{role:'viewer'},labels:{}}));
 assert.match(markup,/Subtotal after discounts/);assert.match(markup,/₹100\.20/);assert.match(markup,/CGST/);assert.match(markup,/SGST \/ UTGST/);assert.match(markup,/-₹0\.24/);assert.match(markup,/do not establish GST eligibility or filing status/);
});
test('legacy missing breakdown does not invent a tax subtotal',()=>{
 const markup=renderToStaticMarkup(React.createElement(Detail,{record:{kind:'estimate',amount:'200',data:{lines:[{description:'Legacy',quantity:'1',rate:'200'}]}},records:[],company:{role:'viewer'},labels:{}}));
 assert.match(markup,/breakdown are unavailable/);assert.doesNotMatch(markup,/Subtotal after discounts/);
});
test('stock opening and loss show saved quantity and reason without a payment trail or guessed unit cost',()=>{
 for(const [kind,data,expected] of [['stock_opening',{quantity:'10',unit:'pcs',unit_cost:'80'},/10 pcs/],['stock_adjustment',{quantity:'5',unit:'pcs',direction:'decrease',reason:'Damaged',unit_cost:null},/−5 pcs/]]) {
 const markup=renderToStaticMarkup(React.createElement(Detail,{record:{kind,name:'Synthetic item',amount:'800',posted:true,data},records:[],company:{role:'viewer'},labels:{}}));
 assert.match(markup,expected);assert.doesNotMatch(markup,/Payment &amp; document trail/);assert.match(markup,/not a payment/);
 if(kind==='stock_opening')assert.match(markup,/₹80\.00/);else{assert.match(markup,/Not separately recorded/);assert.match(markup,/Reason: Damaged/);}
 }
});
