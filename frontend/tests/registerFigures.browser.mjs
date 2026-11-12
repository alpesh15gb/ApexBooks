// Synthetic browser geometry: run from frontend with node tests/registerFigures.browser.mjs.
import assert from 'node:assert/strict';
import {mkdtemp,readFile,writeFile,rm,mkdir} from 'node:fs/promises';
import {resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
import {execFileSync} from 'node:child_process';
import {build} from 'esbuild';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
const temp=await mkdtemp(resolve('node_modules/.register-figures-'));
const artifacts='/tmp/apex-register-figures';await mkdir(artifacts,{recursive:true});
try {
 const module=resolve(temp,'RegisterOverview.mjs');
 await build({entryPoints:['src/RegisterOverview.jsx'],outfile:module,bundle:true,platform:'node',format:'esm',jsx:'automatic',external:['react','react-dom','lucide-react']});
 const Component=(await import(pathToFileURL(module))).default;
 let css='';for(const file of ['commerce','style','capabilities','workspace','flows','ledger','rich-workspace','clarity','quickbooks-workflows'])css+=await readFile('src/'+file+'.css','utf8');
 const records=[{kind:'sales_invoice',posted:true,amount:'1234567890123.45',outstanding:'1234567.89'}];
 const markup=renderToStaticMarkup(React.createElement(Component,{page:'sales_invoice',records,filter:'all',onFilter:()=>{}}));
 for(const width of [1200,768,375,320]) {
  const file=resolve(artifacts,'register-'+width+'.html');
  await writeFile(file,`<!doctype html><html><head><meta name="viewport" content="width=device-width, initial-scale=1"><style>${css}\nbody{padding:16px}main{margin-left:${width>=1000?'240px':'0'};min-width:0}</style></head><body><main>${markup}</main><script>const results=[...document.querySelectorAll('.register-overview strong')].map(n=>{let r=document.createRange();r.selectNodeContents(n);let rects=[...r.getClientRects()];return {text:n.textContent,width:r.getBoundingClientRect().width,available:n.clientWidth,lines:new Set(rects.map(r=>Math.round(r.top))).size}});document.body.dataset.result=JSON.stringify({width:innerWidth,overflow:document.documentElement.scrollWidth>innerWidth+1,results});</script></body></html>`);
  const output=execFileSync(process.env.CHROMIUM||'/usr/bin/chromium',['--headless','--disable-dev-shm-usage',`--user-data-dir=${temp}/profile-${width}`,'--no-sandbox','--disable-gpu','--no-proxy-server','--host-resolver-rules=MAP * ~NOTFOUND','--disable-background-networking',`--window-size=${width},790`,'--force-device-scale-factor=1','--virtual-time-budget=1500',`--screenshot=${artifacts}/register-${width}.png`,'--dump-dom',pathToFileURL(file).href],{encoding:'utf8',stdio:['ignore','pipe','pipe'],maxBuffer:5_000_000});
  const match=output.match(/data-result="([^"]+)"/);assert.ok(match,'geometry result');
  const result=JSON.parse(match[1].replaceAll('&quot;','"').replaceAll('&amp;','&'));
  assert.equal(result.width,width,'requested viewport must be honored');assert.equal(result.overflow,false,JSON.stringify(result));assert.equal(result.results.length,4);
  for(const row of result.results){assert.equal(row.lines,1,JSON.stringify(row));assert.ok(row.width<=row.available+1,JSON.stringify(row));}
  console.log(JSON.stringify(result));
 }
} finally {await rm(temp,{recursive:true,force:true});}
