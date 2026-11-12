import test from 'node:test';
import assert from 'node:assert/strict';
import {refreshRestoredCompany} from '../src/restoreNavigation.js';
import {createRequestScope} from '../src/requestScope.js';
for(const outcome of ['success','failure'])for(const transition of ['current','company','away-back','role','unmount','access','session'])test(`restored navigation ${outcome}/${transition}`,async()=>{
 const scope=createRequestScope('a:owner');let valid=true,finish,fail,applied=[];
 const request=refreshRestoredCompany({id:'restored',current:scope.capture(),verify:()=>{if(!valid)throw Error('obsolete');},readCompanies:()=>new Promise((r,j)=>{finish=r;fail=j;}),apply:(...args)=>applied.push(args)});
 if(['company','role','unmount'].includes(transition))scope.setContext(transition);
 if(transition==='away-back'){scope.setContext('b:owner');scope.setContext('a:owner');}
 if(['access','session'].includes(transition))valid=false;
 if(outcome==='success')finish([{id:'restored'}]);else fail(Error('CURRENT READ FAILURE'));
 if(transition==='current'&&outcome==='failure')await assert.rejects(request,/CURRENT READ FAILURE/);else assert.equal(await request,transition==='current');
 assert.equal(applied.length,transition==='current'&&outcome==='success'?1:0);
});
test('confirmed restore absent from refreshed list does not select missing company',async()=>{
 let applied=false;await assert.rejects(refreshRestoredCompany({id:'restored',current:()=>true,verify:()=>{},readCompanies:async()=>[{id:'a'}],apply:()=>applied=true}),/do not restore again/);assert.equal(applied,false);
});
