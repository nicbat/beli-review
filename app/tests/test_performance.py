"""Regression coverage for request-local snapshot reuse without stale source data."""
import copy
import json
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from app.backend.store import Store
from app.tests.test_workshop import fixture


class SnapshotReuseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(Path(self.temp.name) / 'workspace.sqlite3')

    def import_export(self, payload):
        self.store.mutate(dict(action='import', payload=payload,
                               revision=self.store.view()['revision'], operation_id=str(uuid.uuid4())))

    def test_each_snapshot_is_decoded_once_per_view(self):
        self.import_export(fixture())
        self.import_export(fixture(stamp='2026-10-07T10:00:00+00:00'))
        # Archived older exports also appear in the import list, but must not
        # replace the current source content.
        self.import_export(fixture(stamp='2026-10-05T10:00:00+00:00'))
        loads = json.loads
        decoded_sources = []

        def count_source(value):
            result = loads(value)
            if 'entries' in result and 'exported_at' in result:
                decoded_sources.append(result['exported_at'])
            return result

        with patch('app.backend.store.json.loads', side_effect=count_source):
            view = self.store.view()
        self.assertEqual(len(decoded_sources), 3)
        self.assertEqual(len(set(decoded_sources)), 3)
        self.assertEqual(len(view['imports']), 3)
        self.assertEqual(view['original'], view['latest'])

    def test_merged_attachment_history_does_not_modify_snapshots(self):
        self.import_export(fixture())
        updated = fixture(stamp='2026-10-07T10:00:00+00:00')
        updated['notes'] = []
        updated['photos'] = []
        self.import_export(updated)
        with self.store.connect() as db:
            _, state = self.store.read(db)
            sources = {sid: self.store.source(db, sid) for sid in state['sources']}
            untouched = copy.deepcopy(sources)
            entries = self.store.entries(db, state, sources)
        self.assertEqual(sources, untouched)
        self.assertEqual(entries['RES:1']['previous_notes'][0]['id'], 900)
        self.assertEqual(entries['RES:1']['previous_photos'][0]['id'], 800)
        self.assertEqual(entries['RES:1']['photos'], [])

    def test_another_store_import_is_visible_on_next_view(self):
        self.import_export(fixture())
        self.store.view()
        other = Store(self.store.path)
        updated = fixture(stamp='2026-10-07T10:00:00+00:00')
        updated['notes'][0]['value'] = 'Updated in another tab'
        other.mutate(dict(action='import', payload=updated,
                          revision=other.view()['revision'], operation_id=str(uuid.uuid4())))
        self.assertEqual(self.store.view()['entries']['RES:1']['notes'][0]['value'],
                         'Updated in another tab')


if __name__ == '__main__':
    unittest.main()
