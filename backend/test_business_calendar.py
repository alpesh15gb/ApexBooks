import unittest
from datetime import date, datetime, timezone, timedelta
from unittest.mock import patch
from business_calendar import business_today, financial_year_start


class BusinessCalendarTest(unittest.TestCase):
    def test_india_midnight_is_independent_of_server_timezone(self):
        self.assertEqual(business_today(datetime(2026, 11, 2, 18, 29, 59, tzinfo=timezone.utc)), date(2026, 11, 2))
        self.assertEqual(business_today(datetime(2026, 11, 2, 18, 30, tzinfo=timezone.utc)), date(2026, 11, 3))
        same_instant = datetime(2026, 11, 2, 8, 30, tzinfo=timezone(timedelta(hours=-10)))
        self.assertEqual(business_today(same_instant), date(2026, 11, 3))
        with self.assertRaises(ValueError):
            business_today(datetime(2026, 11, 2, 18, 30))

    def test_financial_year_changes_at_india_april_first(self):
        before = business_today(datetime(2026, 3, 31, 18, 29, 59, tzinfo=timezone.utc))
        after = business_today(datetime(2026, 3, 31, 18, 30, tzinfo=timezone.utc))
        self.assertEqual(financial_year_start(before), 2025)
        self.assertEqual(financial_year_start(after), 2026)
        self.assertEqual(financial_year_start(date(2024, 2, 29)), 2023)
        with patch('business_calendar.datetime') as clock:
            clock.now.return_value = datetime(2026, 3, 31, 18, 30, tzinfo=timezone.utc)
            self.assertEqual(financial_year_start(), 2026)

    def test_default_record_date_and_report_defaults_use_business_day_but_explicit_dates_remain(self):
        import test_api
        import main
        from test_completion import CompletionTest
        instant = datetime(2026, 3, 31, 18, 30, tzinfo=timezone.utc)
        with patch('business_calendar.datetime') as clock:
            clock.now.return_value = instant
            self.assertEqual(main.RecordInput(kind='estimate', name='Synthetic').date, date(2026, 4, 1))
            self.assertEqual(main.RecordInput(kind='estimate', name='Synthetic', date='2026-03-31').date, date(2026, 3, 31))
            client, headers, base = CompletionTest().client_context('unregistered')
            party = client.post(base+'/records', headers=headers, json={'kind':'party','name':'Business date synthetic'}).json()
            self.assertEqual(party['date'], '2026-04-01')
            draft = {'kind':'estimate','name':party['name'],'data':{'party_id':party['id'],'lines':[{'description':'Service','quantity':'1','rate':'1','gst_rate':'0'}]}}
            default = client.post(base+'/records',headers=headers,json=draft)
            self.assertEqual(default.status_code,200,default.text)
            self.assertIn('/26-27/',default.json()['number'])
            selected = client.post(base+'/records',headers=headers,json={**draft,'date':'2026-03-31'})
            self.assertEqual(selected.status_code,200,selected.text)
            self.assertIn('/25-26/',selected.json()['number'])
            for path in ('/reports/reorder', '/parties/'+party['id']+'/credit-status'):
                self.assertEqual(client.get(base+path, headers=headers).json()['as_of'], '2026-04-01')
                self.assertEqual(client.get(base+path+'?as_of=2026-03-31', headers=headers).json()['as_of'], '2026-03-31')
            explicit = client.get(base+'/reports/ageing?as_of=2026-03-31',headers=headers)
            self.assertEqual(explicit.status_code, 200, explicit.text)
            self.assertEqual(explicit.json()['as_of'], '2026-03-31')
