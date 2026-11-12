import test,{after} from 'node:test';import assert from 'node:assert/strict';import {mkdtemp,rm,readFile} from 'node:fs/promises';import {resolve} from 'node:path';import {pathToFileURL} from 'node:url';import {build} from 'esbuild';import {JSDOM} from 'jsdom';import React,{act} from 'react';
const temp=await mkdtemp(resolve('node_modules/.scan-tests-'));
await build({entryPoints:['src/RecordEditor.jsx'],outfile:resolve(temp,'editor.mjs'),bundle:true,platform:'node',format:'esm',external:['react','react-dom','lucide-react'],plugins:[{name:'synthetic-image',setup(b){if(process.env.APEX_SCAN_BEFORE)b.onLoad({filter:/RecordEditor\.jsx$/},async()=>({contents:await readFile(process.env.APEX_SCAN_BEFORE,'utf8'),loader:'jsx',resolveDir:resolve('src')}));b.onLoad({filter:/prepareInvoiceImage\.js$/},()=>({contents:'export const prepareInvoiceImage=(file)=>globalThis.scanImage(file);',loader:'js'}));}}]});
const dom=new JSDOM('<div id="root"></div>',{url:'http://localhost'});Object.assign(globalThis,{window:dom.window,document:dom.window.document,localStorage:dom.window.localStorage,IS_REACT_ACT_ENVIRONMENT:true});URL.createObjectURL=()=> 'blob:synthetic';URL.revokeObjectURL=()=>{};
const {createRoot}=await import('react-dom/client');const Editor=(await import(pathToFileURL(resolve(temp,'editor.mjs')))).default;
after(async()=>{dom.window.close();await rm(temp,{recursive:true,force:true});});
const deferred=()=>{let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b;});return{promise,resolve,reject};};
const Modal=({children})=>React.createElement('section',null,children);
async function mount(){const image=deferred(),ocr=deferred();let images=0,posts=0;globalThis.scanImage=()=>{images++;return image.promise;};const root=createRoot(document.getElementById('root'));let props={kind:'purchase_bill',company:{role:'owner',tax_mode:'regular',state_code:'27'},companyId:'a',records:[],source:{id:'bill',name:'Original supplier',data:{lines:[{description:'Original item',quantity:'1',rate:'10',gst_rate:'0'}]}},edit:true,Modal,labels:{purchase_bill:'Purchase bills'},documentKinds:['purchase_bill'],today:()=> '2026-04-01',money:String,save:()=>{},close:()=>{},api:async(path)=>{if(path==='/ocr/status')return{ready:true};if(path.endsWith('/ocr/purchase-draft')){posts++;return ocr.promise;}if(path.endsWith('bank-accounts'))return[];return {amount:'10',data:{lines:[]}};}};const render=async changes=>{props={...props,...changes};await act(async()=>root.render(React.createElement(Editor,props)));};await render({});const start=async()=>{await act(async()=>{const input=document.querySelector('input[type=file]');Object.defineProperty(input,'files',{configurable:true,value:[{}]});input.dispatchEvent(new window.Event('change',{bubbles:true}));input.dispatchEvent(new window.Event('change',{bubbles:true}));});};return{root,image,ocr,start,render,get images(){return images},get posts(){return posts}};}
for(const stage of ['image','ocr'])for(const mode of ['current','company','role-roundtrip','token','unmount'])for(const failure of [false,true])test(`scan ${stage} ${mode} ${failure?'failure':'success'}`,async()=>{
 const v=await mount();await v.start();assert.equal(v.images,1);
 if(stage==='ocr')await act(async()=>v.image.resolve('synthetic'));
 if(mode==='company')await v.render({companyId:'b'});
 if(mode==='role-roundtrip'){await v.render({company:{role:'viewer',tax_mode:'regular',state_code:'27'}});await v.render({company:{role:'owner',tax_mode:'regular',state_code:'27'}});}
 if(mode==='token')localStorage.token='replacement';
 if(mode==='unmount')await act(async()=>v.root.unmount());
 if(stage==='image')await act(async()=>failure?v.image.reject(new Error('image failed')):v.image.resolve('synthetic'));
 if(stage==='ocr'||(!failure&&mode==='current'))await act(async()=>failure?v.ocr.reject(new Error('OCR failed')):v.ocr.resolve({draft:{supplier_name:'Scanned supplier',items:[{description:'Scanned item',quantity:'1',rate:'20'}]}}));
 if(mode==='current'&&!failure)assert.equal(document.querySelector('[name=name]').value,'Scanned supplier');
 else if(mode!=='unmount'){assert.equal(document.querySelector('[name=name]').value,'Original supplier');if(mode!=='current')assert.doesNotMatch(document.body.textContent,/image failed|OCR failed/);}
 assert.equal(v.posts,stage==='ocr'||(mode==='current'&&!failure)?1:0);
 localStorage.removeItem('token');
 if(mode!=='unmount')await act(async()=>v.root.unmount());
});
