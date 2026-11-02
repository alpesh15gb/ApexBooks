const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');

function harness() {
  const jar = new Map();
  const writes = [];
  const document = {};
  Object.defineProperty(document, 'cookie', {
    get: () => [...jar].map(([name, value]) => `${name}=${value}`).join('; '),
    set: (value) => {
      writes.push(value);
      const pair = value.split(';')[0];
      const separator = pair.indexOf('=');
      const name = pair.slice(0, separator);
      if (value.includes('Max-Age=0')) jar.delete(name);
      else jar.set(name, pair.slice(separator + 1));
    },
  });
  const constants = {GUEST_CART_TOKEN: 'guest_cart_token', GUEST_CART_ID: 'guest_cart_id', IS_GUEST: 'is_guest'};
  const modules = {};
  function load(name) {
    if (name.endsWith('/constants')) return constants;
    if (modules[name]) return modules[name];
    const filename = path.join(__dirname, '../src/utils', name.endsWith('jwt-cookie') ? 'jwt-cookie.ts' : 'getCartToken.ts');
    const code = ts.transpileModule(fs.readFileSync(filename, 'utf8'), {compilerOptions: {module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022}}).outputText;
    const exports = {};
    vm.runInNewContext(code, {exports, require: load, document, window: {location: {protocol: 'https:'}}, console,
      btoa: (value) => Buffer.from(value, 'binary').toString('base64'), atob: (value) => Buffer.from(value, 'base64').toString('binary')});
    modules[name] = exports;
    return exports;
  }
  return {jar, writes, api: load('@/utils/getCartToken')};
}

test('adopts a replacement cart capability before the next checkout request', () => {
  const {api, writes} = harness();
  api.rememberGuestCart('inactive-order-session', 1);
  api.rememberGuestCart('authoritative-new-cart-session', 2);
  assert.equal(api.getCartToken(), 'authoritative-new-cart-session');
  assert.equal(api.getGuestCartId(), 2);
  assert.ok(writes.filter(value => value.startsWith('guest_cart_token=')).every(value => value.includes('SameSite=Lax') && value.includes('; Secure')));
});

test('completed guest checkout synchronously clears both identifiers', () => {
  const {api} = harness();
  api.rememberGuestCart('completed-cart-session', 8);
  api.clearCompletedGuestCart();
  assert.equal(api.getCartToken(), null);
  assert.equal(api.getGuestCartId(), null);
  api.rememberGuestCart('next-purchase-session', 9);
  assert.equal(api.getCartToken(), 'next-purchase-session');
});

test('guest rotation and cleanup preserve a signed-in customer identity', () => {
  const {api, jar} = harness();
  jar.set('is_guest', 'false');
  jar.set('guest_cart_token', 'synthetic-customer-session');
  api.rememberGuestCart('unrelated-guest-session', 42);
  api.clearCompletedGuestCart();
  assert.equal(api.getCartToken(), 'synthetic-customer-session');
  assert.equal(jar.get('is_guest'), 'false');
});
