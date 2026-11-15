import test from 'node:test';
import assert from 'node:assert/strict';
import {
  addLocations, addMake, addModel, draftChanged, draftFromSetup, effectiveCatalog, fitmentLabel, itemSearchText, itemSummary,
  locationNames, rangeNames, removeMake, removeModel, restoreMake, setupPayload, yearsLabel,
} from '../src/inventorySetup.js';

const defaults = [
  { make: 'Maruti Suzuki', type: 'car', models: ['800', 'Alto', 'Swift'] },
  { make: 'Hero MotoCorp', type: 'two_wheeler', models: ['Splendor', 'Passion'] },
];
const empty = () => ({ automobile_enabled: true, locations: [], vehicle_added: [], vehicle_hidden_makes: [], vehicle_hidden_models: [] });
const setup = { locations: [{ id: 'l1', name: 'Rack 1', active: true }, { id: 'l2', name: 'Shelf B', active: false }] };

test('number series are generated, bounded and validated', () => {
  assert.deepEqual(rangeNames(' Rack ', '1', '3').names, ['Rack 1', 'Rack 2', 'Rack 3']);
  assert.ok(rangeNames('', '1', '3').error);
  assert.ok(rangeNames('Rack', '5', '2').error);
  assert.ok(rangeNames('Rack', '1', '500').error);
  assert.ok(rangeNames('Rack', 'a', '3').error);
});

test('adding locations ignores duplicates in any case and keeps existing ids', () => {
  const draft = { ...empty(), locations: [{ id: 'l1', name: 'Rack 1', active: true }] };
  const result = addLocations(draft, ['rack 1', ' Rack 2 ', 'Rack  2']);
  assert.deepEqual(result.draft.locations.map(row => [row.id, row.name]), [['l1', 'Rack 1'], [null, 'Rack 2']]);
  assert.ok(addLocations(draft, ['RACK 1']).error);
  assert.ok(addLocations(draft, ['x'.repeat(41)]).error);
});

test('locations resolve to names for known ids only', () => {
  assert.deepEqual(locationNames(setup, ['l2', 'gone', 'l1']), ['Shelf B', 'Rack 1']);
  assert.deepEqual(locationNames(null, ['l1']), []);
});

test('the effective vehicle list is the built-in list minus hidden plus added', () => {
  let draft = empty();
  draft = addModel(defaults, draft, 'Maruti Suzuki', 'Swift Dzire Tour').draft;
  draft = addMake(defaults, draft, 'Local Coachworks', 'commercial').draft;
  draft = addModel(defaults, draft, 'Local Coachworks', 'Tipper').draft;
  draft = removeModel(defaults, draft, 'Maruti Suzuki', '800').draft;
  draft = removeMake(defaults, draft, 'Hero MotoCorp').draft;
  const catalog = effectiveCatalog(defaults, draft);
  const maruti = catalog.find(row => row.make === 'Maruti Suzuki');
  assert.deepEqual(maruti.models.map(row => row.name), ['Alto', 'Swift', 'Swift Dzire Tour']);
  assert.equal(maruti.models.find(row => row.name === 'Swift Dzire Tour').custom, true);
  assert.equal(catalog.find(row => row.make === 'Hero MotoCorp').hidden, true);
  assert.equal(catalog.find(row => row.make === 'Local Coachworks').custom, true);
  assert.deepEqual(draft.vehicle_hidden_models, [{ make: 'Maruti Suzuki', model: '800' }]);
});

test('edits that repeat something already listed are refused, and hiding then re-adding restores the original', () => {
  let draft = empty();
  assert.ok(addMake(defaults, draft, 'maruti suzuki', 'car').error);
  assert.ok(addModel(defaults, draft, 'Maruti Suzuki', 'swift').error);
  assert.ok(addMake(defaults, draft, '   ', 'car').error);
  draft = removeModel(defaults, draft, 'Maruti Suzuki', 'Alto').draft;
  draft = addModel(defaults, draft, 'Maruti Suzuki', 'alto').draft;
  assert.deepEqual(draft.vehicle_hidden_models, []);
  assert.deepEqual(draft.vehicle_added, []);
  draft = removeMake(defaults, draft, 'Hero MotoCorp').draft;
  assert.deepEqual(restoreMake(draft, 'hero motocorp').draft.vehicle_hidden_makes, []);
  assert.deepEqual(addMake(defaults, draft, 'Hero MotoCorp', 'car').draft.vehicle_hidden_makes, []);
});

test('removing a custom make or model removes it outright', () => {
  let draft = addModel(defaults, addMake(defaults, empty(), 'Local Coachworks', 'commercial').draft, 'Local Coachworks', 'Tipper').draft;
  draft = removeModel(defaults, draft, 'Local Coachworks', 'Tipper').draft;
  assert.deepEqual(draft.vehicle_added[0].models, []);
  draft = removeMake(defaults, draft, 'Local Coachworks').draft;
  assert.deepEqual(draft.vehicle_added, []);
  assert.deepEqual(draft.vehicle_hidden_makes, []);
});

test('the save payload leaves new locations without an id and detects real changes only', () => {
  const server = { version: 4, automobile_enabled: false, locations: [{ id: 'l1', name: 'Rack 1', active: true }], vehicle_added: [], vehicle_hidden_makes: [], vehicle_hidden_models: [] };
  const draft = draftFromSetup(server);
  assert.equal(draftChanged(server, draft), false);
  const edited = addLocations(draft, ['Rack 2']).draft;
  assert.equal(draftChanged(server, edited), true);
  assert.deepEqual(setupPayload(server.version, edited).locations, [{ id: 'l1', name: 'Rack 1', active: true }, { name: 'Rack 2', active: true }]);
  assert.equal(setupPayload(4, edited).version, 4);
});

test('items are described and found by location, part number, brand and fitment', () => {
  const record = { name: 'Brake pad', number: '', data: { hsn: '8708', barcode: '8901', location_ids: ['l1'], oem_number: '55810', part_brand: 'Bosch', part_grade: 'aftermarket',
    vehicle_fitment: [{ make: 'Maruti Suzuki', model: 'Swift', year_from: 2011, year_to: 2017 }, { make: 'Hyundai', model: '', year_from: null, year_to: null }] } };
  const summary = itemSummary(record, setup);
  assert.deepEqual(summary.locations, ['Rack 1']);
  assert.deepEqual(summary.fits, ['Maruti Suzuki Swift 2011–2017', 'Hyundai']);
  const text = itemSearchText(record, setup);
  for (const word of ['rack 1', '55810', 'bosch', 'aftermarket', 'swift', '2011', 'brake pad', '8901']) assert.ok(text.includes(word), word);
  assert.equal(itemSearchText({ name: 'Oil', data: {} }, null), 'oil');
});

test('year ranges read naturally', () => {
  assert.equal(yearsLabel(2011, 2017), '2011–2017');
  assert.equal(yearsLabel(2015, 2015), '2015');
  assert.equal(yearsLabel(2018, null), '2018 onwards');
  assert.equal(yearsLabel(null, 2012), 'up to 2012');
  assert.equal(fitmentLabel({ make: ' Tata ', model: 'Nexon', year_from: null, year_to: null }), 'Tata Nexon');
});
