"""Offline checks: python3 -m unittest -v test_export.py"""
import tempfile
from pathlib import Path
import unittest

from export_all import fetch_pages, make_entries, own_records
from probe import API, Client


class FakeClient:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    def request(self, path, params):
        self.calls.append((path, params))
        return next(self.responses)


class ExportTests(unittest.TestCase):
    def test_pagination_retains_order_and_raw_pages(self):
        client = FakeClient([
            {'count': 2, 'results': [{'id': 1}], 'next': API + '/api/get-ranking/?user=u&category=RES&page=2'},
            {'count': 2, 'results': [{'id': 2}], 'next': None},
        ])
        with tempfile.TemporaryDirectory() as tmp:
            records = fetch_pages(client, '/api/get-ranking/', {'user': 'u', 'category': 'RES'}, Path(tmp), 'rankings')
            self.assertEqual([r['id'] for r in records], [1, 2])
            self.assertEqual(len(list(Path(tmp).glob('*.json'))), 2)
        self.assertEqual(client.calls[1][1]['page'], '2')

    def test_foreign_pagination_is_rejected(self):
        client = FakeClient([{'results': [], 'next': 'https://example.com/steal'}])
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(RuntimeError, 'destination'):
                fetch_pages(client, '/api/get-ranking/', {}, Path(tmp), 'rankings')
        self.assertEqual(len(client.calls), 1)

    def test_incomplete_count_is_reported(self):
        client = FakeClient([{'count': 5, 'results': [{'id': 1}]}])
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(RuntimeError, 'server reports'):
                fetch_pages(client, '/api/get-ranking/', {}, Path(tmp), 'rankings')

    def test_photos_join_by_business_not_response_position(self):
        ranks = {'RES': [{'business': {'id': 8, 'name': 'A'}, 'score': 9}],
                 'BAK': [{'business': {'id': 9, 'name': 'B'}, 'score': 8}]}
        entries = make_entries(ranks, [{'business': 9, 'value': 'note'}],
                               [{'business': 8, 'id': 1}, {'business': 99, 'id': 2}])
        self.assertEqual([p['id'] for p in entries[0]['photos']], [1])
        self.assertEqual(entries[0]['notes'], [])
        self.assertEqual(entries[1]['notes'][0]['value'], 'note')
        self.assertEqual(entries[1]['api_position'], 1)

    def test_foreign_users_are_excluded(self):
        warnings = []
        self.assertEqual(own_records([{'user': 'other'}, {'user_id': 'me'}], 'me', 'photos', warnings), [{'user_id': 'me'}])
        self.assertTrue(warnings)

    def test_write_routes_blocked(self):
        with self.assertRaises(ValueError):
            Client().request('/api/add-ranking/', login={})
        with self.assertRaises(ValueError):
            Client().request('/api/delete-ranking/a/1/')


if __name__ == '__main__':
    unittest.main()
