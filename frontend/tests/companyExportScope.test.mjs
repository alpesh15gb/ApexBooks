import test, {after} from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp, rm} from 'node:fs/promises';
import {resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
import {build} from 'esbuild';
import {JSDOM} from 'jsdom';
import React, {act} from 'react';
import {createRoot} from 'react-dom/client';

// No browser navigation, network, or actual download: only synthetic response
// objects, object-URL accounting, and an instrumented anchor.click are used.
const temporary = await mkdtemp(resolve('node_modules/.company-export-tests-'));
await build({entryPoints:['src/CompanyDataExport.jsx'],outfile:resolve(temporary,'component.mjs'),bundle:true,platform:'node',format:'esm',external:['react','react-dom','lucide-react']});
const CompanyDataExport = (await import(pathToFileURL(resolve(temporary,'component.mjs')))).default;
const dom = new JSDOM('<div id="root"></div>', {url:'http://localhost'});
const saved = Object.fromEntries(['window','document','localStorage','IS_REACT_ACT_ENVIRONMENT'].map(key=>[key,Object.getOwnPropertyDescriptor(globalThis,key)]));
Object.assign(globalThis,{window:dom.window,document:dom.window.document,localStorage:dom.window.localStorage,IS_REACT_ACT_ENVIRONMENT:true});
after(async()=>{
  dom.window.close();
  for (const [key,descriptor] of Object.entries(saved)) {
    if (descriptor) Object.defineProperty(globalThis,key,descriptor); else delete globalThis[key];
  }
  await rm(temporary,{recursive:true,force:true});
});
const deferred = () => {let resolve; const promise=new Promise(done=>{resolve=done;}); return {promise,resolve};};
const settle = async action => act(async()=>{await action?.();await new Promise(done=>setImmediate(done));});
const findButton = () => document.querySelector('button');
const success = () => ({ok:true,blob:async()=>new Blob(['{"synthetic":true}'],{type:'application/json'})});
function changeSession(token, key='token') {
  const oldValue=localStorage.getItem('token');
  if (token===null) localStorage.removeItem('token'); else localStorage.token=token;
  window.dispatchEvent(new window.StorageEvent('storage',{key,oldValue,newValue:token,storageArea:localStorage}));
}
async function fixture(t) {
  localStorage.clear(); localStorage.token='synthetic-original-session';
  const urls=[], clicks=[], revoked=[], cleanup=[], requests=[];
  const originalTimeout=globalThis.setTimeout;
  const hooks={create:null,click:null};
  t.mock.method(globalThis,'fetch',async()=>{throw new Error('Unexpected synthetic fetch');});
  t.mock.method(URL,'createObjectURL',blob=>{
    const url=`blob:synthetic-export-${urls.length+1}`;urls.push({url,blob});hooks.create?.();return url;
  });
  t.mock.method(URL,'revokeObjectURL',url=>revoked.push(url));
  t.mock.method(dom.window.HTMLAnchorElement.prototype,'click',function(){
    clicks.push({filename:this.download,href:this.href});hooks.click?.();
  });
  t.mock.method(globalThis,'setTimeout',(callback,delay,...args)=>{
    if(delay===1000){cleanup.push(()=>callback(...args));return 0;}
    return originalTimeout(callback,delay,...args);
  });
  const root=createRoot(document.getElementById('root'));
  let mounted=true, props={companyId:'companyA-one',role:'owner'};
  const render=async next=>{props={...props,...next};await settle(()=>root.render(React.createElement(CompanyDataExport,props)));};
  const unmount=async()=>{if(mounted){await settle(()=>root.unmount());mounted=false;}};
  t.after(unmount);
  await render();
  return {urls,clicks,revoked,cleanup,requests,hooks,render,unmount,
    click:async()=>settle(()=>findButton().click()),
    flushCleanup:()=>{for(const callback of cleanup.splice(0))callback();},
    fetch:implementation=>{globalThis.fetch=async(path,options={})=>{
      assert.equal(options.method,undefined,'exports must remain read-only');
      requests.push({path,options});return implementation(path,options);
    };},
  };
}
function pendingResponse(stage) {
  const gate=deferred(); let reached=false, bodyCalls=0;
  return {
    get reached(){return reached;}, get bodyCalls(){return bodyCalls;}, release:gate.resolve,
    fetch:async()=>{
      if(stage==='fetch'){reached=true;await gate.promise;}
      if(stage==='error-json')return {ok:false,json:async()=>{bodyCalls++;reached=true;await gate.promise;return {detail:'SYNTHETIC old-company failure'};}};
      return {ok:true,blob:async()=>{bodyCalls++;if(stage==='blob'){reached=true;await gate.promise;}return new Blob(['{"synthetic":true}']);}};
    },
  };
}

for(const stage of ['fetch','blob','error-json']) for(const change of ['company','token','role','unmount']) {
  test(`discard deferred ${stage} after ${change} change even when fetch ignores abort`,async t=>{
    const f=await fixture(t), pending=pendingResponse(stage);f.fetch(pending.fetch);
    await f.click();assert.equal(pending.reached,true);assert.equal(findButton().disabled,true);
    if(change==='company')await f.render({companyId:'companyB-two'});
    if(change==='token')await settle(()=>{localStorage.token='synthetic-replacement-session';});
    if(change==='role')await f.render({role:'viewer'});
    if(change==='unmount')await f.unmount();
    await settle(pending.release);
    assert.equal(f.urls.length,0);assert.equal(f.clicks.length,0);
    assert.doesNotMatch(document.body.textContent,/SYNTHETIC old-company failure/);
    if(change==='company'||change==='token')assert.equal(findButton().disabled,false);
    if(change!=='token')assert.equal(f.requests[0].options.signal.aborted,true);
    if(stage==='fetch')assert.equal(pending.bodyCalls,0,'do not consume stale response body');
  });
}

for(const stage of ['fetch','blob','error-json']) test(`storage-event token ABA never revives deferred ${stage}`,async t=>{
  const f=await fixture(t), pending=pendingResponse(stage);f.fetch(pending.fetch);
  await f.click();assert.equal(pending.reached,true);
  await settle(()=>{changeSession('synthetic-replacement-session');changeSession('synthetic-original-session');});
  assert.equal(findButton().disabled,false);assert.equal(f.requests[0].options.signal.aborted,true);
  await settle(pending.release);
  assert.equal(f.urls.length,0);assert.equal(f.clicks.length,0);assert.doesNotMatch(document.body.textContent,/SYNTHETIC old-company failure/);
  f.fetch(async()=>success());await f.click();
  assert.equal(f.urls.length,1);assert.equal(f.clicks.length,1);
  assert.equal(f.requests[1].options.headers.Authorization,'Bearer synthetic-original-session');
  f.flushCleanup();assert.deepEqual(f.revoked,[f.urls[0].url]);
});

for(const change of ['company','role']) test(`${change} ABA invalidates old request and allows a fresh restored-context export`,async t=>{
  const f=await fixture(t), pending=pendingResponse('blob');f.fetch(pending.fetch);await f.click();
  if(change==='company'){await f.render({companyId:'companyB-two'});await f.render({companyId:'companyA-one'});}
  else{await f.render({role:'viewer'});await f.render({role:'owner'});}
  await settle(pending.release);assert.equal(f.clicks.length,0);
  f.fetch(async()=>success());await f.click();assert.equal(f.clicks.length,1);assert.equal(f.clicks[0].filename,'apex-company-companyA.json');
});

test('normal export preserves request scope, filename, exact blob and cleanup',async t=>{
  const f=await fixture(t), blob=new Blob(['{"synthetic":"original"}'],{type:'application/json'});
  f.fetch(async()=>({ok:true,blob:async()=>blob}));await f.click();
  assert.equal(f.requests.length,1);assert.equal(f.requests[0].path,'/api/companies/companyA-one/data-export.json');
  assert.equal(f.requests[0].options.headers.Authorization,'Bearer synthetic-original-session');
  assert.equal(f.urls[0].blob,blob);assert.deepEqual(f.clicks,[{filename:'apex-company-companyA.json',href:f.urls[0].url}]);
  assert.equal(findButton().disabled,false);assert.equal(f.revoked.length,0);f.flushCleanup();assert.deepEqual(f.revoked,[f.urls[0].url]);
});

test('concurrent clicks before React redraw start only one request',async t=>{
  const f=await fixture(t), pending=pendingResponse('fetch');f.fetch(pending.fetch);
  await settle(()=>{const button=findButton();button.click();button.click();button.click();});
  assert.equal(f.requests.length,1);await settle(pending.release);assert.equal(f.clicks.length,1);
});

for(const stage of ['fetch','blob','error-json']) test(`old ${stage} completion cannot clear busy or error state owned by a newer request`,async t=>{
  const f=await fixture(t), old=pendingResponse(stage), newer=pendingResponse('blob');
  f.fetch(old.fetch);await f.click();
  await f.render({companyId:'companyB-two'});f.fetch(newer.fetch);await f.click();assert.equal(newer.reached,true);
  await settle(old.release);assert.equal(findButton().disabled,true);assert.match(findButton().textContent,/Preparing/);
  assert.equal(f.clicks.length,0);assert.doesNotMatch(document.body.textContent,/SYNTHETIC old-company failure/);
  await settle(newer.release);assert.equal(findButton().disabled,false);assert.equal(f.clicks.length,1);assert.equal(f.clicks[0].filename,'apex-company-companyB.json');
});

test('fresh replacement-session request remains locked when original-session request settles',async t=>{
  const f=await fixture(t), old=pendingResponse('blob'), newer=pendingResponse('blob');
  f.fetch(old.fetch);await f.click();await settle(()=>changeSession('synthetic-replacement-session'));
  f.fetch(newer.fetch);await f.click();await settle(old.release);
  assert.equal(findButton().disabled,true);assert.equal(f.clicks.length,0);
  await settle(newer.release);assert.equal(f.clicks.length,1);assert.equal(f.requests[1].options.headers.Authorization,'Bearer synthetic-replacement-session');
});

test('clear-storage event invalidates pending export even if original token is restored',async t=>{
  const f=await fixture(t), pending=pendingResponse('blob');f.fetch(pending.fetch);await f.click();
  await settle(()=>{localStorage.clear();window.dispatchEvent(new window.StorageEvent('storage',{key:null,storageArea:localStorage}));localStorage.token='synthetic-original-session';});
  await settle(pending.release);assert.equal(f.clicks.length,0);assert.equal(f.requests[0].options.signal.aborted,true);
});

test('unrelated storage event does not cancel legitimate export',async t=>{
  const f=await fixture(t), pending=pendingResponse('blob');f.fetch(pending.fetch);await f.click();
  await settle(()=>window.dispatchEvent(new window.StorageEvent('storage',{key:'unrelated',storageArea:localStorage})));
  await settle(pending.release);assert.equal(f.clicks.length,1);assert.equal(f.requests[0].options.signal.aborted,false);
});

test('object URL is reclaimed if anchor click throws',async t=>{
  const f=await fixture(t);f.fetch(async()=>success());f.hooks.click=()=>{throw Error('SYNTHETIC click failure');};await f.click();
  assert.equal(f.urls.length,1);assert.match(document.body.textContent,/SYNTHETIC click failure/);assert.equal(findButton().disabled,false);
  f.flushCleanup();assert.deepEqual(f.revoked,[f.urls[0].url]);
});

for(const event of ['storage','token-only']) test(`object URL is reclaimed without click after late ${event} invalidation`,async t=>{
  const f=await fixture(t);f.fetch(async()=>success());
  f.hooks.create=()=>{if(event==='storage')changeSession('synthetic-replacement-session');else localStorage.token='synthetic-replacement-session';};
  await f.click();assert.equal(f.urls.length,1);assert.equal(f.clicks.length,0);assert.equal(findButton().disabled,false);
  f.flushCleanup();assert.deepEqual(f.revoked,[f.urls[0].url]);
});

for(const detail of ['SYNTHETIC current-company failure','COMPLETE_BACKUP_REQUIRED']) test(`current export error remains visible: ${detail}`,async t=>{
  const f=await fixture(t);f.fetch(async()=>({ok:false,json:async()=>({detail})}));await f.click();
  assert.match(document.body.textContent,detail==='COMPLETE_BACKUP_REQUIRED'?/contains retained receipts.*Complete backup and restore/:/SYNTHETIC current-company failure/);
  assert.equal(findButton().disabled,false);assert.equal(f.urls.length,0);
});
