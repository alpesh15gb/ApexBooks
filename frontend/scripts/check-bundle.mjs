import { readFileSync } from 'node:fs';
import { dirname, resolve, relative, isAbsolute } from 'node:path';
import { fileURLToPath } from 'node:url';
import { gzipSync } from 'node:zlib';

// Guard the actual shipping assets, including every statically imported chunk.
// Dynamic workspaces are measured separately and do not count as initial JS.
const directory = resolve(dirname(fileURLToPath(import.meta.url)), '../dist');
const manifest = JSON.parse(readFileSync(resolve(directory, '.vite/manifest.json'), 'utf8'));
const scripts = new Set(), styles = new Set(), visited = new Set();
function visit(key) {
  if (visited.has(key)) return;
  visited.add(key);
  const chunk = manifest[key];
  if (!chunk) throw new Error(`Build manifest is missing ${key}`);
  scripts.add(chunk.file);
  for (const css of chunk.css || []) styles.add(css);
  for (const dependency of chunk.imports || []) visit(dependency);
}
const entries = Object.entries(manifest).filter(([, chunk]) => chunk.isEntry);
if (!entries.length) throw new Error('Build manifest has no entry point');
for (const [key] of entries) visit(key);
function contents(file) {
  const path = resolve(directory, file);
  const within = relative(directory, path);
  if (within.startsWith('..') || isAbsolute(within)) throw new Error('Asset path escapes build directory');
  return readFileSync(path);
}
const compressed = files => [...files].reduce((sum, file) => sum + gzipSync(contents(file)).length, 0);
const result = {
  initialJavascriptGzipBytes: compressed(scripts),
  initialCssGzipBytes: compressed(styles),
  largestJavascriptChunkBytes: Math.max(...Object.values(manifest)
    .filter(chunk => chunk.file.endsWith('.js')).map(chunk => contents(chunk.file).length)),
};
const limits = { initialJavascriptGzipBytes: 150_000, initialCssGzipBytes: 45_000, largestJavascriptChunkBytes: 500_000 };
for (const [key, value] of Object.entries(result)) {
  if (value > limits[key]) throw new Error(`${key}: ${value} exceeds the ${limits[key]} byte budget`);
}
console.log('Web bundle budgets passed:', JSON.stringify(result));
