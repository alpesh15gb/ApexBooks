import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, rm } from 'node:fs/promises';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { build } from 'esbuild';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';

test('initial preference render describes loading rather than an invented session change', async()=>{
 const temporary=await mkdtemp(resolve('node_modules/.preference-initial-'));
 const previous=globalThis.localStorage;globalThis.localStorage={getItem:()=> 'synthetic'};
 try {
  const outfile=resolve(temporary,'component.mjs');
  await build({entryPoints:['src/DocumentLayoutPreference.jsx'],outfile,bundle:true,platform:'node',format:'esm',jsx:'automatic',external:['react']});
  const {default:Preference}=await import(pathToFileURL(outfile));
  const html=renderToStaticMarkup(React.createElement(Preference,{companyId:'synthetic',role:'owner',api:()=>{throw Error('effects must not run during initial render');}}));
  assert.match(html,/Loading document layout/);assert.doesNotMatch(html,/session changed|Retry document layout/);
 } finally {globalThis.localStorage=previous;await rm(temporary,{recursive:true,force:true});}
});
