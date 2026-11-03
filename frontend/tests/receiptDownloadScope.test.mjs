import test, {after} from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp, rm} from 'node:fs/promises';
import {resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
import {createHash, webcrypto} from 'node:crypto';
import {build} from 'esbuild';
import {JSDOM} from 'jsdom';
import React, {act} from 'react';
import {createRoot} from 'react-dom/client';

// The component uses the real verifiedReceiptDownload implementation, including
// bounded stream reads and real SHA-256. Requests, URL allocation and clicks are
// synthetic; no upload/write endpoint, browser navigation or file is touched.
const temporary=await mkdtemp(resolve('node_modules/.receipt-download-tests-'));
await build({entryPoints:['src/DocumentAttachments.jsx'],outfile:resolve(temporary,'component.mjs'),bundle:true,platform:'node',format:'esm',loader:{'.css':'empty'},external:['react','react-dom']});
const DocumentAttachments=(await import(pathToFileURL(resolve(temporary,'component.mjs')))).default;
const dom=new JSDOM('<div id="root"></div>',{url:'http://localhost'});
const globals=['window','document','localStorage','IS_REACT_ACT_ENVIRONMENT','crypto'];
const saved=Object.fromEntries(globals.map(key=>[key,Object.getOwnPropertyDescriptor(globalThis,key)]));
Object.assign(globalThis,{window:dom.window,document:dom.window.document,localStorage:dom.window.localStorage,IS_REACT_ACT_ENVIRONMENT:true});
after(async()=>{
  dom.window.close();
  for(const [key,descriptor] of Object.entries(saved)){if(descriptor)Object.defineProperty(globalThis,key,descriptor);else delete globalThis[key];}
  await rm(temporary,{recursive:true,force:true});
});
const deferred=()=>{let resolve;const promise=new Promise(done=>{resolve=done;});return{promise,resolve};};
const settle=async action=>act(async()=>{await action?.();await new Promise(done=>setImmediate(done));});
const bytes=new TextEncoder().encode('%PDF-1.4\nSYNTHETIC DOWNLOAD ONLY\n%%EOF');
const row={id:'synthetic-a1',filename:'Synthetic receipt.pdf',media_type:'application/pdf',size_bytes:bytes.length,sha256:createHash('sha256').update(bytes).digest('hex'),is_archived:false,version:0};
const storage={used_bytes:bytes.length,quota_bytes:64*1024*1024,remaining_bytes:64*1024*1024-bytes.length,file_count:1,max_files_per_company:500,max_files_per_record:5};
const downloadButton=()=>document.querySelector('.attachment-actions button');
const refreshButton=()=>[...document.querySelectorAll('button')].find(button=>button.textContent==='Refresh receipts');
function changeSession(token,key='token'){
  const oldValue=localStorage.getItem('token');
  if(token===null)localStorage.removeItem('token');else localStorage.token=token;
  window.dispatchEvent(new window.StorageEvent('storage',{key,oldValue,newValue:token,storageArea:localStorage}));
}
function pendingDownload(stage='body',content=bytes){
  const gate=deferred(), reached=deferred(), digestFinished=deferred();let bodyReads=0;
  return {stage,reached:reached.promise,digestFinished:digestFinished.promise,release:gate.resolve,
    get bodyReads(){return bodyReads;},
    digest:async(...args)=>{
      if(stage==='digest'){reached.resolve();await gate.promise;}
      const result=await webcrypto.subtle.digest(...args);digestFinished.resolve();return result;
    },
    response:async()=>{
      if(stage==='headers'){reached.resolve();await gate.promise;}
      let reads=0;
      return {ok:true,headers:new Headers({'Content-Length':String(bytes.length),'X-Content-SHA256':row.sha256}),body:{getReader:()=>({
        read:async()=>{bodyReads++;if(reads++===0){if(stage==='body'){reached.resolve();await gate.promise;}return{done:false,value:content};}return{done:true};},
        cancel:async()=>{},
      })}};
    },
  };
}
async function fixture(t,role='viewer'){
  localStorage.clear();localStorage.token='synthetic-original-session';
  const urls=[],clicks=[],revoked=[],cleanup=[],requests=[],hooks={create:null,click:null};
  let response=async()=>{throw Error('Unconfigured synthetic download');},digest=(...args)=>webcrypto.subtle.digest(...args);
  const originalTimeout=globalThis.setTimeout;
  t.mock.method(globalThis,'fetch',async()=>{throw Error('Network is forbidden in this test');});
  t.mock.method(URL,'createObjectURL',blob=>{const url=`blob:synthetic-receipt-${urls.length+1}`;urls.push({url,blob});hooks.create?.();return url;});
  t.mock.method(URL,'revokeObjectURL',url=>revoked.push(url));
  t.mock.method(dom.window.HTMLAnchorElement.prototype,'click',function(){clicks.push({href:this.href,filename:this.download});hooks.click?.();});
  t.mock.method(globalThis,'setTimeout',(callback,delay,...args)=>{if(delay===1000){cleanup.push(()=>callback(...args));return 0;}return originalTimeout(callback,delay,...args);});
  Object.defineProperty(globalThis,'crypto',{value:{subtle:{digest:(...args)=>digest(...args)}},configurable:true});
  const api=async(path,options)=>{
    requests.push({path,options});assert.equal(options?.method,undefined,'read-only fixture refuses mutations');
    if(path.endsWith('/download')){assert.equal(options.rawResponse,true);return response();}
    assert.match(path,/\/records\/[^/]+\/attachments$/);return{attachments:[row],storage};
  };
  const root=createRoot(document.getElementById('root'));let mounted=true,props={companyId:'companyA',recordId:'recordA',role,api};
  const render=async next=>{props={...props,...next};await settle(()=>root.render(React.createElement(DocumentAttachments,props)));};
  const unmount=async()=>{if(mounted){await settle(()=>root.unmount());mounted=false;}};
  t.after(unmount);await render();
  const setFlow=flow=>{response=flow.response;digest=flow.digest;};
  return {urls,clicks,revoked,cleanup,requests,hooks,render,unmount,setFlow,
    setResponse:fn=>{response=fn;},
    downloads:()=>requests.filter(request=>request.path.endsWith('/download')),
    start:async flow=>{setFlow(flow);assert.equal(downloadButton().disabled,false);await settle(()=>downloadButton().click());await flow.reached;},
    finish:async(flow,{skipDigest=false}={})=>{digest=flow.digest;await settle(async()=>{flow.release();if(!skipDigest)await flow.digestFinished;});},
    flushCleanup:()=>{for(const callback of cleanup.splice(0))callback();},
  };
}

for(const stage of ['body','digest']) for(const change of ['token','company','unmount']) test(`discard verified ${stage} result after ${change} change`,async t=>{
  const f=await fixture(t),flow=pendingDownload(stage);await f.start(flow);
  if(change==='token')await settle(()=>{localStorage.token='synthetic-replacement-session';});
  if(change==='company')await f.render({companyId:'companyB',recordId:'recordB'});
  if(change==='unmount')await f.unmount();
  await f.finish(flow);assert.equal(f.urls.length,0);assert.equal(f.clicks.length,0);
  if(change!=='unmount')assert.equal(downloadButton().disabled,false);
  assert.equal(f.downloads()[0].options.signal.aborted,true,'finished obsolete request releases its controller');
});

for(const change of ['company','unmount','token']) test(`scope blocks late headers after ${change}`,async t=>{
  const f=await fixture(t),flow=pendingDownload('headers');await f.start(flow);
  if(change==='company')await f.render({companyId:'companyB',recordId:'recordB'});else if(change==='token')await settle(()=>{localStorage.token='synthetic-replacement-session';});else await f.unmount();
  await f.finish(flow,{skipDigest:true});assert.equal(f.urls.length,0);assert.equal(f.clicks.length,0);
  assert.equal(f.downloads()[0].options.signal.aborted,true);assert.equal(flow.bodyReads,0,'do not start verifying a stale response');
});

for(const stage of ['body','digest']) test(`observed token ABA cancels ${stage} download and permits fresh restored-session download`,async t=>{
  const f=await fixture(t),old=pendingDownload(stage);await f.start(old);
  await settle(()=>{changeSession('synthetic-replacement-session');changeSession('synthetic-original-session');});
  assert.equal(downloadButton().disabled,false);assert.equal(f.downloads()[0].options.signal.aborted,true);
  await f.finish(old);assert.equal(f.clicks.length,0);
  const fresh=pendingDownload('body');await f.start(fresh);await f.finish(fresh);
  assert.equal(f.urls.length,1);assert.equal(f.clicks.length,1);assert.equal(downloadButton().disabled,false);
});

for(const stage of ['body','digest']) test(`refresh during ${stage} verification clears busy and allows another download`,async t=>{
  const f=await fixture(t),old=pendingDownload(stage);await f.start(old);
  assert.equal(refreshButton().disabled,false);await settle(()=>refreshButton().click());
  assert.equal(downloadButton().disabled,false);assert.equal(downloadButton().textContent,'Download');
  assert.equal(f.downloads()[0].options.signal.aborted,true);
  await f.finish(old);assert.equal(f.clicks.length,0);assert.equal(downloadButton().disabled,false);
  const fresh=pendingDownload('body');await f.start(fresh);await f.finish(fresh);assert.equal(f.clicks.length,1);
});

for(const reset of ['refresh','storage']) test(`old verification finally cannot unlock a newer download after ${reset}`,async t=>{
  const f=await fixture(t),old=pendingDownload('body'),fresh=pendingDownload('body');await f.start(old);
  if(reset==='refresh')await settle(()=>refreshButton().click());else await settle(()=>changeSession('synthetic-replacement-session'));
  await f.start(fresh);await f.finish(old);
  assert.equal(downloadButton().disabled,true);assert.equal(downloadButton().textContent,'Verifying…');assert.equal(f.clicks.length,0);
  await f.finish(fresh);assert.equal(downloadButton().disabled,false);assert.equal(f.clicks.length,1);
});

test('rapid replacement download keeps newest controller authoritative',async t=>{
  const f=await fixture(t),old=pendingDownload('headers'),fresh=pendingDownload('body');let calls=0;
  f.setResponse(()=>calls++===0?old.response():fresh.response());
  await settle(()=>{const button=downloadButton();button.click();button.click();});await old.reached;await fresh.reached;
  assert.equal(f.downloads().length,2);assert.equal(f.downloads()[0].options.signal.aborted,true);
  await f.finish(old,{skipDigest:true});assert.equal(downloadButton().disabled,true);assert.equal(f.clicks.length,0);
  await f.finish(fresh);assert.equal(downloadButton().disabled,false);assert.equal(f.clicks.length,1);
});

test('viewer downloads exact verified bytes with forced-download MIME and URL cleanup',async t=>{
  const f=await fixture(t),flow=pendingDownload('body');assert.equal(document.querySelector('input[type=file]'),null);
  await f.start(flow);await f.finish(flow);
  assert.equal(f.urls.length,1);assert.equal(f.urls[0].blob.type,'application/octet-stream');assert.deepEqual(new Uint8Array(await f.urls[0].blob.arrayBuffer()),bytes);
  assert.deepEqual(f.clicks,[{href:f.urls[0].url,filename:row.filename}]);assert.equal(f.revoked.length,0);
  f.flushCleanup();assert.deepEqual(f.revoked,[f.urls[0].url]);assert.equal(downloadButton().disabled,false);
});

test('owner to viewer downgrade preserves legitimate receipt download',async t=>{
  const f=await fixture(t,'owner'),flow=pendingDownload('digest');await f.start(flow);await f.render({role:'viewer'});await f.finish(flow);
  assert.equal(f.clicks.length,1);assert.equal(document.querySelector('input[type=file]'),null);
});

test('late checksum failure cannot pollute replacement-session UI',async t=>{
  const f=await fixture(t),flow=pendingDownload('body',new Uint8Array(bytes.length));await f.start(flow);
  await settle(()=>{localStorage.token='synthetic-replacement-session';});await f.finish(flow);
  assert.equal(f.clicks.length,0);assert.equal(document.querySelector('[role=alert]'),null);assert.equal(downloadButton().disabled,false);
});

test('current-session checksum failure remains visible and cannot dispatch',async t=>{
  const f=await fixture(t),flow=pendingDownload('body',new Uint8Array(bytes.length));await f.start(flow);await f.finish(flow);
  assert.match(document.querySelector('[role=alert]').textContent,/checksum mismatch/);assert.equal(f.urls.length,0);assert.equal(downloadButton().disabled,false);
});

test('object URL is reclaimed after click throws',async t=>{
  const f=await fixture(t),flow=pendingDownload('body');f.hooks.click=()=>{throw Error('SYNTHETIC click failed');};await f.start(flow);await f.finish(flow);
  assert.equal(f.urls.length,1);assert.match(document.querySelector('[role=alert]').textContent,/SYNTHETIC click failed/);assert.equal(downloadButton().disabled,false);
  f.flushCleanup();assert.deepEqual(f.revoked,[f.urls[0].url]);
});

for(const event of ['storage','token-only']) test(`late ${event} invalidation reclaims object URL without dispatch`,async t=>{
  const f=await fixture(t),flow=pendingDownload('body');f.hooks.create=()=>{if(event==='storage')changeSession('synthetic-replacement-session');else localStorage.token='synthetic-replacement-session';};
  await f.start(flow);await f.finish(flow);assert.equal(f.urls.length,1);assert.equal(f.clicks.length,0);assert.equal(downloadButton().disabled,false);
  f.flushCleanup();assert.deepEqual(f.revoked,[f.urls[0].url]);
});

test('clear-storage event cancels old verification even when token is restored',async t=>{
  const f=await fixture(t),flow=pendingDownload('body');await f.start(flow);
  await settle(()=>{localStorage.clear();window.dispatchEvent(new window.StorageEvent('storage',{key:null,storageArea:localStorage}));localStorage.token='synthetic-original-session';});
  await f.finish(flow);assert.equal(f.clicks.length,0);assert.equal(f.downloads()[0].options.signal.aborted,true);assert.equal(downloadButton().disabled,false);
});

test('unrelated storage event leaves legitimate receipt download intact',async t=>{
  const f=await fixture(t),flow=pendingDownload('body');await f.start(flow);
  await settle(()=>window.dispatchEvent(new window.StorageEvent('storage',{key:'unrelated',storageArea:localStorage})));
  assert.equal(f.downloads()[0].options.signal.aborted,false);await f.finish(flow);assert.equal(f.clicks.length,1);
});
