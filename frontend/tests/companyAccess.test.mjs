import test from 'node:test';import assert from 'node:assert/strict';import {JSDOM} from 'jsdom';
const dom=new JSDOM('',{url:'http://localhost'});Object.assign(globalThis,{window:dom.window,localStorage:dom.window.localStorage});localStorage.token='synthetic';
const access=await import('../src/companyAccess.js');const {sessionFetch}=await import('../src/sessionScope.js');const reply=(status,value)=>({status,ok:status<400,json:async()=>value});
test('company denial locks current missing membership and rejects stale bodies after recovery',async()=>{
 access.setActiveCompanyAccess('a');let release;let denied=0;window.addEventListener('apex-company-access-lost',()=>denied++);
 globalThis.fetch=async path=>path==='/api/companies'?reply(200,[]):path.endsWith('/records')?reply(404,{}):{...reply(200,{}),blob:()=>new Promise(resolve=>release=resolve)};
 const download=await sessionFetch('/api/companies/a/documents/doc.pdf');const pending=download.blob();
 await assert.rejects(sessionFetch('/api/companies/a/records'),e=>e.companyAccess&&e.status===404);assert.equal(denied,1);
 await assert.rejects(sessionFetch('/api/companies/a/records'),e=>e.status===403);
 access.allowCompanyRecovery('a');release(new Blob(['synthetic']));await assert.rejects(pending,e=>e.companyAccess&&e.status===0);
});
test('resource 404 and owner-only 403 do not revoke an authorized viewer',async()=>{
 access.setActiveCompanyAccess('b');globalThis.fetch=async path=>path==='/api/companies'?reply(200,[{id:'b',role:'viewer'}]):reply(path.endsWith('/members')?403:404,{});
 assert.equal((await sessionFetch('/api/companies/b/members')).status,403);assert.equal((await sessionFetch('/api/companies/b/records/missing')).status,404);
});
test('old company denial cannot lock current company',async()=>{
 access.setActiveCompanyAccess('c');let finish;globalThis.fetch=()=>new Promise(resolve=>finish=resolve);
 const pending=sessionFetch('/api/companies/c/records');access.setActiveCompanyAccess('d');finish(reply(404,{}));await assert.rejects(pending,e=>e.status===0);
 assert.doesNotThrow(()=>access.captureCompanyAccess('/api/companies/d/records'));
});
test('pending stream cannot expose bytes after denial and recovery',async()=>{
 access.setActiveCompanyAccess('stream');let controller,cancelled=false;
 globalThis.fetch=async()=>new Response(new ReadableStream({start(value){controller=value;},cancel(){cancelled=true;}}));
 const response=await sessionFetch('/api/companies/stream/attachments/a/download');const read=response.body.getReader().read();
 access.blockCompanyAccess('stream');access.allowCompanyRecovery('stream');controller.enqueue(new Uint8Array([1,2]));
 await assert.rejects(read,e=>e.companyAccess&&e.status===0);assert.equal(cancelled,true);
});
test('unverifiable membership locks current company explicitly',async()=>{
 access.setActiveCompanyAccess('unknown');globalThis.fetch=async path=>path==='/api/companies'?reply(503,{}):reply(404,{});
 await assert.rejects(sessionFetch('/api/companies/unknown/records'),e=>e.companyAccess&&e.status===404);
 assert.throws(()=>access.captureCompanyAccess('/api/companies/unknown/records'),e=>e.status===403);
});
