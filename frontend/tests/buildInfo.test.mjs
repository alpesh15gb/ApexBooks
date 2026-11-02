import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {WEB_VERSION,normalizedBuildRevision} from '../src/buildInfo.js';
test('build identity is explicit full SHA or unknown; package and displayed versions agree',async()=>{
 const metadata=JSON.parse(await readFile(new URL('../package.json',import.meta.url),'utf8'));assert.equal(WEB_VERSION,metadata.version);
 for(const value of [undefined,null,'','HEAD','abc1234','a'.repeat(41),'a'.repeat(40)+';command'])assert.equal(normalizedBuildRevision(value),'unknown');
 assert.equal(normalizedBuildRevision(' '+ 'A'.repeat(40)+' '),'a'.repeat(40));assert.equal(normalizedBuildRevision('b'.repeat(64)),'b'.repeat(64));
});
