import test from 'node:test';
import assert from 'node:assert/strict';
import { createPostingRequest } from '../src/postingRequest.js';
import { registerPostingRequest, hasPendingPostings } from '../src/postingRegistry.js';
test('registry blocks only live busy or unresolved operations and releases after recovery', async () => {
 const request=createPostingRequest(), other=createPostingRequest();
 const release=registerPostingRequest(request), releaseOther=registerPostingRequest(other);
 assert.equal(hasPendingPostings(),false);
 let calls=0, complete;
 const original=()=>++calls===1?new Promise((resolve,reject)=>{complete=reject;}):Promise.resolve('recovered');
 const first=request.run(original);assert.equal(hasPendingPostings(),true);
 complete(Object.assign(new Error('Timeout'),{status:408}));await assert.rejects(first);
 assert.equal(hasPendingPostings(),true);
 await request.run(()=>assert.fail('must recover original'));
 assert.equal(hasPendingPostings(),false);
 await assert.rejects(other.run(async()=>{throw Object.assign(new Error('Invalid'),{status:422});}));
 assert.equal(hasPendingPostings(),false);
 release();releaseOther();
});
