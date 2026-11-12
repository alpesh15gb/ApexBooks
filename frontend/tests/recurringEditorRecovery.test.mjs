import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
const source=await readFile(new URL('../src/main.jsx',import.meta.url),'utf8');
const body=source.split('  async function beginEdit(record) {')[1].split('\n  async function beginConversion')[0];
const AsyncFunction=Object.getPrototypeOf(async function(){}).constructor;
for(const mode of ['success','failure','viewer','stale','pending'])test(`actual App beginEdit reports editor opening outcome: ${mode}`,async()=>{
 let calls=0,opened=0,errors=[];
 const names=['postingNavigationBlocked','company','editorRequests','api','companyId','rememberEditorContext','setEditingMaster','setEditingDraft','setConversionSource','setRelatedSource','setDraftSeed','setPage','setEditorCycle','setModal','setError','record'];
 const fn=new AsyncFunction(...names,body.slice(0,body.lastIndexOf('}')));
 const result=await fn(()=>mode==='pending',{role:mode==='viewer'?'viewer':'owner'},{current:{latest:()=>()=>mode!=='stale'}},async()=>{calls++;if(mode==='failure')throw Error('Editor read failed');return{id:'saved'};},'synthetic',()=>{},()=>{},()=>{},()=>{},()=>{},()=>{},()=>{},()=>{},()=>{opened++;},message=>errors.push(message),{id:'saved',kind:'sales_order'});
 assert.equal(result,mode==='success');assert.equal(opened,mode==='success'?1:0);assert.equal(calls,['viewer','pending'].includes(mode)?0:1);assert.deepEqual(errors,mode==='failure'?['Editor read failed']:[]);
});
