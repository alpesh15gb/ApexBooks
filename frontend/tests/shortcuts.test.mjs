import test from 'node:test';
import assert from 'node:assert/strict';
import { SHORTCUTS, isHelpKey, shortcutFor } from '../src/shortcuts.js';

test('Alt shortcuts map to actions and never fire while a dialog is open', () => {
  assert.deepEqual(shortcutFor({ altKey: true, key: 'N' }), SHORTCUTS.find(s => s.target === 'sales_invoice' && s.action === 'create'));
  assert.equal(shortcutFor({ altKey: true, key: 'd' }).target, 'day_book');
  assert.equal(shortcutFor({ altKey: true, key: 'n' }, true), null);
  assert.equal(shortcutFor({ altKey: true, ctrlKey: true, key: 'n' }), null);
  assert.equal(shortcutFor({ key: 'n' }), null);
  assert.equal(new Set(SHORTCUTS.map(s => s.key)).size, SHORTCUTS.length);
});

test('? opens help except while typing', () => {
  assert.equal(isHelpKey({ key: '?', target: { tagName: 'BODY' } }), true);
  assert.equal(isHelpKey({ key: '?', target: { tagName: 'INPUT' } }), false);
});
