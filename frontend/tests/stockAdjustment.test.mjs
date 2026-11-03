import test, {after} from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp, rm} from 'node:fs/promises';
import {resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
import {build} from 'esbuild';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
const temporary = await mkdtemp(resolve('node_modules/.stock-adjustment-test-'));
await build({entryPoints:['src/StockAdjustment.jsx'],outfile:resolve(temporary,'component.mjs'),bundle:true,jsx:'automatic',platform:'node',format:'esm',external:['react','react-dom','lucide-react']});
const Adjustment = (await import(pathToFileURL(resolve(temporary,'component.mjs')))).default;
after(() => rm(temporary,{recursive:true,force:true}));
test('stock adjustment explains physical-only zero value without promising a financial journal', () => {
  const markup = renderToStaticMarkup(React.createElement(Adjustment,{items:[{id:'synthetic',name:'Free sample',data:{unit:'pcs'}}],close(){},save(){}}));
  assert.match(markup,/zero-value adjustment changes counted stock only, with no financial journal/);
  assert.match(markup,/Nonzero values post an inventory loss or gain/);
  assert.match(markup,/min="0.001"/);
  assert.match(markup,/Adjustments cannot be backdated/);
});
