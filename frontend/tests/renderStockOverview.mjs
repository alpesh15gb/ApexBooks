// Invoked by tests/stock_overview_acceptance.py with actual synthetic API records.
import {build} from 'esbuild';
import {mkdtemp,rm} from 'node:fs/promises';
import {resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
const chunks=[];for await(const chunk of process.stdin)chunks.push(chunk);
const records=JSON.parse(Buffer.concat(chunks).toString());
const temp=await mkdtemp(resolve('node_modules/.stock-api-render-'));
try{await build({entryPoints:['src/TransactionDetail.jsx'],outfile:resolve(temp,'detail.mjs'),bundle:true,platform:'node',format:'esm',loader:{'.css':'empty'},external:['react','react-dom','lucide-react']});
 const Detail=(await import(pathToFileURL(resolve(temp,'detail.mjs')))).default;
 process.stdout.write(JSON.stringify(records.map(record=>renderToStaticMarkup(React.createElement(Detail,{record,records:[],company:{role:'viewer'},labels:{}})))));
}finally{await rm(temp,{recursive:true,force:true});}
