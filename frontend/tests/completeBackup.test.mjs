import test,{after} from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,rm} from 'node:fs/promises';
import {resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
import {build} from 'esbuild';
import {JSDOM} from 'jsdom';
import React,{act} from 'react';
import {sha256Bytes} from '../src/backupChunks.js';
const temp=await mkdtemp(resolve('node_modules/.complete-backup-tests-'));
await build({entryPoints:['src/CompleteBackup.jsx'],outfile:resolve(temp,'component.mjs'),bundle:true,platform:'node',format:'esm',external:['react','react-dom','lucide-react']});
const Component=(await import(pathToFileURL(resolve(temp,'component.mjs')))).default;
const dom=new JSDOM('<div id="root"></div>',{url:'http://localhost'});
Object.assign(globalThis,{window:dom.window,document:dom.window.document,IS_REACT_ACT_ENVIRONMENT:true});
const {createRoot}=await import('react-dom/client');
after(async()=>{dom.window.close();await rm(temp,{recursive:true,force:true});});
const zip=new Uint8Array([80,75,3,4,1,2,3,4]), hash=await sha256Bytes(zip), id='11111111-1111-4111-8111-111111111111';
const job={upload_id:id,export_id:id,state:'uploading',byte_count:zip.length,sha256:hash,chunk_size:524288,chunk_count:1,chunks:[],expires_at:'2026-11-04',target_company_name:'Destination books'};
const preview={digest:hash,company_name:'Original legal name',counts:{records:1},attachment_count:1};
const find=text=>[...document.querySelectorAll('button')].find(b=>b.textContent.includes(text));
function field(label){return [...document.querySelectorAll('label')].find(l=>l.textContent.startsWith(label))?.querySelector('input');}
async function type(label,value){await act(async()=>{const input=field(label);Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set.call(input,value);input.dispatchEvent(new window.Event('input',{bubbles:true}));input.dispatchEvent(new window.Event('change',{bubbles:true}));});}
async function choose(bytes=zip){await act(async()=>{const input=field('Backup file');const blob=new Blob([bytes]);Object.defineProperty(blob,'name',{value:'synthetic.zip'});Object.defineProperty(input,'files',{value:[blob],configurable:true});input.dispatchEvent(new window.Event('change',{bubbles:true}));});}
async function until(predicate){for(let n=0;n<200;n++){if(predicate())return;await act(async()=>{await new Promise(resolve=>setTimeout(resolve,10));});}assert.fail('Timed out waiting for component operation');}
async function mount(api,extra={}){const root=createRoot(document.getElementById('root'));await act(async()=>root.render(React.createElement(Component,{companyId:'c1',api,...extra})));return root;}
test('unknown snapshot preparation retries original request and blocks upload operation',async()=>{
 const writes=[];const root=await mount(async(path,options)=>{writes.push({path,...options});if(writes.length===1)throw Error('Response lost');return job;});
 await act(async()=>find('Prepare complete').click());assert.ok(find('Retry original preparation'));assert.equal(find('Retry original request').disabled,true);
 await act(async()=>find('Retry original preparation').click());assert.deepEqual(writes[0],writes[1]);assert.equal(writes.length,2);
 await act(async()=>root.unmount());
});

test('backup transfer operations start once even before the busy state renders',async()=>{
 let calls=0,finish;
 const root=await mount(async()=>{calls++;return new Promise(resolve=>{finish=resolve;});});
 await act(async()=>{find('Find my active transfers').click();find('Find my active transfers').click();});
 assert.equal(calls,1);
 await act(async()=>finish({transfers:[]}));
 assert.match(document.body.textContent,/No retained unexpired transfers/);
 await act(async()=>root.unmount());
});
test('restore creation and commit lost responses retry same operation; validation never auto-commits',async()=>{
 const writes=[];let creates=0,commits=0,restored;
 const root=await mount(async(path,options)=>{
  writes.push({path,...options});
  if(path==='/backups/uploads'){if(++creates===1)throw Error('Lost create response');return job;}
  if(path.endsWith('/chunks/0'))return{size_bytes:zip.length,sha256:hash};
  if(path.endsWith('/preview'))return preview;
  if(path.endsWith('/commit')){if(++commits===1)throw Error('Lost commit response');return{company_id:'new-company'};}
  throw Error('Unexpected '+path);
 },{onRestored:id=>{restored=id;}});
 await type('New company name','Destination books');await choose();
 await act(async()=>find('Upload and validate').click());await until(()=>creates===1&&!find('Upload and validate'));
 assert.equal(creates,1);assert.equal(find('Retry original preparation').disabled,true);
 await act(async()=>find('Retry original request').click());await until(()=>!!find('Restore as separate company'));assert.equal(creates,2);assert.equal(commits,0);assert.match(document.body.textContent,/Validated:/);
 const createCalls=writes.filter(w=>w.path==='/backups/uploads');assert.deepEqual(createCalls[0],createCalls[1]);assert.equal(JSON.parse(createCalls[0].body).company_name,'Destination books');
 await act(async()=>find('Restore as separate company').click());assert.equal(commits,1);assert.equal(find('Retry original request').disabled,true);
 await act(async()=>find('Retry original restore').click());assert.equal(commits,2);assert.equal(restored,'new-company');
 const commitCalls=writes.filter(w=>w.path.endsWith('/commit'));assert.deepEqual(commitCalls[0],commitCalls[1]);
 assert.ok(writes.every(w=>!JSON.stringify(w).includes('password')));
 await act(async()=>root.unmount());
});
test('resumed sealed upload retains destination name and requires explicit restore',async()=>{
 let commits=0;const root=await mount(async(path)=>{if(path.endsWith('/commit')){commits++;return{};}return{...job,...preview,state:'sealed'};});
 await type('Transfer ID',id);await act(async()=>find('Recover transfer').click());
 assert.equal(field('New company name').value,'Destination books');assert.equal(field('New company name').disabled,true);assert.equal(commits,0);assert.ok(find('Restore as separate company'));
 await act(async()=>root.unmount());
});
test('encrypted export over8MiB refuses before any chunk read; no plaintext fallback',async()=>{
 const paths=[];const root=await mount(async(path)=>{paths.push(path);return{...job,byte_count:9*1024*1024,chunk_count:18};});
 await type('Backup password','Synthetic-password-only');await act(async()=>find('Prepare complete').click());await act(async()=>find('Download complete').click());
 assert.equal(paths.length,1);assert.match(document.body.textContent,/larger complete archive/);
 await act(async()=>root.unmount());
});
test('plain restore above16MiB refuses before reading file or creating stage',async()=>{
 const paths=[];const root=await mount(async path=>{paths.push(path);return job;});await type('New company name','Destination books');
 await act(async()=>{const input=field('Backup file');Object.defineProperty(input,'files',{value:[{size:16*1024*1024+1,arrayBuffer:()=>assert.fail('must not read'),slice:()=>assert.fail('must not read')}],configurable:true});input.dispatchEvent(new window.Event('change',{bubbles:true}));});
 await act(async()=>find('Upload and validate').click());assert.equal(paths.length,0);assert.match(document.body.textContent,/exceeds the browser limit/);await act(async()=>root.unmount());
});
test('stopping a chunk transfer never previews or commits; retained upload remains resumable',async()=>{
 const paths=[];let first=true;
 const root=await mount(async(path,options)=>{
  paths.push(path);
  if(path==='/backups/uploads')return job;
  if(path===`/backups/uploads/${id}`)return job;
  if(path.endsWith('/chunks/0')){if(first){first=false;return new Promise((_,reject)=>options.signal.addEventListener('abort',()=>reject(new DOMException('Stopped','AbortError')),{once:true}));}return{size_bytes:zip.length,sha256:hash};}
  if(path.endsWith('/preview'))return preview;
  assert.fail('Unexpected '+path);
 });
 await type('New company name','Destination books');await choose();
 await act(async()=>find('Upload and validate').click());await until(()=>paths.some(path=>path.endsWith('/chunks/0')));
 assert.ok(find('Stop transfer'));await act(async()=>find('Stop transfer').click());
 assert.ok(paths.every(path=>!path.endsWith('/preview')&&!path.endsWith('/commit')));assert.match(document.body.textContent,/Transfer stopped/);
 await act(async()=>find('Resume and validate original file').click());await until(()=>!!find('Restore as separate company'));
 assert.ok(find('Restore as separate company'));assert.ok(paths.every(path=>!path.endsWith('/commit')));
 await act(async()=>root.unmount());
});
test('encrypted restore decrypts locally and sends original plaintext checksum, never password',async()=>{
 const {encryptPortableBackup}=await import('../src/portableBackup.js');const secret='Synthetic-private-password';
 const encrypted=await encryptPortableBackup(zip,secret), calls=[];
 const root=await mount(async(path,options)=>{calls.push({path,...options});if(path==='/backups/uploads')return job;if(path.endsWith('/chunks/0'))return{size_bytes:zip.length,sha256:hash};if(path.endsWith('/preview'))return preview;assert.fail(path);});
 await type('Backup password',secret);await type('New company name','Destination books');await choose(encrypted);
 await act(async()=>find('Upload and validate').click());await until(()=>!!find('Restore as separate company'));
 assert.ok(find('Restore as separate company'));assert.equal(JSON.parse(calls[0].body).sha256,hash);assert.ok(!JSON.stringify(calls).includes(secret));assert.deepEqual(calls.find(call=>call.path.endsWith('/chunks/0')).body,zip);
 await act(async()=>root.unmount());
});
test('stopping while reading the local file does not create a staging job afterward',async()=>{
 let release,creates=0;const root=await mount(async(path)=>{if(path==='/backups/uploads'){creates++;return job;}return{};});
 await type('New company name','Destination books');
 await act(async()=>{const input=field('Backup file'),blob=new Blob([zip]);blob.arrayBuffer=()=>new Promise(resolve=>{release=resolve;});Object.defineProperty(input,'files',{value:[blob],configurable:true});input.dispatchEvent(new window.Event('change',{bubbles:true}));});
 await act(async()=>{find('Upload and validate').click();await new Promise(resolve=>setTimeout(resolve,15));});
 await act(async()=>find('Stop transfer').click());
 await act(async()=>{release(zip.buffer);await new Promise(resolve=>setTimeout(resolve,30));});
 await act(async()=>root.unmount());assert.equal(creates,0,'cancelled local preparation must not create server stage');
});
test('reopened lost creation recovers existing stage by listing, not a second prepare POST',async()=>{
 let creates=0;const paths=[];
 const api=async(path,options)=>{
  paths.push({path,method:options?.method || 'GET'});
  if(path==='/backups/uploads'){creates++;throw Error('Original response lost after stage creation');}
  if(path==='/backups/transfers')return{transfers:[{...job,direction:'import'}]};
  if(path===`/backups/uploads/${id}`)return job;
  if(path.endsWith('/chunks/0'))return{sha256:hash,size_bytes:zip.length};
  if(path.endsWith('/preview'))return preview;
  assert.fail(path);
 };
 let root=await mount(api);await type('New company name','Destination books');await choose();
 await act(async()=>find('Upload and validate').click());await until(()=>creates===1&&!find('Upload and validate'));
 // Simulate a forced tab close/reopen, not the normal guarded navigation path.
 await act(async()=>root.unmount());root=await mount(api);
 assert.equal(paths.filter(row=>row.path==='/backups/transfers').length,0,'no startup listing overhead');
 await act(async()=>find('Find my active transfers').click());await act(async()=>find('Recover this transfer').click());
 assert.equal(field('New company name').value,'Destination books');assert.equal(field('New company name').disabled,true);
 await choose();await act(async()=>find('Resume and validate original file').click());await until(()=>!!find('Restore as separate company'));
 assert.equal(creates,1);assert.ok(paths.every(row=>!row.path.endsWith('/commit')));
 await act(async()=>root.unmount());
});
test('transfer selector refuses another company export and recovers sealed import without posting',async()=>{
 const paths=[];const root=await mount(async(path,options)=>{paths.push({path,...options});return{transfers:[{...job,export_id:'22222222-2222-4222-8222-222222222222',direction:'export',source_company_id:'other-company'},{...job,...preview,export_id:undefined,direction:'import',state:'sealed'}]};});
 await act(async()=>find('Find my active transfers').click());
 const recover=[...document.querySelectorAll('button')].filter(button=>button.textContent==='Recover this transfer');assert.equal(recover.length,2);assert.equal(recover[0].disabled,true);assert.equal(recover[1].disabled,false);
 await act(async()=>recover[1].click());assert.ok(find('Restore as separate company'));assert.equal(field('New company name').value,'Destination books');assert.equal(paths.length,1);assert.equal(paths[0].method,undefined);
 await act(async()=>root.unmount());
});
test('reopened lost commit recovers canonical completed company without reposting restore',async()=>{
 const paths=[];let opened='';const root=await mount(async(path,options)=>{paths.push({path,...options});assert.equal(path,'/backups/transfers');return{transfers:[{...job,...preview,state:'restored',direction:'import',company_id:'canonical-restored-company'}]};},{onRestored:value=>{opened=value;}});
 await act(async()=>find('Find my active transfers').click());await act(async()=>find('Recover completed result').click());
 assert.ok(find('Open restored company'));assert.equal(opened,'');assert.equal(find('Restore as separate company'),undefined);
 await act(async()=>find('Open restored company').click());assert.equal(opened,'canonical-restored-company');assert.equal(paths.length,1);assert.ok(paths.every(row=>!row.path.endsWith('/commit')));
 await act(async()=>root.unmount());
});
