import test, { after } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, rm } from 'node:fs/promises';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { build } from 'esbuild';
import { JSDOM } from 'jsdom';
import React, { act } from 'react';
const temporary=await mkdtemp(resolve('node_modules/.dashboard-date-tests-'));
const dom=new JSDOM('<div id="root"></div>',{url:'http://localhost/'});
Object.assign(globalThis,{window:dom.window,document:dom.window.document,IS_REACT_ACT_ENVIRONMENT:true,ResizeObserver:class{observe(){} disconnect(){}}});
const {createRoot}=await import('react-dom/client');
const outfile=resolve(temporary,'component.mjs');
await build({entryPoints:['src/BusinessOverview.jsx'],outfile,bundle:true,platform:'node',format:'esm',jsx:'automatic',external:['react','react-dom','lucide-react']});
const Overview=(await import(pathToFileURL(outfile))).default;
const RealDate=Date;
after(async()=>{globalThis.Date=RealDate;dom.window.close();await rm(temporary,{recursive:true,force:true});});
test('rendered dashboard report requests include the India business day at UTC midnight boundary',async()=>{
 for(const [instant,end,start] of [['2026-11-02T18:29:59Z','2026-11-02','2026-04-01'],['2026-11-02T18:30:00Z','2026-11-03','2026-04-01'],['2026-03-31T18:30:00Z','2026-04-01','2026-04-01']]){
  globalThis.Date=class extends RealDate{constructor(...args){super(...(args.length?args:[instant]));}static now(){return new RealDate(instant).getTime();}};
  const paths=[];const root=createRoot(document.getElementById('root'));
  try{
   await act(async()=>root.render(React.createElement(Overview,{company:{id:'synthetic',name:'Synthetic',role:'owner'},records:[],onNavigate:()=>{},onCreate:()=>{},api:async path=>{paths.push(path);return path.endsWith('/bank-accounts')?[]:path.includes('/financial?')?{accounts:[],income:100,expenses:0,net_profit:100}:path.includes('/summary?')?{sales:100,receivables:100,payables:0}:{cash_total:0};}})));
   for(const name of ['summary','financial'])assert.ok(paths.includes(`/companies/synthetic/reports/${name}?from_date=${start}&to_date=${end}`));
   assert.ok(paths.includes(`/companies/synthetic/reports/gst-payable?from_date=2000-01-01&to_date=${end}`));
  }finally{await act(async()=>root.unmount());globalThis.Date=RealDate;}
 }
});
