"""Item locations, the Automobile module and the owner-editable vehicle list."""
import base64
import io
import json
import unittest
from uuid import uuid4

from openpyxl import load_workbook

import test_completion
from vehicle_catalog import CATALOG, VEHICLE_TYPES


class InventorySetupTest(unittest.TestCase):
    def setUp(self):
        self.client, self.headers, self.base = test_completion.CompletionTest.client_context(self)
        self.setup_url = self.base + '/inventory-setup'

    def get_setup(self):
        response = self.client.get(self.setup_url, headers=self.headers)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def put_setup(self, current=None, status=200, **changes):
        current = current or self.get_setup()
        body = {'version': current['version'], 'automobile_enabled': current['automobile_enabled'],
                'locations': [{'id': row['id'], 'name': row['name'], 'active': row['active']} for row in current['locations']],
                'vehicle_added': current['vehicle_added'], 'vehicle_hidden_makes': current['vehicle_hidden_makes'],
                'vehicle_hidden_models': current['vehicle_hidden_models'], **changes}
        response = self.client.put(self.setup_url, headers=self.headers, json=body)
        self.assertEqual(response.status_code, status, response.text)
        return response.json()

    def item(self, name='Brake pad', status=200, **data):
        response = self.client.post(self.base + '/records', headers={**self.headers, 'Idempotency-Key': uuid4().hex},
                                    json={'kind': 'item', 'name': name, 'date': '2026-04-01', 'data': data})
        self.assertEqual(response.status_code, status, response.text)
        return response.json()

    def update_item(self, record, status=200, **data):
        body = {'name': record['name'], 'hsn': '', 'unit': 'Pcs', 'sale_rate': '100', 'purchase_rate': '60', 'gst_rate': '18',
                'track_stock': False, 'item_type': 'goods', 'tax_treatment': 'taxable', **data}
        response = self.client.put(self.base + '/masters/' + record['id'], headers=self.headers, json=body)
        self.assertEqual(response.status_code, status, response.text)
        return response.json()

    def test_fresh_company_has_no_locations_and_the_automobile_module_is_off_with_a_full_catalogue(self):
        setup = self.get_setup()
        self.assertEqual((setup['version'], setup['automobile_enabled'], setup['locations']), (0, False, []))
        makes = {row['make']: row for row in setup['vehicle_options']}
        self.assertGreaterEqual(len(makes), 80)
        self.assertGreaterEqual(sum(len(row['models']) for row in makes.values()), 800)
        for name in ('Maruti Suzuki', 'Hero MotoCorp', 'Tata Commercial', 'Bajaj Three-Wheelers', 'Mahindra', 'Royal Enfield'):
            self.assertIn(name, makes)
        self.assertEqual(set(setup['vehicle_types']), set(VEHICLE_TYPES))
        self.assertTrue(all(row['type'] in VEHICLE_TYPES for row in makes.values()))
        self.assertIn('Swift', [model['name'] for model in makes['Maruti Suzuki']['models']])

    def test_default_catalogue_is_clean(self):
        names = [entry['make'].casefold() for entry in CATALOG]
        self.assertEqual(len(names), len(set(names)))
        for entry in CATALOG:
            models = [model.casefold() for model in entry['models']]
            self.assertEqual(len(models), len(set(models)), entry['make'])
            self.assertTrue(models, entry['make'])

    def test_owner_maps_locations_and_can_rename_archive_and_remove_unused_ones(self):
        saved = self.put_setup(locations=[{'name': 'Rack 1'}, {'name': 'Rack 2'}, {'name': ' Counter   drawer '}])
        self.assertEqual([row['name'] for row in saved['locations']], ['Rack 1', 'Rack 2', 'Counter drawer'])
        self.assertEqual(saved['version'], 1)
        ids = [row['id'] for row in saved['locations']]
        self.assertEqual(len(set(ids)), 3)
        renamed = self.put_setup(saved, locations=[{'id': ids[0], 'name': 'Rack A'}, {'id': ids[1], 'name': 'Rack 2', 'active': False},
                                                    {'id': ids[2], 'name': 'Counter drawer'}])
        self.assertEqual([row['id'] for row in renamed['locations']], ids)
        self.assertEqual(renamed['locations'][1]['active'], False)
        removed = self.put_setup(renamed, locations=[{'id': ids[0], 'name': 'Rack A'}, {'id': ids[1], 'name': 'Rack 2', 'active': False}])
        self.assertEqual(len(removed['locations']), 2)

    def test_location_names_must_be_unique_and_ids_must_exist_and_stale_saves_conflict(self):
        saved = self.put_setup(locations=[{'name': 'Rack 1'}])
        self.put_setup(saved, status=422, locations=[{'name': 'Rack 1'}, {'name': 'rack 1'}])
        self.put_setup(saved, status=422, locations=[{'id': 'loc-forged', 'name': 'Other'}])
        self.put_setup(saved, status=422, locations=[{'id': saved['locations'][0]['id'], 'name': '   '}])
        self.put_setup(saved, status=409, locations=[{'id': saved['locations'][0]['id'], 'name': 'Rack 9'}], version=0)
        self.assertEqual(self.get_setup()['locations'][0]['name'], 'Rack 1')

    def test_repeating_an_existing_location_id_does_not_change_the_saved_location(self):
        saved = self.put_setup(locations=[{'name': 'Rack 1'}])
        location_id = saved['locations'][0]['id']
        self.put_setup(saved, status=422, locations=[
            {'id': location_id, 'name': 'Upper shelf'},
            {'id': location_id, 'name': 'Lower shelf'},
        ])
        self.assertEqual(self.get_setup()['locations'], saved['locations'])
        self.assertEqual(self.get_setup()['version'], saved['version'])

    def test_vehicle_catalog_names_must_not_be_blank_after_normalization(self):
        self.put_setup(status=422, vehicle_added=[{'make': '   ', 'models': ['Local model']}])
        self.put_setup(status=422, vehicle_hidden_models=[{'make': 'Toyota', 'model': '   '}])
        self.assertEqual(self.get_setup()['version'], 0)

    def test_only_the_owner_can_change_setup_but_editors_can_read_it(self):
        editor = {'email': 'editor-' + uuid4().hex + '@example.invalid', 'password': 'test-only-strong-password'}
        self.client.post('/api/auth/register', json=editor)
        token = self.client.post('/api/auth/login', json=editor).json()['token']
        editor_headers = {'Authorization': 'Bearer ' + token}
        self.client.post(self.base + '/members', headers=self.headers, json={'email': editor['email'], 'role': 'editor'}).raise_for_status()
        self.assertEqual(self.client.get(self.setup_url, headers=editor_headers).status_code, 200)
        denied = self.client.put(self.setup_url, headers=editor_headers, json={'version': 0, 'automobile_enabled': True})
        self.assertEqual(denied.status_code, 403, denied.text)
        self.assertFalse(self.get_setup()['automobile_enabled'])

    def test_items_can_sit_in_several_locations_and_old_clients_do_not_erase_them(self):
        saved = self.put_setup(locations=[{'name': 'Rack 1'}, {'name': 'Rack 2'}])
        first, second = [row['id'] for row in saved['locations']]
        item = self.item(location_ids=[first, second, first])
        self.assertEqual(item['data']['location_ids'], [first, second])
        # An older client that never sends location_ids must not clear them.
        self.update_item(item, sale_rate='120')
        stored = next(row for row in self.client.get(self.base + '/records', headers=self.headers).json() if row['id'] == item['id'])
        self.assertEqual(stored['data']['location_ids'], [first, second])
        self.assertEqual(stored['data']['sale_rate'], '120')
        cleared = self.update_item(item, location_ids=[])
        self.assertEqual(cleared['data']['location_ids'], [])

    def test_items_reject_unknown_or_too_many_or_newly_archived_locations(self):
        saved = self.put_setup(locations=[{'name': f'Rack {number}'} for number in range(1, 8)])
        ids = [row['id'] for row in saved['locations']]
        self.item(name='Ghost', status=422, location_ids=['loc-forged'])
        self.item(name='Crowded', status=422, location_ids=ids[:6])
        item = self.item(name='Pad', location_ids=[ids[0]])
        archived = self.put_setup(saved, locations=[{'id': ids[0], 'name': 'Rack 1', 'active': False}] +
                                  [{'id': i, 'name': f'Rack {n}'} for n, i in enumerate(ids[1:], 2)])
        self.update_item(item, status=422, location_ids=[ids[0], ids[1], ids[1] + 'x'])
        self.update_item(item, status=200, location_ids=[ids[0]])  # keeping an archived location it already had is fine
        self.item(name='Fresh', status=422, location_ids=[archived['locations'][0]['id']])

    def test_a_location_that_items_use_cannot_be_removed_only_archived(self):
        saved = self.put_setup(locations=[{'name': 'Rack 1'}, {'name': 'Rack 2'}])
        first = saved['locations'][0]['id']
        self.item(location_ids=[first])
        refused = self.put_setup(saved, status=409, locations=[{'id': saved['locations'][1]['id'], 'name': 'Rack 2'}])
        self.assertIn('used by 1 item', refused['detail'])

    def test_vehicle_details_need_the_automobile_module_and_are_kept_when_it_is_switched_off(self):
        fit = [{'make': 'Maruti Suzuki', 'model': 'Swift', 'year_from': 2011, 'year_to': 2017}, {'make': '  Hyundai ', 'model': 'i20'}]
        self.item(name='Early', status=422, vehicle_fitment=fit)
        self.item(name='Early OEM', status=422, oem_number='ABC-123')
        self.put_setup(automobile_enabled=True)
        item = self.item(name='Pad', vehicle_fitment=fit, oem_number=' 55810  M68K00 ', part_brand='Bosch', part_grade='aftermarket')
        self.assertEqual(item['data']['oem_number'], '55810 M68K00')
        self.assertEqual(item['data']['vehicle_fitment'][1], {'make': 'Hyundai', 'model': 'i20', 'year_from': None, 'year_to': None})
        self.put_setup(automobile_enabled=False)
        # Hidden, not deleted; an old client that omits the fields leaves them alone; real changes are refused.
        self.update_item(item, sale_rate='130')
        stored = next(row for row in self.client.get(self.base + '/records', headers=self.headers).json() if row['id'] == item['id'])
        self.assertEqual(stored['data']['oem_number'], '55810 M68K00')
        self.update_item(item, status=422, oem_number='CHANGED')
        self.update_item(item, status=200, oem_number='55810 M68K00')

    def test_bad_fitment_is_refused(self):
        self.put_setup(automobile_enabled=True)
        self.item(name='Backwards', status=422, vehicle_fitment=[{'make': 'Tata Motors', 'model': 'Nexon', 'year_from': 2020, 'year_to': 2018}])
        self.item(name='No make', status=422, vehicle_fitment=[{'make': '   ', 'model': 'X'}])
        self.item(name='Weird grade', status=422, part_grade='stolen')
        self.item(name='Too many', status=422, vehicle_fitment=[{'make': 'Kia', 'model': str(n)} for n in range(61)])

    def test_parties_cannot_carry_locations_or_vehicle_details(self):
        saved = self.put_setup(automobile_enabled=True, locations=[{'name': 'Rack 1'}])
        response = self.client.post(self.base + '/records', headers={**self.headers, 'Idempotency-Key': uuid4().hex},
                                    json={'kind': 'party', 'name': 'Buyer', 'date': '2026-04-01', 'data': {'oem_number': 'X'}})
        self.assertEqual(response.status_code, 422, response.text)
        response = self.client.post(self.base + '/records', headers={**self.headers, 'Idempotency-Key': uuid4().hex},
                                    json={'kind': 'party', 'name': 'Buyer 2', 'date': '2026-04-01',
                                          'data': {'location_ids': [saved['locations'][0]['id']]}})
        self.assertEqual(response.status_code, 422, response.text)

    def test_owner_can_add_and_hide_makes_and_models_without_touching_the_default_list(self):
        setup = self.put_setup(
            vehicle_added=[{'make': 'Maruti Suzuki', 'type': 'car', 'models': ['Swift', 'Swift Dzire Tour', 'swift dzire tour']},
                           {'make': 'Local Coachworks', 'type': 'commercial', 'models': ['Mini Bus', 'Tipper']}],
            vehicle_hidden_makes=['Opel', 'Ferrari'], vehicle_hidden_models=[{'make': 'Maruti Suzuki', 'model': '800'}])
        makes = {row['make']: row for row in setup['vehicle_options']}
        self.assertNotIn('Ferrari', makes)
        maruti = {model['name']: model for model in makes['Maruti Suzuki']['models']}
        self.assertNotIn('800', maruti)
        self.assertTrue(maruti['Swift Dzire Tour']['custom'])
        self.assertFalse(maruti['Swift']['custom'])
        self.assertEqual(sum(1 for name in maruti if name.casefold() == 'swift dzire tour'), 1)
        self.assertTrue(makes['Local Coachworks']['custom'])
        self.assertEqual([model['name'] for model in makes['Local Coachworks']['models']], ['Mini Bus', 'Tipper'])
        # The built-in catalogue itself is untouched for other companies.
        other_client, other_headers, other_base = test_completion.CompletionTest.client_context(self)
        other = other_client.get(other_base + '/inventory-setup', headers=other_headers).json()
        self.assertIn('Ferrari', [row['make'] for row in other['vehicle_options']])

    def export_text(self):
        response = self.client.get(self.base + '/masters/export.xlsx', headers=self.headers, params={'kind': 'item'})
        self.assertEqual(response.status_code, 200, response.text[:200])
        sheet = load_workbook(io.BytesIO(response.content)).active
        return chr(10).join(' | '.join(str(cell) for cell in row if cell is not None) for row in sheet.iter_rows(values_only=True))

    def test_item_list_export_shows_locations_and_vehicle_columns_when_the_module_is_on(self):
        saved = self.put_setup(automobile_enabled=True, locations=[{'name': 'Rack 1'}, {'name': 'Rack 2'}])
        ids = [row['id'] for row in saved['locations']]
        self.item(name='Brake pad', location_ids=ids, oem_number='55810', part_brand='Bosch', part_grade='oem',
                  vehicle_fitment=[{'make': 'Maruti Suzuki', 'model': 'Swift', 'year_from': 2011, 'year_to': 2017}])
        text = self.export_text()
        for expected in ('Location', 'OEM number', 'Fits vehicles', 'Rack 1, Rack 2', 'Maruti Suzuki Swift 2011-2017', 'Bosch'):
            self.assertIn(expected, text)
        self.put_setup(automobile_enabled=False)
        text = self.export_text()
        self.assertIn('Rack 1, Rack 2', text)
        self.assertNotIn('OEM number', text)

    def test_setup_record_never_appears_among_business_records_or_exports(self):
        self.put_setup(automobile_enabled=True, locations=[{'name': 'Rack 1'}])
        self.assertNotIn('inventory_setup', {row['kind'] for row in self.client.get(self.base + '/records', headers=self.headers).json()})
        self.assertNotIn('Inventory setup', self.client.get(self.base + '/export.csv', headers=self.headers).text)

    def test_locations_items_and_vehicle_details_survive_a_company_backup_and_restore(self):
        saved = self.put_setup(automobile_enabled=True, locations=[{'name': 'Rack 1'}, {'name': 'Rack 2'}],
                               vehicle_added=[{'make': 'Local Coachworks', 'type': 'commercial', 'models': ['Tipper']}])
        first = saved['locations'][0]['id']
        item = self.item(name='Brake pad', location_ids=[first], oem_number='55810',
                         vehicle_fitment=[{'make': 'Hyundai', 'model': 'i20'}])
        payload = self.client.get(self.base + '/data-export.json', headers=self.headers).json()
        encoded = base64.b64encode(json.dumps(payload).encode()).decode()
        restore = {'company_name': 'Restored garage', 'backup_base64': encoded}
        preview = self.client.post('/api/backups/restore/preview', headers=self.headers, json=restore)
        self.assertEqual(preview.status_code, 200, preview.text)
        restore['digest'] = preview.json()['digest']
        response = self.client.post('/api/backups/restore/commit', headers={**self.headers, 'Idempotency-Key': uuid4().hex}, json=restore)
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        restored = body.get('company_id') or (body.get('company') or {}).get('id') or body.get('id')
        self.assertTrue(restored, body)
        setup = self.client.get(f'/api/companies/{restored}/inventory-setup', headers=self.headers).json()
        self.assertTrue(setup['automobile_enabled'])
        self.assertEqual([row['name'] for row in setup['locations']], ['Rack 1', 'Rack 2'])
        self.assertIn('Local Coachworks', [row['make'] for row in setup['vehicle_options']])
        rows = self.client.get(f'/api/companies/{restored}/records', headers=self.headers).json()
        stored = next(row for row in rows if row['name'] == 'Brake pad')
        self.assertEqual(stored['data']['location_ids'], [first])
        self.assertEqual(stored['data']['oem_number'], '55810')
        self.assertEqual(item['data']['location_ids'], [first])

    def test_a_backup_pointing_an_item_at_a_missing_location_is_refused(self):
        saved = self.put_setup(locations=[{'name': 'Rack 1'}])
        self.item(name='Pad', location_ids=[saved['locations'][0]['id']])
        payload = self.client.get(self.base + '/data-export.json', headers=self.headers).json()
        for row in payload['records']:
            if row['kind'] == 'item':
                row['data']['location_ids'] = ['loc-missing']
        encoded = base64.b64encode(json.dumps(payload).encode()).decode()
        response = self.client.post('/api/backups/restore/preview', headers=self.headers,
                                    json={'company_name': 'Bad', 'backup_base64': encoded})
        self.assertEqual(response.status_code, 422, response.text)


if __name__ == '__main__':
    unittest.main()
